from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse, RedirectResponse

from app.auth.guards import dashboard_destination

auth_page_router = APIRouter(include_in_schema=False)
FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"


def _frontend_file(filename: str) -> FileResponse:
    path = FRONTEND_DIR / filename
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Frontend file `{filename}` is not available.",
        )
    return FileResponse(path)


@auth_page_router.get("/")
def root_redirect(request: Request) -> RedirectResponse:
    return RedirectResponse(dashboard_destination(request), status_code=status.HTTP_303_SEE_OTHER)


@auth_page_router.get("/login")
def login_selector() -> FileResponse:
    return _frontend_file("login.html")


@auth_page_router.get("/login/provider")
def provider_login() -> FileResponse:
    return _frontend_file("sqlexplorer.html")


@auth_page_router.get("/login/client")
def client_login() -> FileResponse:
    return _frontend_file("index.html")


@auth_page_router.get("/unauthorized")
def unauthorized() -> FileResponse:
    return _frontend_file("unauthorized.html")
