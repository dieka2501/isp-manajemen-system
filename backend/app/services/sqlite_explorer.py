from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from app.core.config import BASE_DIR, Settings


@dataclass(frozen=True)
class SQLiteSource:
    name: str
    path: str
    resolved_path: str
    exists: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "resolved_path": self.resolved_path,
            "exists": self.exists,
        }


class SQLiteExplorerService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def list_sources(self) -> list[SQLiteSource]:
        raw_sources = self._parse_sources_config()
        if not raw_sources:
            raw_sources = [
                {
                    "name": "Chat Database",
                    "path": self.settings.chat_database_path,
                }
            ]

        return [self._build_source(item) for item in raw_sources]

    def get_source(self, path: str | None) -> SQLiteSource:
        if path and path.strip():
            return self._build_source({"name": Path(path).name or "Custom Database", "path": path})
        return self.list_sources()[0]

    def list_tables(self, db_path: str) -> list[dict[str, Any]]:
        with self._connect(db_path) as conn:
            rows = conn.execute(
                """
                SELECT name, type
                FROM sqlite_master
                WHERE type IN ('table', 'view')
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY type, name
                """
            ).fetchall()

            tables: list[dict[str, Any]] = []
            for row in rows:
                table_name = row["name"]
                columns = self._table_columns(conn, table_name)
                row_count = self._table_row_count(conn, table_name) if row["type"] == "table" else None
                tables.append(
                    {
                        "name": table_name,
                        "type": row["type"],
                        "row_count": row_count,
                        "columns": columns,
                    }
                )
            return tables

    def run_query(self, db_path: str, sql: str, limit: int = 250) -> dict[str, Any]:
        query = sql.strip().rstrip(";").strip()
        if not query:
            raise ValueError("Query cannot be empty.")

        operation = self._statement_operation(query)
        if operation in {"insert", "update"}:
            return self._run_write_statement(db_path, query, operation, limit=limit)
        if operation not in {"select", "pragma", "with", "explain"}:
            raise ValueError("Only SELECT, PRAGMA, INSERT, and UPDATE statements are allowed.")

        return self._run_read_query(db_path, query, limit=limit)

    def _run_read_query(self, db_path: str, query: str, limit: int) -> dict[str, Any]:
        try:
            with self._connect(db_path, readonly=True) as conn:
                cursor = conn.execute(query)
                columns = [column[0] for column in cursor.description or []]
                rows = cursor.fetchmany(limit)
                result_rows = [self._stringify_row(row, columns) for row in rows]
                truncated = cursor.fetchone() is not None
        except sqlite3.Error as exc:
            raise ValueError(self._sqlite_error_message(exc)) from exc

        return {
            "columns": columns,
            "rows": result_rows,
            "row_count": len(result_rows),
            "truncated": truncated,
            "limit": limit,
            "sql": query,
            "operation": "read",
            "rows_affected": None,
            "last_insert_rowid": None,
        }

    def _run_write_statement(
        self,
        db_path: str,
        query: str,
        operation: str,
        limit: int,
    ) -> dict[str, Any]:
        try:
            with self._connect(db_path, readonly=False) as conn:
                try:
                    cursor = conn.execute(query)
                    columns = [column[0] for column in cursor.description or []]
                    rows = cursor.fetchmany(limit) if columns else []
                    result_rows = [self._stringify_row(row, columns) for row in rows]
                    truncated = cursor.fetchone() is not None if columns else False
                    rows_affected = cursor.rowcount if cursor.rowcount >= 0 else 0
                    last_insert_rowid = cursor.lastrowid if cursor.lastrowid else None
                    conn.commit()
                except sqlite3.Error:
                    conn.rollback()
                    raise
        except sqlite3.Error as exc:
            raise ValueError(self._sqlite_error_message(exc)) from exc

        return {
            "columns": columns,
            "rows": result_rows,
            "row_count": len(result_rows),
            "truncated": truncated,
            "limit": limit,
            "sql": query,
            "operation": operation,
            "rows_affected": rows_affected,
            "last_insert_rowid": last_insert_rowid,
        }

    def preview_table(self, db_path: str, table_name: str, limit: int = 100) -> dict[str, Any]:
        quoted_table = self._quote_identifier(table_name)
        return self.run_query(db_path, f"SELECT * FROM {quoted_table} LIMIT {limit}", limit=limit)

    def _parse_sources_config(self) -> list[dict[str, Any]]:
        raw = self.settings.sqlite_explorer_sources_json.strip()
        if not raw:
            return []

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("SQLITE_EXPLORER_SOURCES_JSON must be valid JSON.") from exc

        if isinstance(parsed, str):
            try:
                parsed = json.loads(parsed)
            except json.JSONDecodeError as exc:
                raise ValueError("SQLITE_EXPLORER_SOURCES_JSON must be valid JSON.") from exc

        if isinstance(parsed, dict):
            parsed = [parsed]
        elif not isinstance(parsed, list):
            raise ValueError("SQLITE_EXPLORER_SOURCES_JSON must be a JSON array or object.")

        sources: list[dict[str, Any]] = []
        for item in parsed:
            if isinstance(item, str):
                sources.append({"name": Path(item).name or item, "path": item})
            elif isinstance(item, dict):
                path = item.get("path")
                if not path:
                    continue
                sources.append(
                    {
                        "name": str(item.get("name") or Path(str(path)).name or path),
                        "path": str(path),
                    }
                )
        return sources

    def _build_source(self, item: dict[str, Any]) -> SQLiteSource:
        raw_path = str(item["path"])
        resolved = self._resolve_path(raw_path)
        return SQLiteSource(
            name=str(item.get("name") or Path(raw_path).name or raw_path),
            path=raw_path,
            resolved_path=str(resolved),
            exists=resolved.exists(),
        )

    def _resolve_path(self, raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser()
        if candidate.is_absolute():
            return candidate.resolve()
        return (BASE_DIR / candidate).resolve()

    def _connect(self, db_path: str, *, readonly: bool) -> sqlite3.Connection:
        resolved = self._resolve_path(db_path)
        if not resolved.exists():
            raise FileNotFoundError(f"SQLite file not found: {resolved}")
        mode = "ro" if readonly else "rw"
        conn = sqlite3.connect(f"file:{quote(str(resolved))}?mode={mode}", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def _statement_operation(self, query: str) -> str:
        statement = self._strip_leading_comments(query).lstrip()
        if not statement:
            return ""
        return statement.split(None, 1)[0].lower()

    def _strip_leading_comments(self, query: str) -> str:
        statement = query
        while True:
            stripped = statement.lstrip()
            if stripped.startswith("--"):
                newline_index = stripped.find("\n")
                if newline_index == -1:
                    return ""
                statement = stripped[newline_index + 1 :]
                continue
            if stripped.startswith("/*"):
                end_index = stripped.find("*/")
                if end_index == -1:
                    return ""
                statement = stripped[end_index + 2 :]
                continue
            return stripped

    def _table_columns(self, conn: sqlite3.Connection, table_name: str) -> list[dict[str, Any]]:
        rows = conn.execute(f"PRAGMA table_info({self._quote_identifier(table_name)})").fetchall()
        return [
            {
                "name": row["name"],
                "type": row["type"],
                "notnull": bool(row["notnull"]),
                "default_value": row["dflt_value"],
                "primary_key": bool(row["pk"]),
            }
            for row in rows
        ]

    def _table_row_count(self, conn: sqlite3.Connection, table_name: str) -> int:
        row = conn.execute(
            f"SELECT COUNT(*) AS count FROM {self._quote_identifier(table_name)}"
        ).fetchone()
        return int(row["count"]) if row else 0

    def _stringify_row(self, row: sqlite3.Row, columns: list[str]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for column in columns:
            value = row[column]
            result[column] = self._stringify_value(value)
        return result

    def _stringify_value(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.hex()
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=True)
        return value

    def _quote_identifier(self, value: str) -> str:
        escaped = value.replace('"', '""')
        return f'"{escaped}"'

    def _sqlite_error_message(self, exc: sqlite3.Error) -> str:
        message = str(exc).strip()
        return message or "SQLite query failed."
