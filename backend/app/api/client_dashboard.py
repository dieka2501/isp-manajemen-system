from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.registrations import (
    InstallationCompleteRequest,
    RegistrationApproveRequest,
    RegistrationPaymentRequest,
    _active_notice,
    _approved_notice,
    _notify_technicians,
    _paid_notice,
    _send_customer_message,
)
from app.auth.guards import require_client
from app.client_dashboard.permissions import ClientPermission
from app.core.config import get_settings
from app.services.chat_store import SQLiteChatStore
from app.services.client_dashboard_auth import ClientDashboardTokenService
from app.services.isp_agent import ISPCSAgent

client_dashboard_router = APIRouter(tags=["client-dashboard"])


class ClientLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identifier: str = Field(min_length=1)
    password: str = Field(min_length=1)


class AgentPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1)
    device_id: int | None = None


class LearningMapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

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


def _client_dependency(
    permission: ClientPermission,
) -> Callable[..., dict[str, object]]:
    def dependency(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> dict[str, object]:
        session = require_client(request, authorization, permission)
        client = _store().get_client_profile(session.client_id)
        if not client or not int(client.get("is_active") or 0):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Client is not active or no longer exists.",
            )
        return client

    return dependency


_dashboard_client = _client_dependency(ClientPermission.DASHBOARD_ACCESS)
_profile_client = _client_dependency(ClientPermission.PROFILE_READ)
_customers_client = _client_dependency(ClientPermission.CUSTOMERS_READ)
_packages_client = _client_dependency(ClientPermission.PACKAGES_READ)
_billing_client = _client_dependency(ClientPermission.BILLING_READ)
_registrations_client = _client_dependency(ClientPermission.REGISTRATIONS_MANAGE)
_learning_client = _client_dependency(ClientPermission.LEARNING_MANAGE)


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
def login(payload: ClientLoginRequest, response: Response) -> dict[str, object]:
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
    settings = get_settings()
    response.set_cookie(
        key=settings.client_dashboard_cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.dashboard_cookie_secure,
        path="/",
        max_age=settings.client_dashboard_token_hours * 3600,
    )
    response.delete_cookie(key=settings.dashboard_cookie_name, path="/")
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires_at,
        "client": client,
    }


@client_dashboard_router.get("/auth/me")
def me(client: dict[str, object] = Depends(_profile_client)) -> dict[str, object]:
    return {"client": client}


@client_dashboard_router.post("/auth/logout")
def logout(
    response: Response,
    client: dict[str, object] = Depends(_dashboard_client),
) -> dict[str, str]:
    settings = get_settings()
    response.delete_cookie(key=settings.client_dashboard_cookie_name, path="/")
    return {"status": "ok"}


@client_dashboard_router.get("/profile")
def profile(client: dict[str, object] = Depends(_profile_client)) -> dict[str, object]:
    return {"client": client}


@client_dashboard_router.get("/summary")
def summary(client: dict[str, object] = Depends(_dashboard_client)) -> dict[str, object]:
    client_id = int(client["id"])
    return {"item": _store().get_client_dashboard_summary(client_id)}


@client_dashboard_router.get("/devices")
def devices(client: dict[str, object] = Depends(_profile_client)) -> dict[str, object]:
    return {"items": _store().list_client_devices(int(client["id"]))}


@client_dashboard_router.get("/customers")
def customers(
    query: str | None = Query(default=None),
    status_filter: str = Query(default="all", alias="status"),
    limit: int = Query(default=200, ge=1, le=500),
    client: dict[str, object] = Depends(_customers_client),
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
    client: dict[str, object] = Depends(_packages_client),
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
    client: dict[str, object] = Depends(_billing_client),
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


def _raise_registration_error(exc: ValueError) -> None:
    status_code = (
        status.HTTP_404_NOT_FOUND
        if "not found" in str(exc).lower()
        else status.HTTP_422_UNPROCESSABLE_ENTITY
    )
    raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@client_dashboard_router.get("/registrations/items")
def registrations(
    status_filter: str = Query(default="registered", alias="status"),
    limit: int = Query(default=100, ge=1, le=200),
    client: dict[str, object] = Depends(_registrations_client),
) -> dict[str, object]:
    try:
        items = _store().list_customer_registrations(
            status_filter=status_filter,
            limit=limit,
            client_id=int(client["id"]),
        )
    except ValueError as exc:
        _raise_registration_error(exc)
    return {"items": items}


@client_dashboard_router.post("/registrations/{registration_id}/approve")
def approve_registration(
    registration_id: int,
    payload: RegistrationApproveRequest,
    client: dict[str, object] = Depends(_registrations_client),
) -> dict[str, object]:
    store = _store()
    settings = get_settings()
    try:
        item = store.approve_customer_registration(
            registration_id=registration_id,
            amount=payload.amount,
            payment_method=payload.payment_method,
            virtual_account=payload.virtual_account,
            notes=payload.notes,
            client_id=int(client["id"]),
        )
    except ValueError as exc:
        _raise_registration_error(exc)
    notification = _send_customer_message(
        settings=settings,
        registration=item,
        message=_approved_notice(item),
    )
    return {"item": item, "notification": notification}


@client_dashboard_router.post("/registrations/{registration_id}/payment")
def record_registration_payment(
    registration_id: int,
    payload: RegistrationPaymentRequest,
    client: dict[str, object] = Depends(_registrations_client),
) -> dict[str, object]:
    store = _store()
    settings = get_settings()
    try:
        item = store.record_registration_payment(
            registration_id=registration_id,
            payment_method=payload.payment_method,
            amount=payload.amount,
            reference_number=payload.reference_number,
            virtual_account=payload.virtual_account,
            notes=payload.notes,
            client_id=int(client["id"]),
        )
    except ValueError as exc:
        _raise_registration_error(exc)
    customer_notification = _send_customer_message(
        settings=settings,
        registration=item,
        message=_paid_notice(item),
    )
    technician_notification = _notify_technicians(
        settings=settings,
        store=store,
        registration=item,
    )
    return {
        "item": item,
        "customer_notification": customer_notification,
        "technician_notification": technician_notification,
    }


@client_dashboard_router.post("/registrations/{registration_id}/activate")
def activate_registration(
    registration_id: int,
    payload: InstallationCompleteRequest,
    client: dict[str, object] = Depends(_registrations_client),
) -> dict[str, object]:
    store = _store()
    settings = get_settings()
    try:
        item = store.complete_customer_installation(
            registration_id=registration_id,
            notes=payload.notes,
            client_id=int(client["id"]),
        )
    except ValueError as exc:
        _raise_registration_error(exc)
    notification = _send_customer_message(
        settings=settings,
        registration=item,
        message=_active_notice(item),
    )
    return {"item": item, "notification": notification}


@client_dashboard_router.get("/learning/intents")
def learning_intents(
    device_id: int | None = Query(default=None),
    client: dict[str, object] = Depends(_learning_client),
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
    client: dict[str, object] = Depends(_learning_client),
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
    client: dict[str, object] = Depends(_learning_client),
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
    client: dict[str, object] = Depends(_learning_client),
) -> dict[str, object]:
    store = _store()
    client_id = int(client["id"])
    device_id = _resolve_device_id_for_client(store, client_id, payload.device_id)
    catalog = store.get_intent_agent_catalog(client_id=client_id, device_id=device_id)
    return {"item": ISPCSAgent(catalog).answer(payload.message).as_dict()}
