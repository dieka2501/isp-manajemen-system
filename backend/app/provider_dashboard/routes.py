from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse, RedirectResponse

from app.auth.guards import require_provider
from app.provider_dashboard.permissions import ProviderPermission

provider_page_router = APIRouter(include_in_schema=False)
FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"


def _provider_page(request: Request) -> FileResponse | RedirectResponse:
    try:
        require_provider(request, ProviderPermission.DASHBOARD_ACCESS)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            return RedirectResponse("/login/provider", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse("/unauthorized", status_code=status.HTTP_303_SEE_OTHER)

    page = FRONTEND_DIR / "sqlexplorer.html"
    if not page.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider dashboard frontend is not available.",
        )
    return FileResponse(page)


@provider_page_router.get("/sqlexplore")
@provider_page_router.get("/sqlexplore/")
@provider_page_router.get("/sqlexplore/{dashboard_path:path}")
def provider_dashboard(request: Request, dashboard_path: str = ""):
    return _provider_page(request)


@provider_page_router.get("/sqlexplorer")
@provider_page_router.get("/sqlexplorer/")
def legacy_provider_dashboard() -> RedirectResponse:
    return RedirectResponse("/sqlexplore", status_code=status.HTTP_308_PERMANENT_REDIRECT)


@provider_page_router.get("/sqlexplorer/{dashboard_path:path}")
def legacy_provider_dashboard_path(dashboard_path: str) -> RedirectResponse:
    suffix = f"/{dashboard_path}" if dashboard_path else ""
    return RedirectResponse(
        f"/sqlexplore{suffix}",
        status_code=status.HTTP_308_PERMANENT_REDIRECT,
    )
