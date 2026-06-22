from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict

from app.auth.guards import provider_guard
from app.core.config import get_settings
from app.provider_dashboard.permissions import ProviderPermission
from app.services.chat_store import SQLiteChatStore

provider_message_dump_router = APIRouter(tags=["provider-message-dumps"])


class MessageDumpReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    reviewer_notes: str | None = None


def _store() -> SQLiteChatStore:
    return SQLiteChatStore(get_settings())


@provider_message_dump_router.get(
    "/items",
    dependencies=[Depends(provider_guard(ProviderPermission.MESSAGE_DUMPS_MANAGE))],
)
def list_message_dumps(
    status_filter: str = Query(default="pending", alias="status"),
    limit: int = Query(default=100, ge=1, le=200),
) -> dict[str, Any]:
    try:
        items = _store().list_misaligned_message_dumps(
            status_filter=status_filter,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {"items": items}


@provider_message_dump_router.post(
    "/{dump_id}",
    dependencies=[Depends(provider_guard(ProviderPermission.MESSAGE_DUMPS_MANAGE))],
)
def review_message_dump(
    dump_id: int,
    payload: MessageDumpReviewRequest,
) -> dict[str, Any]:
    try:
        item = _store().review_misaligned_message_dump(
            dump_id=dump_id,
            status=payload.status,
            reviewer_notes=payload.reviewer_notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {"item": item}
