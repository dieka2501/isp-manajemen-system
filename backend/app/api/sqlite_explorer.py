from __future__ import annotations

from dataclasses import dataclass
from email.parser import BytesParser
from email.policy import default

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.auth.guards import provider_guard
from app.core.config import get_settings
from app.provider_dashboard.permissions import ProviderPermission
from app.services.billing_import import load_billing_rows_from_bytes
from app.services.chat_store import SQLiteChatStore
from app.services.sqlite_explorer import SQLiteExplorerService

sqlite_explorer_router = APIRouter(tags=["provider-sqlite-explorer"])


class SQLiteQueryRequest(BaseModel):
    path: str | None = None
    sql: str = Field(min_length=1)
    limit: int = Field(default=250, ge=1, le=1000)


@dataclass(frozen=True)
class UploadedPart:
    filename: str
    content_type: str
    data: bytes


def _service() -> SQLiteExplorerService:
    return SQLiteExplorerService(get_settings())


def _chat_store() -> SQLiteChatStore:
    return SQLiteChatStore(get_settings())


def _parse_optional_int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
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
            detail="Use multipart/form-data with a billing_file upload.",
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


@sqlite_explorer_router.get(
    "/sources",
    dependencies=[Depends(provider_guard(ProviderPermission.SQLITE_MANAGE))],
)
def list_sources() -> dict[str, object]:
    items = _service().list_sources()
    default_source = items[0].as_dict() if items else None
    return {
        "default_source": default_source,
        "items": [item.as_dict() for item in items],
    }


@sqlite_explorer_router.get(
    "/billing-import/scopes",
    dependencies=[Depends(provider_guard(ProviderPermission.BILLING_MANAGE))],
)
def list_billing_import_scopes() -> dict[str, object]:
    return {"items": _chat_store().billing_import_scopes()}


@sqlite_explorer_router.post(
    "/billing-import",
    dependencies=[Depends(provider_guard(ProviderPermission.BILLING_MANAGE))],
)
async def import_billing_workbook(request: Request) -> dict[str, object]:
    body = await request.body()
    if len(body) > 15 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Billing workbook upload is too large. Max size is 15 MB.",
        )
    fields, files = _parse_multipart_form(
        content_type=request.headers.get("content-type", ""),
        body=body,
    )
    upload = files.get("billing_file")
    if not upload:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Upload field `billing_file` is required.",
        )
    if not upload.filename.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Billing import only accepts .xlsx files.",
        )

    try:
        rows = load_billing_rows_from_bytes(upload.data)
        if not rows:
            raise ValueError("Workbook does not contain billing rows.")
        summary = _chat_store().import_billing_rows(
            rows=rows,
            client_id=_parse_optional_int(fields.get("client_id")),
            device_id=_parse_optional_int(fields.get("device_id")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {
        "filename": upload.filename,
        "item": summary,
    }


@sqlite_explorer_router.get(
    "/tables",
    dependencies=[Depends(provider_guard(ProviderPermission.SQLITE_MANAGE))],
)
def list_tables(path: str | None = Query(default=None)) -> dict[str, object]:
    try:
        source = _service().get_source(path)
        items = _service().list_tables(source.path)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {
        "source": source.as_dict(),
        "tables": items,
    }


@sqlite_explorer_router.post(
    "/query",
    dependencies=[Depends(provider_guard(ProviderPermission.SQLITE_MANAGE))],
)
def run_query(payload: SQLiteQueryRequest) -> dict[str, object]:
    try:
        source = _service().get_source(payload.path)
        result = _service().run_query(source.path, payload.sql, limit=payload.limit)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {
        "source": source.as_dict(),
        **result,
    }


@sqlite_explorer_router.get("/tables/{table_name}")
def preview_table(
    table_name: str,
    path: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    _: object = Depends(provider_guard(ProviderPermission.SQLITE_MANAGE)),
) -> dict[str, object]:
    try:
        source = _service().get_source(path)
        result = _service().preview_table(source.path, table_name, limit=limit)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {
        "source": source.as_dict(),
        "table_name": table_name,
        **result,
    }
