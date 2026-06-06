from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.services.dashboard_auth import DashboardAuthService
from app.services.sqlite_explorer import SQLiteExplorerService

sqlite_explorer_router = APIRouter(prefix="/sqlite", tags=["sqlite-explorer"])


class SQLiteQueryRequest(BaseModel):
    path: str | None = None
    sql: str = Field(min_length=1)
    limit: int = Field(default=250, ge=1, le=1000)


class DashboardLoginRequest(BaseModel):
    password: str = Field(min_length=1)


def _service() -> SQLiteExplorerService:
    return SQLiteExplorerService(get_settings())


def _auth_service() -> DashboardAuthService:
    return DashboardAuthService(get_settings())


def _require_dashboard_auth(request: Request) -> None:
    _auth_service().require_auth(request)


@sqlite_explorer_router.get("/auth/status")
def auth_status(request: Request) -> dict[str, object]:
    return _auth_service().status(request).as_dict()


@sqlite_explorer_router.post("/auth/login")
def auth_login(payload: DashboardLoginRequest, response: Response) -> dict[str, object]:
    state = _auth_service().login(payload.password, response)
    return state.as_dict()


@sqlite_explorer_router.post("/auth/logout")
def auth_logout(response: Response) -> dict[str, str]:
    _auth_service().logout(response)
    return {"status": "ok"}


@sqlite_explorer_router.get("/sources", dependencies=[Depends(_require_dashboard_auth)])
def list_sources() -> dict[str, object]:
    items = _service().list_sources()
    default_source = items[0].as_dict() if items else None
    return {
        "default_source": default_source,
        "items": [item.as_dict() for item in items],
    }


@sqlite_explorer_router.get("/tables", dependencies=[Depends(_require_dashboard_auth)])
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


@sqlite_explorer_router.post("/query", dependencies=[Depends(_require_dashboard_auth)])
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
    request: Request,
    table_name: str,
    path: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
) -> dict[str, object]:
    _require_dashboard_auth(request)
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
