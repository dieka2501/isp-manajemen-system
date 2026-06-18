from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.services.chat_store import SQLiteChatStore
from app.services.dashboard_auth import DashboardAuthService
from app.services.fonnte import FonnteClient

registration_router = APIRouter(prefix="/registrations", tags=["customer-registrations"])


class PublicRegistrationSubmitRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    phone: str = Field(min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    address: str = Field(min_length=1)
    maps_link: str | None = None


class RegistrationApproveRequest(BaseModel):
    amount: int | None = Field(default=None, ge=0)
    payment_method: str = Field(default="virtual_account")
    virtual_account: str | None = None
    notes: str | None = None


class RegistrationPaymentRequest(BaseModel):
    payment_method: str
    amount: int = Field(default=0, ge=0)
    reference_number: str | None = None
    virtual_account: str | None = None
    notes: str | None = None


class InstallationCompleteRequest(BaseModel):
    notes: str | None = None


class VirtualAccountCallbackRequest(BaseModel):
    registration_id: int
    amount: int = Field(default=0, ge=0)
    reference_number: str | None = None
    virtual_account: str | None = None
    provider_payload: dict[str, Any] | None = None


class MessageDumpReviewRequest(BaseModel):
    status: str
    reviewer_notes: str | None = None


@dataclass(frozen=True)
class UploadedPart:
    filename: str
    content_type: str
    data: bytes


def _store() -> SQLiteChatStore:
    return SQLiteChatStore(get_settings())


def _settings() -> Settings:
    return get_settings()


def _require_dashboard_auth(request: Request) -> None:
    DashboardAuthService(get_settings()).require_auth(request)


def _parse_optional_int(value: str | None, default: int = 0) -> int:
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid integer value `{value}`.",
        ) from exc


def _parse_multipart_form(
    *,
    content_type: str,
    body: bytes,
) -> tuple[dict[str, str], dict[str, UploadedPart]]:
    if "multipart/form-data" not in content_type:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Use multipart/form-data with a proof_file upload.",
        )

    message = BytesParser(policy=default).parsebytes(
        b"Content-Type: "
        + content_type.encode("utf-8")
        + b"\r\nMIME-Version: 1.0\r\n\r\n"
        + body
    )
    if not message.is_multipart():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid multipart upload.",
        )

    fields: dict[str, str] = {}
    files: dict[str, UploadedPart] = {}
    for part in message.iter_parts():
        params = dict(part.get_params(header="content-disposition") or [])
        field_name = params.get("name")
        if not field_name:
            continue
        payload = part.get_payload(decode=True) or b""
        filename = params.get("filename")
        if filename:
            files[field_name] = UploadedPart(
                filename=filename,
                content_type=part.get_content_type(),
                data=payload,
            )
        else:
            fields[field_name] = payload.decode("utf-8", errors="replace").strip()
    return fields, files


def _safe_filename(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(filename).stem).strip(".-")
    return f"{stem or 'payment-proof'}{suffix}"


def _send_customer_message(
    *,
    settings: Settings,
    registration: dict[str, Any],
    message: str,
) -> dict[str, Any]:
    try:
        result = FonnteClient(settings).send_message(
            target_number=str(registration["phone"] or registration["sender_number"]),
            message=message,
            auth_token=registration.get("outbound_token"),
        )
        return {"sent": True, "result": result, "error": None}
    except Exception as exc:
        return {"sent": False, "result": None, "error": str(exc)}


