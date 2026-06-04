from __future__ import annotations

from json import JSONDecodeError
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.core.config import get_settings
from app.services.google_sheets import GoogleSheetsLogger

webhooks_router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _validate_secret(provided_secret: str | None, expected_secret: str) -> None:
    if expected_secret and provided_secret != expected_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook secret.",
        )


def _parse_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook payload must be a JSON object.",
        )
    return payload


@webhooks_router.post("/fonnte")
async def receive_fonnte_webhook(
    request: Request,
    secret: str | None = Query(default=None),
) -> dict[str, Any]:
    settings = get_settings()
    _validate_secret(secret, settings.fonnte_webhook_secret)

    try:
        payload = _parse_payload(await request.json())
    except JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload.",
        ) from exc

    try:
        result = GoogleSheetsLogger(settings).append_whatsapp_message(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to write to Google Sheets: {exc}",
        ) from exc

    updates = result.get("updates", {})
    return {
        "status": "ok",
        "saved": True,
        "spreadsheet_id": settings.google_sheets_spreadsheet_id,
        "updated_range": updates.get("updatedRange"),
        "updated_rows": updates.get("updatedRows"),
    }
