from __future__ import annotations

import json
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings

SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
WHATSAPP_LOG_HEADERS = [
    "received_at",
    "device",
    "sender",
    "name",
    "message",
    "member",
    "url",
    "filename",
    "extension",
    "location",
    "raw_payload",
]
PRODUCT_HEADER_ALIASES = (
    "nama product",
    "nama produk",
    "product name",
    "product",
    "nama_product",
    "nama_produk",
)
TYPE_HEADER_ALIASES = ("type", "tipe")
STOCK_HEADER_ALIASES = ("stock", "stok")


def _import_google_clients() -> tuple[Any, Any, Any]:
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
    except ImportError as exc:
        raise RuntimeError(
            "Google Sheets dependencies are not installed. Run `pip install -e .` in apps/backend."
        ) from exc

    return service_account, build, HttpError


def _sheet_range(worksheet_name: str, cells: str) -> str:
    escaped_name = worksheet_name.replace("'", "''")
    return f"'{escaped_name}'!{cells}"


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=True)
    return str(value)


def _normalize_header(value: str) -> str:
    return " ".join(
        "".join(char.lower() if char.isalnum() else " " for char in value).split()
    )


def _cell(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return _stringify(row[index])


@dataclass(frozen=True)
class StockMatch:
    product_name: str
    product_type: str
    stock: str
    row_number: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "product_name": self.product_name,
            "product_type": self.product_type,
            "stock": self.stock,
            "row_number": self.row_number,
        }


class GoogleSheetsLogger:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def append_whatsapp_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.google_sheets_spreadsheet_id:
            raise ValueError("GOOGLE_SHEETS_SPREADSHEET_ID is not configured.")

        service = self._build_service()
        self._ensure_worksheet_exists(service)
        self._ensure_header_row(service)
        body = {"values": [self._build_row(payload)]}

        return (
            service.spreadsheets()
            .values()
            .append(
                spreadsheetId=self.settings.google_sheets_spreadsheet_id,
                range=_sheet_range(self.settings.google_sheets_worksheet_name, "A:K"),
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body=body,
            )
            .execute()
        )

    def search_stock_products(self, query_tokens: list[str], limit: int = 5) -> list[StockMatch]:
        if not self.settings.google_sheets_spreadsheet_id:
            raise ValueError("GOOGLE_SHEETS_SPREADSHEET_ID is not configured.")
        if not query_tokens:
            return []

        service = self._build_service()
        response = (
            service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self.settings.google_sheets_spreadsheet_id,
                range=_sheet_range(self.settings.google_sheets_stock_worksheet_name, "A:Z"),
            )
            .execute()
        )
        rows = response.get("values", [])
        if len(rows) < 2:
            return []

        headers = [_normalize_header(_stringify(header)) for header in rows[0]]
        product_index = self._find_index(headers, PRODUCT_HEADER_ALIASES)
        type_index = self._find_index(headers, TYPE_HEADER_ALIASES)
        stock_index = self._find_index(headers, STOCK_HEADER_ALIASES)

        if product_index is None:
            raise ValueError(
                "Stock sheet must contain a product name column such as `nama product`."
            )

        normalized_tokens = [_normalize_header(token) for token in query_tokens if token.strip()]
        ranked_rows: list[tuple[int, int, StockMatch]] = []
        for row_number, row in enumerate(rows[1:], start=2):
            product_name = _cell(row, product_index)
            if not product_name:
                continue

            normalized_product = _normalize_header(product_name)
            score = sum(token in normalized_product for token in normalized_tokens)
            if score == 0:
                continue

            ranked_rows.append(
                (
                    score,
                    -len(product_name),
                    StockMatch(
                        product_name=product_name,
                        product_type=_cell(row, type_index),
                        stock=_cell(row, stock_index) or "0",
                        row_number=row_number,
                    ),
                )
            )

        ranked_rows.sort(key=lambda item: (item[0], item[1]), reverse=True)
        if not ranked_rows:
            return []

        best_score = ranked_rows[0][0]
        return [match for score, _, match in ranked_rows if score == best_score][:limit]

    def _build_service(self) -> Any:
        service_account, build, _ = _import_google_clients()
        credentials = self._load_credentials(service_account)
        return build("sheets", "v4", credentials=credentials, cache_discovery=False)

    def _load_credentials(self, service_account: Any) -> Any:
        if self.settings.google_service_account_json:
            try:
                service_account_info = json.loads(self.settings.google_service_account_json)
            except json.JSONDecodeError as exc:
                raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON is not a valid JSON string.") from exc
            return service_account.Credentials.from_service_account_info(
                service_account_info,
                scopes=[SHEETS_SCOPE],
            )

        if self.settings.google_service_account_file:
            return service_account.Credentials.from_service_account_file(
                self.settings.google_service_account_file,
                scopes=[SHEETS_SCOPE],
            )

        raise ValueError(
            "Google credential is not configured. Set GOOGLE_SERVICE_ACCOUNT_FILE or GOOGLE_SERVICE_ACCOUNT_JSON."
        )

    def _find_index(self, normalized_headers: list[str], aliases: tuple[str, ...]) -> int | None:
        alias_set = {_normalize_header(alias) for alias in aliases}
        for index, header in enumerate(normalized_headers):
            if header in alias_set:
                return index
        return None

    def _ensure_worksheet_exists(self, service: Any) -> None:
        spreadsheet = (
            service.spreadsheets()
            .get(spreadsheetId=self.settings.google_sheets_spreadsheet_id)
            .execute()
        )
        sheet_titles = {
            sheet.get("properties", {}).get("title", "")
            for sheet in spreadsheet.get("sheets", [])
        }
        if self.settings.google_sheets_worksheet_name in sheet_titles:
            return

        (
            service.spreadsheets()
            .batchUpdate(
                spreadsheetId=self.settings.google_sheets_spreadsheet_id,
                body={
                    "requests": [
                        {
                            "addSheet": {
                                "properties": {
                                    "title": self.settings.google_sheets_worksheet_name,
                                }
                            }
                        }
                    ]
                },
            )
            .execute()
        )

    def _ensure_header_row(self, service: Any) -> None:
        response = (
            service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self.settings.google_sheets_spreadsheet_id,
                range=_sheet_range(self.settings.google_sheets_worksheet_name, "A1:K1"),
            )
            .execute()
        )

        values = response.get("values", [])
        if values and any(cell.strip() for cell in values[0] if isinstance(cell, str)):
            return

        (
            service.spreadsheets()
            .values()
            .update(
                spreadsheetId=self.settings.google_sheets_spreadsheet_id,
                range=_sheet_range(self.settings.google_sheets_worksheet_name, "A1:K1"),
                valueInputOption="RAW",
                body={"values": [WHATSAPP_LOG_HEADERS]},
            )
            .execute()
        )

    def _build_row(self, payload: dict[str, Any]) -> list[str]:
        return [
            datetime.now(timezone.utc).isoformat(),
            _stringify(payload.get("device")),
            _stringify(payload.get("sender")),
            _stringify(payload.get("name")),
            _stringify(payload.get("message")),
            _stringify(payload.get("member")),
            _stringify(payload.get("url")),
            _stringify(payload.get("filename")),
            _stringify(payload.get("extension")),
            _stringify(payload.get("location")),
            json.dumps(payload, ensure_ascii=True),
        ]