def _notify_technicians(
    *,
    settings: Settings,
    store: SQLiteChatStore,
    registration: dict[str, Any],
) -> dict[str, Any]:
    targets = [
        target.strip()
        for target in settings.technician_whatsapp_numbers.split(",")
        if target.strip()
    ]
    if not targets:
        store.update_installation_task_notification(
            registration_id=int(registration["id"]),
            notification_status="not_configured",
        )
        return {"sent": False, "targets": [], "error": "TECHNICIAN_WHATSAPP_NUMBERS is not configured."}

    message = (
        "Ada customer baru status PAID dan siap pemasangan.\n"
        f"ID: {registration.get('customer_code') or '-'}\n"
        f"Nama: {registration.get('name') or '-'}\n"
        f"WA: {registration.get('phone') or registration.get('sender_number') or '-'}\n"
        f"Alamat: {registration.get('address') or '-'}\n"
        f"Maps: {registration.get('maps_link') or '-'}"
    )
    errors = []
    for target in targets:
        try:
            FonnteClient(settings).send_message(target_number=target, message=message)
        except Exception as exc:
            errors.append(f"{target}: {exc}")
    status_text = "sent" if not errors else "failed"
    store.update_installation_task_notification(
        registration_id=int(registration["id"]),
        notification_status=status_text,
        technician_contact=", ".join(targets),
    )
    return {"sent": not errors, "targets": targets, "error": "; ".join(errors) or None}


def _registered_notice(registration: dict[str, Any]) -> str:
    return (
        "Terima kasih, data pendaftaran Kakak sudah kami terima. "
        "Proses pengecekan dan verifikasi membutuhkan waktu maksimal 1x24 jam.\n\n"
        f"Link halaman pembayaran: {registration['payment_url']}"
    )


def _approved_notice(registration: dict[str, Any]) -> str:
    payments = registration.get("payments") or []
    amount = payments[0].get("amount") if payments else 0
    amount_text = f"Rp {int(amount or 0):,}".replace(",", ".")
    return (
        "Pendaftaran Kakak sudah approved untuk proses pemasangan.\n\n"
        f"ID pelanggan: {registration.get('customer_code') or '-'}\n"
        f"Nama: {registration.get('name') or '-'}\n"
        f"No WA: {registration.get('phone') or '-'}\n"
        f"Alamat: {registration.get('address') or '-'}\n"
        f"Virtual account: {registration.get('virtual_account') or '-'}\n"
        f"Nominal awal: {amount_text}\n\n"
        "Pembayaran bisa lewat virtual account, transfer bank dengan upload bukti di halaman pembayaran, "
        "atau cash ke kantor sesuai arahan admin."
    )


def _paid_notice(registration: dict[str, Any]) -> str:
    return (
        "Pembayaran sudah kami terima. Status pelanggan berubah menjadi PAID dan tim teknisi akan diproses "
        "untuk pemasangan internet."
    )


def _active_notice(registration: dict[str, Any]) -> str:
    return "Pemasangan internet sudah selesai. Status pelanggan Kakak sekarang ACTIVE. Terima kasih."


def _validate_payment_webhook_secret(provided_secret: str | None, settings: Settings) -> None:
    if settings.payment_webhook_secret and provided_secret != settings.payment_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid payment webhook secret.",
        )


@registration_router.get("/public/{token}")
def get_public_registration(token: str) -> dict[str, Any]:
    try:
        item = _store().get_customer_registration_by_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"item": item}


@registration_router.post("/public/{token}")
def submit_public_registration(
    token: str,
    payload: PublicRegistrationSubmitRequest,
) -> dict[str, Any]:
    store = _store()
    settings = _settings()
    try:
        item = store.submit_customer_registration(
            token=token,
            name=payload.name,
            phone=payload.phone,
            email=payload.email,
            address=payload.address,
            maps_link=payload.maps_link,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    notification = _send_customer_message(
        settings=settings,
        registration=item,
        message=_registered_notice(item),
    )
    return {"item": item, "notification": notification}


@registration_router.get("/public/{token}/payment")
def get_public_payment(token: str) -> dict[str, Any]:
    try:
        item = _store().get_customer_registration_by_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"item": item}


