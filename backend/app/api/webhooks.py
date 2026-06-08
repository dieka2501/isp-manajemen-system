from __future__ import annotations

from json import JSONDecodeError
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.core.config import get_settings
from app.services.chatbot import ISPCSChatService

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
        result = ISPCSChatService(settings).handle_incoming_payload(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected webhook processing error: {exc}",
        ) from exc

    return {
        "status": "ok",
        "saved": True,
        "conversation_id": result["conversation_id"],
        "message_id": result["message_id"],
        "client": result["client"],
        "device": result["device"],
        "analysis": result["analysis"],
        "reply_attempted": result["reply_attempted"],
        "matched_products": result["matched_products"],
        "reply_text": result["reply_text"],
        "reply_sent": result["reply_sent"],
        "send_error": result["send_error"],
    }


@webhooks_router.get("/fonnte")
async def verify_fonnte_webhook(
    secret: str | None = Query(default=None),
) -> dict[str, Any]:
    settings = get_settings()
    _validate_secret(secret, settings.fonnte_webhook_secret)

    return {
        "status": "ok",
        "message": "Fonnte webhook endpoint is ready.",
        "method": "GET",
    }
