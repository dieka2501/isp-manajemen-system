from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.services.chat_store import SQLiteChatStore
from app.services.client_dashboard_auth import ClientDashboardTokenService
from app.services.isp_agent import ISPCSAgent

client_dashboard_router = APIRouter(
    prefix="/client-dashboard",
    tags=["client-dashboard"],
)


class ClientLoginRequest(BaseModel):
    identifier: str = Field(min_length=1)
    password: str = Field(min_length=1)


class AgentPreviewRequest(BaseModel):
    message: str = Field(min_length=1)
    device_id: int | None = None


class LearningMapRequest(BaseModel):
    intent_code: str | None = None
    mapping_type: str
    keyword: str | None = None
    normalized_keyword: str | None = None
    weight: int = Field(default=4, ge=1, le=10)
    notes: str | None = None


def _store() -> SQLiteChatStore:
    return SQLiteChatStore(get_settings())


def _token_service() -> ClientDashboardTokenService:
    return ClientDashboardTokenService(get_settings())


def _current_client(authorization: str | None = Header(default=None)) -> dict[str, object]:
    store = _store()
    client_id = _token_service().require_client_id(authorization)
    client = store.get_client_profile(client_id)
    if not client or not int(client.get("is_active") or 0):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Client is not active or no longer exists.",
        )
    return client


def _resolve_device_id_for_client(
    store: SQLiteChatStore,
    client_id: int,
    requested_device_id: int | None,
) -> int | None:
    devices = store.list_client_devices(client_id)
    if not devices:
        return None
    if requested_device_id is None:
        return int(devices[0]["id"])
    if any(int(device["id"]) == requested_device_id for device in devices):
        return requested_device_id
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Device was not found for this client.",
    )


@client_dashboard_router.post("/auth/login")
def login(payload: ClientLoginRequest) -> dict[str, object]:
    store = _store()
    client = store.authenticate_client(
        identifier=payload.identifier,
        password=payload.password,
    )
    if not client:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid client login.",
        )
    token, expires_at = _token_service().issue_token(int(client["id"]))
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires_at,
        "client": client,
    }


@client_dashboard_router.get("/auth/me")
def me(client: dict[str, object] = Depends(_current_client)) -> dict[str, object]:
    return {"client": client}


@client_dashboard_router.get("/profile")
def profile(client: dict[str, object] = Depends(_current_client)) -> dict[str, object]:
    return {"client": client}


@client_dashboard_router.get("/summary")
def summary(client: dict[str, object] = Depends(_current_client)) -> dict[str, object]:
    client_id = int(client["id"])
    return {"item": _store().get_client_dashboard_summary(client_id)}


@client_dashboard_router.get("/devices")
def devices(client: dict[str, object] = Depends(_current_client)) -> dict[str, object]:
    return {"items": _store().list_client_devices(int(client["id"]))}


@client_dashboard_router.get("/customers")
def customers(
    query: str | None = Query(default=None),
    status_filter: str = Query(default="all", alias="status"),
    limit: int = Query(default=200, ge=1, le=500),
    client: dict[str, object] = Depends(_current_client),
) -> dict[str, object]:
    try:
        items = _store().list_customers(
            client_id=int(client["id"]),
            query=query,
            status_filter=status_filter,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {"items": items}


@client_dashboard_router.get("/packages")
def packages(
    active_only: bool = Query(default=True),
    client: dict[str, object] = Depends(_current_client),
) -> dict[str, object]:
    return {
        "items": _store().list_client_packages(
            client_id=int(client["id"]),
            active_only=active_only,
        )
    }


@client_dashboard_router.get("/billing")
def billing(
    status_filter: str = Query(default="all", alias="status"),
    limit: int = Query(default=200, ge=1, le=500),
    client: dict[str, object] = Depends(_current_client),
) -> dict[str, object]:
    try:
        items = _store().list_billing_records(
            client_id=int(client["id"]),
            status_filter=status_filter,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {"items": items}


@client_dashboard_router.get("/learning/intents")
def learning_intents(
    device_id: int | None = Query(default=None),
    client: dict[str, object] = Depends(_current_client),
) -> dict[str, object]:
    store = _store()
    client_id = int(client["id"])
    resolved_device_id = _resolve_device_id_for_client(store, client_id, device_id)
    return {
        "items": store.list_intents_for_mapping(
            client_id=client_id,
            device_id=resolved_device_id,
        ),
        "device_id": resolved_device_id,
    }


@client_dashboard_router.get("/learning/unprocessed")
def learning_unprocessed(
    status_filter: str = Query(default="pending", alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    client: dict[str, object] = Depends(_current_client),
) -> dict[str, object]:
    try:
        items = _store().list_unprocessed_questions(
            status_filter=status_filter,
            limit=limit,
            client_id=int(client["id"]),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {"items": items}


@client_dashboard_router.post("/learning/unprocessed/{question_id}/map")
def map_learning_unprocessed(
    question_id: int,
    payload: LearningMapRequest,
    client: dict[str, object] = Depends(_current_client),
) -> dict[str, object]:
    store = _store()
    try:
        item = store.get_unprocessed_question(question_id)
        if int(item["client_id"]) != int(client["id"]):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Learning item was not found for this client.",
            )
        mapped = store.map_unprocessed_question(
            question_id=question_id,
            intent_code=payload.intent_code,
            mapping_type=payload.mapping_type,
            keyword=payload.keyword,
            normalized_keyword=payload.normalized_keyword,
            weight=payload.weight,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {"item": mapped}


@client_dashboard_router.post("/agent/preview")
def preview_agent_reply(
    payload: AgentPreviewRequest,
    client: dict[str, object] = Depends(_current_client),
) -> dict[str, object]:
    store = _store()
    client_id = int(client["id"])
    device_id = _resolve_device_id_for_client(store, client_id, payload.device_id)
    catalog = store.get_intent_agent_catalog(client_id=client_id, device_id=device_id)
    return {"item": ISPCSAgent(catalog).answer(payload.message).as_dict()}
