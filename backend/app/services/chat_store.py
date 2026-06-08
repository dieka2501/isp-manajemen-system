from __future__ import annotations

import json
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import Settings


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "account"


def _normalize_search_text(value: str) -> str:
    return " ".join(
        "".join(char.lower() if char.isalnum() else " " for char in value).split()
    )


@dataclass(frozen=True)
class DeviceContext:
    account_id: int
    account_name: str
    account_slug: str
    client_id: int
    client_name: str
    client_token: str
    device_id: int
    device_identifier: str
    device_name: str | None
    outbound_token: str | None


@dataclass(frozen=True)
class StoredIncomingMessage:
    conversation_id: int
    message_id: int
    sender_number: str
    sender_name: str | None
    device: DeviceContext


@dataclass(frozen=True)
class StockMatch:
    product_id: int
    product_name: str
    product_type: str
    stock: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "product_name": self.product_name,
            "product_type": self.product_type,
            "stock": self.stock,
        }


class SQLiteChatStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db_path = Path(settings.chat_database_path)

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    slug TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS clients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    external_ref TEXT,
                    api_token TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS devices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER NOT NULL,
                    device_identifier TEXT NOT NULL UNIQUE,
                    device_name TEXT,
                    outbound_token TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER NOT NULL,
                    device_id INTEGER NOT NULL,
                    sender_number TEXT NOT NULL,
                    sender_name TEXT,
                    last_message_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE,
                    FOREIGN KEY (device_id) REFERENCES devices (id) ON DELETE CASCADE,
                    UNIQUE (client_id, device_id, sender_number)
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id INTEGER NOT NULL,
                    direction TEXT NOT NULL CHECK(direction IN ('incoming', 'outgoing')),
                    message_text TEXT NOT NULL,
                    matched_keywords TEXT,
                    matched_product_name TEXT,
                    reply_text TEXT,
                    raw_payload TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS stock_products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER NOT NULL,
                    product_name TEXT NOT NULL,
                    product_type TEXT,
                    stock INTEGER NOT NULL DEFAULT 0,
                    metadata TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE CASCADE,
                    UNIQUE (client_id, product_name, product_type)
                );

                CREATE INDEX IF NOT EXISTS idx_clients_account_id ON clients (account_id);
                CREATE INDEX IF NOT EXISTS idx_devices_client_id ON devices (client_id);
                CREATE INDEX IF NOT EXISTS idx_conversations_client_id ON conversations (client_id);
                CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages (conversation_id);
                CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages (created_at);
                CREATE INDEX IF NOT EXISTS idx_stock_products_client_id
                    ON stock_products (client_id);
                CREATE INDEX IF NOT EXISTS idx_stock_products_name
                    ON stock_products (product_name);
                """
            )

    def list_accounts(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    a.id,
                    a.name,
                    a.slug,
                    a.created_at,
                    a.updated_at,
                    COUNT(DISTINCT c.id) AS client_count,
                    COUNT(DISTINCT d.id) AS device_count
                FROM accounts a
                LEFT JOIN clients c ON c.account_id = a.id
                LEFT JOIN devices d ON d.client_id = c.id
                GROUP BY a.id
                ORDER BY a.created_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def create_account(self, name: str, slug: str | None = None) -> dict[str, Any]:
        now = _utc_now()
        normalized_slug = _slugify(slug or name)
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM accounts WHERE slug = ?",
                (normalized_slug,),
            ).fetchone()
            if existing:
                raise ValueError(f"Account slug `{normalized_slug}` already exists.")

            cursor = conn.execute(
                """
                INSERT INTO accounts (name, slug, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (name.strip(), normalized_slug, now, now),
            )
            account_id = cursor.lastrowid
            row = conn.execute(
                """
                SELECT id, name, slug, created_at, updated_at
                FROM accounts
                WHERE id = ?
                """,
                (account_id,),
            ).fetchone()
        return dict(row) if row else {}

    def create_client(
        self,
        *,
        account_slug: str,
        name: str,
        external_ref: str | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        api_token = secrets.token_urlsafe(24)
        with self._connect() as conn:
            account = conn.execute(
                "SELECT id, name, slug FROM accounts WHERE slug = ?",
                (account_slug,),
            ).fetchone()
            if not account:
                raise ValueError(f"Account `{account_slug}` was not found.")

            cursor = conn.execute(
                """
                INSERT INTO clients (
                    account_id,
                    name,
                    external_ref,
                    api_token,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    account["id"],
                    name.strip(),
                    external_ref.strip() if external_ref else None,
                    api_token,
                    now,
                    now,
                ),
            )
            client_id = cursor.lastrowid
            row = conn.execute(
                """
                SELECT
                    c.id,
                    c.account_id,
                    a.name AS account_name,
                    a.slug AS account_slug,
                    c.name,
                    c.external_ref,
                    c.api_token,
                    c.created_at,
                    c.updated_at
                FROM clients c
                JOIN accounts a ON a.id = c.account_id
                WHERE c.id = ?
                """,
                (client_id,),
            ).fetchone()
        return dict(row) if row else {}

    def list_clients(self, account_slug: str | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT
                c.id,
                c.account_id,
                a.name AS account_name,
                a.slug AS account_slug,
                c.name,
                c.external_ref,
                c.api_token,
                c.created_at,
                c.updated_at,
                COUNT(DISTINCT d.id) AS device_count,
                COUNT(DISTINCT conv.id) AS conversation_count
            FROM clients c
            JOIN accounts a ON a.id = c.account_id
            LEFT JOIN devices d ON d.client_id = c.id
            LEFT JOIN conversations conv ON conv.client_id = c.id
        """
        params: tuple[Any, ...] = ()
        if account_slug:
            query += " WHERE a.slug = ?"
            params = (account_slug,)
        query += " GROUP BY c.id ORDER BY c.created_at DESC"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def register_device(
        self,
        *,
        device_identifier: str,
        device_name: str | None,
        outbound_token: str | None,
        client_id: int | None = None,
        client_token: str | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        with self._connect() as conn:
            client = self._resolve_client(conn, client_id=client_id, client_token=client_token)
            if not client:
                raise ValueError("Client was not found for the provided identifier/token.")

            existing = conn.execute(
                "SELECT id FROM devices WHERE device_identifier = ?",
                (device_identifier,),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE devices
                    SET client_id = ?, device_name = ?, outbound_token = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        client["id"],
                        device_name,
                        outbound_token,
                        now,
                        existing["id"],
                    ),
                )
                device_id = existing["id"]
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO devices (
                        client_id,
                        device_identifier,
                        device_name,
                        outbound_token,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        client["id"],
                        device_identifier,
                        device_name,
                        outbound_token,
                        now,
                        now,
                    ),
                )
                device_id = cursor.lastrowid

            row = conn.execute(
                """
                SELECT
                    d.id,
                    d.device_identifier,
                    d.device_name,
                    d.outbound_token,
                    d.created_at,
                    d.updated_at,
                    c.id AS client_id,
                    c.name AS client_name,
                    c.api_token AS client_token,
                    a.slug AS account_slug
                FROM devices d
                JOIN clients c ON c.id = d.client_id
                JOIN accounts a ON a.id = c.account_id
                WHERE d.id = ?
                """,
                (device_id,),
            ).fetchone()
        return dict(row) if row else {}

    def save_incoming_message(self, payload: dict[str, Any]) -> StoredIncomingMessage:
        message_text = self._extract_message_text(payload)
        sender_number = self._extract_sender(payload)
        sender_name = self._extract_sender_name(payload)
        device_identifier = self._extract_device(payload)
        now = _utc_now()

        with self._connect() as conn:
            device = self._get_or_create_device_context(conn, device_identifier)
            conversation_id = self._get_or_create_conversation(
                conn=conn,
                client_id=device.client_id,
                device_id=device.device_id,
                sender_number=sender_number,
                sender_name=sender_name,
                at=now,
            )
            cursor = conn.execute(
                """
                INSERT INTO messages (
                    conversation_id,
                    direction,
                    message_text,
                    raw_payload,
                    created_at
                )
                VALUES (?, 'incoming', ?, ?, ?)
                """,
                (
                    conversation_id,
                    message_text,
                    json.dumps(payload, ensure_ascii=True),
                    now,
                ),
            )

        return StoredIncomingMessage(
            conversation_id=conversation_id,
            message_id=int(cursor.lastrowid),
            sender_number=sender_number,
            sender_name=sender_name,
            device=device,
        )

    def save_outgoing_message(
        self,
        *,
        conversation_id: int,
        reply_text: str,
        matched_keywords: list[str],
        matched_product_names: list[str],
        raw_payload: dict[str, Any] | None = None,
    ) -> int:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE conversations
                SET last_message_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, now, conversation_id),
            )
            cursor = conn.execute(
                """
                INSERT INTO messages (
                    conversation_id,
                    direction,
                    message_text,
                    matched_keywords,
                    matched_product_name,
                    raw_payload,
                    created_at
                )
                VALUES (?, 'outgoing', ?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    reply_text,
                    json.dumps(matched_keywords, ensure_ascii=True),
                    json.dumps(matched_product_names, ensure_ascii=True),
                    json.dumps(raw_payload, ensure_ascii=True) if raw_payload else None,
                    now,
                ),
            )
        return int(cursor.lastrowid)

    def update_incoming_message_analysis(
        self,
        *,
        message_id: int,
        matched_keywords: list[str],
        matched_product_names: list[str],
        reply_text: str | None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE messages
                SET matched_keywords = ?, matched_product_name = ?, reply_text = ?
                WHERE id = ?
                """,
                (
                    json.dumps(matched_keywords, ensure_ascii=True),
                    json.dumps(matched_product_names, ensure_ascii=True),
                    reply_text,
                    message_id,
                ),
            )

    def list_stock_products(
        self,
        *,
        client_id: int | None = None,
        client_token: str | None = None,
        query: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 500))
        filters = []
        params: list[Any] = []

        with self._connect() as conn:
            resolved_client = self._resolve_client(
                conn,
                client_id=client_id,
                client_token=client_token,
            )
            if client_id is not None or client_token:
                if not resolved_client:
                    raise ValueError("Client was not found for the provided identifier/token.")
                filters.append("sp.client_id = ?")
                params.append(resolved_client["id"])

            if query and query.strip():
                filters.append("LOWER(sp.product_name) LIKE ?")
                params.append(f"%{query.strip().lower()}%")

            where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
            rows = conn.execute(
                f"""
                SELECT
                    sp.id,
                    sp.client_id,
                    c.name AS client_name,
                    a.slug AS account_slug,
                    sp.product_name,
                    sp.product_type,
                    sp.stock,
                    sp.metadata,
                    sp.created_at,
                    sp.updated_at
                FROM stock_products sp
                JOIN clients c ON c.id = sp.client_id
                JOIN accounts a ON a.id = c.account_id
                {where_clause}
                ORDER BY sp.updated_at DESC, sp.id DESC
                LIMIT ?
                """,
                (*params, safe_limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_stock_product(
        self,
        *,
        product_name: str,
        stock: int,
        product_type: str | None = None,
        metadata: dict[str, Any] | None = None,
        client_id: int | None = None,
        client_token: str | None = None,
    ) -> dict[str, Any]:
        normalized_name = product_name.strip()
        normalized_type = product_type.strip() if product_type else ""
        if not normalized_name:
            raise ValueError("Product name cannot be empty.")
        if stock < 0:
            raise ValueError("Stock cannot be negative.")

        now = _utc_now()
        with self._connect() as conn:
            client = self._resolve_client(conn, client_id=client_id, client_token=client_token)
            if not client:
                raise ValueError("Client was not found for the provided identifier/token.")

            existing = conn.execute(
                """
                SELECT id
                FROM stock_products
                WHERE client_id = ? AND product_name = ? AND product_type = ?
                """,
                (client["id"], normalized_name, normalized_type),
            ).fetchone()
            if existing:
                product_id = int(existing["id"])
                conn.execute(
                    """
                    UPDATE stock_products
                    SET stock = ?, metadata = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        stock,
                        json.dumps(metadata, ensure_ascii=True) if metadata else None,
                        now,
                        product_id,
                    ),
                )
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO stock_products (
                        client_id,
                        product_name,
                        product_type,
                        stock,
                        metadata,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        client["id"],
                        normalized_name,
                        normalized_type,
                        stock,
                        json.dumps(metadata, ensure_ascii=True) if metadata else None,
                        now,
                        now,
                    ),
                )
                product_id = int(cursor.lastrowid)

            row = conn.execute(
                """
                SELECT
                    sp.id,
                    sp.client_id,
                    c.name AS client_name,
                    a.slug AS account_slug,
                    sp.product_name,
                    sp.product_type,
                    sp.stock,
                    sp.metadata,
                    sp.created_at,
                    sp.updated_at
                FROM stock_products sp
                JOIN clients c ON c.id = sp.client_id
                JOIN accounts a ON a.id = c.account_id
                WHERE sp.id = ?
                """,
                (product_id,),
            ).fetchone()
        return dict(row) if row else {}

    def search_stock_products(
        self,
        *,
        client_id: int,
        query_tokens: list[str],
        limit: int = 5,
    ) -> list[StockMatch]:
        normalized_tokens = [
            _normalize_search_text(token)
            for token in query_tokens
            if token and token.strip()
        ]
        if not normalized_tokens:
            return []

        safe_limit = max(1, min(limit, 20))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, product_name, product_type, stock
                FROM stock_products
                WHERE client_id = ?
                """,
                (client_id,),
            ).fetchall()

        ranked_rows: list[tuple[int, int, StockMatch]] = []
        for row in rows:
            product_name = str(row["product_name"])
            normalized_product = _normalize_search_text(product_name)
            score = sum(token in normalized_product for token in normalized_tokens)
            if score == 0:
                continue

            ranked_rows.append(
                (
                    score,
                    -len(product_name),
                    StockMatch(
                        product_id=int(row["id"]),
                        product_name=product_name,
                        product_type=str(row["product_type"] or ""),
                        stock=int(row["stock"] or 0),
                    ),
                )
            )

        ranked_rows.sort(key=lambda item: (item[0], item[1]), reverse=True)
        if not ranked_rows:
            return []

        best_score = ranked_rows[0][0]
        return [match for score, _, match in ranked_rows if score == best_score][:safe_limit]

    def list_conversations(self, limit: int = 50) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 200))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    conv.id,
                    conv.sender_number,
                    conv.sender_name,
                    conv.last_message_at,
                    conv.created_at,
                    conv.updated_at,
                    c.id AS client_id,
                    c.name AS client_name,
                    c.api_token AS client_token,
                    a.slug AS account_slug,
                    d.device_identifier,
                    d.device_name,
                    (
                        SELECT m.message_text
                        FROM messages m
                        WHERE m.conversation_id = conv.id
                        ORDER BY m.created_at DESC, m.id DESC
                        LIMIT 1
                    ) AS last_message_text
                FROM conversations conv
                JOIN clients c ON c.id = conv.client_id
                JOIN accounts a ON a.id = c.account_id
                JOIN devices d ON d.id = conv.device_id
                ORDER BY conv.updated_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_messages(self, conversation_id: int, limit: int = 100) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 500))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    id,
                    conversation_id,
                    direction,
                    message_text,
                    matched_keywords,
                    matched_product_name,
                    reply_text,
                    raw_payload,
                    created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC, id ASC
                LIMIT ?
                """,
                (conversation_id, safe_limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _resolve_client(
        self,
        conn: sqlite3.Connection,
        *,
        client_id: int | None,
        client_token: str | None,
    ) -> sqlite3.Row | None:
        if client_id is not None:
            return conn.execute(
                "SELECT id, account_id, name, api_token FROM clients WHERE id = ?",
                (client_id,),
            ).fetchone()
        if client_token:
            return conn.execute(
                "SELECT id, account_id, name, api_token FROM clients WHERE api_token = ?",
                (client_token,),
            ).fetchone()
        return None

    def _get_or_create_device_context(
        self,
        conn: sqlite3.Connection,
        device_identifier: str,
    ) -> DeviceContext:
        row = conn.execute(
            """
            SELECT
                a.id AS account_id,
                a.name AS account_name,
                a.slug AS account_slug,
                c.id AS client_id,
                c.name AS client_name,
                c.api_token AS client_token,
                d.id AS device_id,
                d.device_identifier,
                d.device_name,
                d.outbound_token
            FROM devices d
            JOIN clients c ON c.id = d.client_id
            JOIN accounts a ON a.id = c.account_id
            WHERE d.device_identifier = ?
            """,
            (device_identifier,),
        ).fetchone()
        if row:
            return DeviceContext(**dict(row))

        now = _utc_now()
        auto_account = conn.execute(
            "SELECT id, name, slug FROM accounts WHERE slug = ?",
            (self.settings.chat_auto_account_slug,),
        ).fetchone()
        if not auto_account:
            cursor = conn.execute(
                """
                INSERT INTO accounts (name, slug, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    self.settings.chat_auto_account_name,
                    self.settings.chat_auto_account_slug,
                    now,
                    now,
                ),
            )
            auto_account = conn.execute(
                "SELECT id, name, slug FROM accounts WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()

        client_name = f"Auto Client {device_identifier}"
        api_token = secrets.token_urlsafe(24)
        client_cursor = conn.execute(
            """
            INSERT INTO clients (
                account_id,
                name,
                external_ref,
                api_token,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                auto_account["id"],
                client_name,
                device_identifier,
                api_token,
                now,
                now,
            ),
        )
        client_id = int(client_cursor.lastrowid)
        device_cursor = conn.execute(
            """
            INSERT INTO devices (
                client_id,
                device_identifier,
                device_name,
                outbound_token,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                client_id,
                device_identifier,
                device_identifier,
                self.settings.fonnte_token or None,
                now,
                now,
            ),
        )
        return DeviceContext(
            account_id=int(auto_account["id"]),
            account_name=str(auto_account["name"]),
            account_slug=str(auto_account["slug"]),
            client_id=client_id,
            client_name=client_name,
            client_token=api_token,
            device_id=int(device_cursor.lastrowid),
            device_identifier=device_identifier,
            device_name=device_identifier,
            outbound_token=self.settings.fonnte_token or None,
        )

    def _get_or_create_conversation(
        self,
        *,
        conn: sqlite3.Connection,
        client_id: int,
        device_id: int,
        sender_number: str,
        sender_name: str | None,
        at: str,
    ) -> int:
        existing = conn.execute(
            """
            SELECT id
            FROM conversations
            WHERE client_id = ? AND device_id = ? AND sender_number = ?
            """,
            (client_id, device_id, sender_number),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE conversations
                SET sender_name = ?, last_message_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (sender_name, at, at, existing["id"]),
            )
            return int(existing["id"])

        cursor = conn.execute(
            """
            INSERT INTO conversations (
                client_id,
                device_id,
                sender_number,
                sender_name,
                last_message_at,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (client_id, device_id, sender_number, sender_name, at, at, at),
        )
        return int(cursor.lastrowid)

    def _extract_device(self, payload: dict[str, Any]) -> str:
        for key in ("device", "device_id", "deviceId"):
            value = payload.get(key)
            if value:
                return str(value)
        return "unknown-device"

    def _extract_sender(self, payload: dict[str, Any]) -> str:
        for key in ("sender", "from", "number", "phone"):
            value = payload.get(key)
            if value:
                return str(value)
        return "unknown-sender"

    def _extract_sender_name(self, payload: dict[str, Any]) -> str | None:
        for key in ("name", "sender_name", "pushName"):
            value = payload.get(key)
            if value:
                return str(value)
        return None

    def _extract_message_text(self, payload: dict[str, Any]) -> str:
        for key in ("message", "text", "body"):
            value = payload.get(key)
            if value:
                return str(value)
        return ""
