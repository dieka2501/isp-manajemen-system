from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.services.chat_store import SQLiteChatStore

chat_router = APIRouter(prefix="/chat", tags=["chat"])


class AccountCreateRequest(BaseModel):
    name: str = Field(min_length=2)
    slug: str | None = None


class ClientCreateRequest(BaseModel):
    account_slug: str
    name: str = Field(min_length=2)
    external_ref: str | None = None


class DeviceRegisterRequest(BaseModel):
    device_identifier: str = Field(min_length=1)
    device_name: str | None = None
    outbound_token: str | None = None
    client_id: int | None = None
    client_token: str | None = None


def _store() -> SQLiteChatStore:
    return SQLiteChatStore(get_settings())


@chat_router.get("/accounts")
def list_accounts() -> dict[str, object]:
    return {"items": _store().list_accounts()}


@chat_router.post("/accounts", status_code=status.HTTP_201_CREATED)
def create_account(payload: AccountCreateRequest) -> dict[str, object]:
    try:
        account = _store().create_account(name=payload.name, slug=payload.slug)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"item": account}


@chat_router.get("/clients")
def list_clients(account_slug: str | None = Query(default=None)) -> dict[str, object]:
    return {"items": _store().list_clients(account_slug=account_slug)}


@chat_router.post("/clients", status_code=status.HTTP_201_CREATED)
def create_client(payload: ClientCreateRequest) -> dict[str, object]:
    try:
        client = _store().create_client(
            account_slug=payload.account_slug,
            name=payload.name,
            external_ref=payload.external_ref,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"item": client}


@chat_router.post("/devices", status_code=status.HTTP_201_CREATED)
def register_device(payload: DeviceRegisterRequest) -> dict[str, object]:
    if payload.client_id is None and payload.client_token is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide `client_id` or `client_token` to register a device.",
        )

    try:
        device = _store().register_device(
            device_identifier=payload.device_identifier,
            device_name=payload.device_name,
            outbound_token=payload.outbound_token,
            client_id=payload.client_id,
            client_token=payload.client_token,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return {"item": device}


@chat_router.get("/conversations")
def list_conversations(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
    return {"items": _store().list_conversations(limit=limit)}


@chat_router.get("/conversations/{conversation_id}/messages")
def list_messages(
    conversation_id: int,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, object]:
    return {"items": _store().list_messages(conversation_id=conversation_id, limit=limit)}
