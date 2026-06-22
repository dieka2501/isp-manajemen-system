from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse, RedirectResponse

from app.auth.guards import require_client
from app.client_dashboard.permissions import ClientPermission
from app.core.config import get_settings
from app.services.chat_store import SQLiteChatStore

client_page_router = APIRouter(include_in_schema=False)
FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"


def _client_page(request: Request) -> FileResponse | RedirectResponse:
    try:
        session = require_client(
            request,
            permission=ClientPermission.DASHBOARD_ACCESS,
        )
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            return RedirectResponse("/login/client", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse("/unauthorized", status_code=status.HTTP_303_SEE_OTHER)

    client = SQLiteChatStore(get_settings()).get_client_profile(session.client_id)
    if not client or not int(client.get("is_active") or 0):
        return RedirectResponse("/login/client", status_code=status.HTTP_303_SEE_OTHER)

    page = FRONTEND_DIR / "index.html"
    if not page.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client dashboard frontend is not available.",
        )
    return FileResponse(page)


@client_page_router.get("/client-dashboard")
@client_page_router.get("/client-dashboard/")
@client_page_router.get("/client-dashboard/{dashboard_path:path}")
def client_dashboard(request: Request, dashboard_path: str = ""):
    return _client_page(request)


@client_page_router.get("/dashboard")
@client_page_router.get("/dashboard/")
def legacy_client_dashboard() -> RedirectResponse:
    return RedirectResponse("/client-dashboard", status_code=status.HTTP_308_PERMANENT_REDIRECT)


@client_page_router.get("/dashboard/{dashboard_path:path}")
def legacy_client_dashboard_path(dashboard_path: str) -> RedirectResponse:
    suffix = f"/{dashboard_path}" if dashboard_path else ""
    return RedirectResponse(
        f"/client-dashboard{suffix}",
        status_code=status.HTTP_308_PERMANENT_REDIRECT,
    )
