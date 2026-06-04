from __future__ import annotations

import json
from datetime import datetime, timezone
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