@registration_router.post("/public/{token}/payment-proof")
async def upload_public_payment_proof(token: str, request: Request) -> dict[str, Any]:
    body = await request.body()
    if len(body) > 8 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Payment proof upload is too large. Max size is 8 MB.",
        )
    fields, files = _parse_multipart_form(
        content_type=request.headers.get("content-type", ""),
        body=body,
    )
    upload = files.get("proof_file")
    if not upload:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Upload field `proof_file` is required.",
        )
    if upload.content_type not in {"image/jpeg", "image/png", "image/webp", "application/pdf"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Payment proof must be a JPG, PNG, WEBP, or PDF file.",
        )

    settings = _settings()
    upload_dir = Path(settings.payment_proof_upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    filename = f"{token}-{timestamp}-{secrets.token_hex(4)}-{_safe_filename(upload.filename)}"
    proof_path = upload_dir / filename
    proof_path.write_bytes(upload.data)
    try:
        item = _store().save_payment_proof(
            token=token,
            amount=_parse_optional_int(fields.get("amount")),
            reference_number=fields.get("reference_number"),
            proof_file_path=str(proof_path),
            proof_file_name=upload.filename,
            proof_content_type=upload.content_type,
            notes=fields.get("notes"),
        )
    except ValueError as exc:
        proof_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {"item": item}


@registration_router.get("/admin/items", dependencies=[Depends(_require_dashboard_auth)])
def list_admin_registrations(
    status_filter: str = Query(default="registered", alias="status"),
    limit: int = Query(default=100, ge=1, le=200),
) -> dict[str, Any]:
    try:
        items = _store().list_customer_registrations(
            status_filter=status_filter,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {"items": items}


@registration_router.post(
    "/admin/{registration_id}/approve",
    dependencies=[Depends(_require_dashboard_auth)],
)
def approve_registration(
    registration_id: int,
    payload: RegistrationApproveRequest,
) -> dict[str, Any]:
    store = _store()
    settings = _settings()
    try:
        item = store.approve_customer_registration(
            registration_id=registration_id,
            amount=payload.amount,
            payment_method=payload.payment_method,
            virtual_account=payload.virtual_account,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    notification = _send_customer_message(
        settings=settings,
        registration=item,
        message=_approved_notice(item),
    )
    return {"item": item, "notification": notification}


@registration_router.post(
    "/admin/{registration_id}/payment",
    dependencies=[Depends(_require_dashboard_auth)],
)
def record_admin_payment(
    registration_id: int,
    payload: RegistrationPaymentRequest,
) -> dict[str, Any]:
    store = _store()
    settings = _settings()
    try:
        item = store.record_registration_payment(
            registration_id=registration_id,
            payment_method=payload.payment_method,
            amount=payload.amount,
            reference_number=payload.reference_number,
            virtual_account=payload.virtual_account,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
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


@registration_router.post(
    "/admin/{registration_id}/activate",
    dependencies=[Depends(_require_dashboard_auth)],
)
def activate_registration(
    registration_id: int,
    payload: InstallationCompleteRequest,
) -> dict[str, Any]:
    store = _store()
    settings = _settings()
    try:
        item = store.complete_customer_installation(
            registration_id=registration_id,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    notification = _send_customer_message(
        settings=settings,
        registration=item,
        message=_active_notice(item),
    )
    return {"item": item, "notification": notification}


@registration_router.post("/virtual-account/callback")
def virtual_account_callback(
    payload: VirtualAccountCallbackRequest,
    secret: str | None = Query(default=None),
) -> dict[str, Any]:
    settings = _settings()
    _validate_payment_webhook_secret(secret, settings)
    store = _store()
    try:
        item = store.record_registration_payment(
            registration_id=payload.registration_id,
            payment_method="virtual_account",
            amount=payload.amount,
            reference_number=payload.reference_number,
            virtual_account=payload.virtual_account,
            provider_payload=payload.provider_payload,
            notes="Verified by virtual account callback.",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
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
        "status": "ok",
        "item": item,
        "customer_notification": customer_notification,
        "technician_notification": technician_notification,
    }


@registration_router.get("/admin/message-dumps", dependencies=[Depends(_require_dashboard_auth)])
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


@registration_router.post(
    "/admin/message-dumps/{dump_id}",
    dependencies=[Depends(_require_dashboard_auth)],
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
