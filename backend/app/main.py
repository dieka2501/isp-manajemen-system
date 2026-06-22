from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from app.api.router import api_router
from app.auth.routes import auth_page_router
from app.client_dashboard.routes import client_page_router
from app.core.config import get_settings
from app.provider_dashboard.routes import provider_page_router
from app.services.chat_store import SQLiteChatStore

settings = get_settings()
logging.basicConfig(level=logging.INFO)
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


class DashboardStaticFiles(StaticFiles):
    def __init__(
        self,
        *,
        directory: Path,
        allowed_files: set[str],
        allowed_directories: set[str] | None = None,
    ) -> None:
        super().__init__(directory=directory)
        self.allowed_files = allowed_files
        self.allowed_directories = allowed_directories or set()

    async def get_response(self, path: str, scope: dict[str, object]) -> Response:
        normalized = path.lstrip("/")
        top_level = normalized.split("/", 1)[0]
        if Path(normalized).suffix.lower() in {".htm", ".html"}:
            return Response(status_code=status.HTTP_404_NOT_FOUND)
        if normalized not in self.allowed_files and top_level not in self.allowed_directories:
            return Response(status_code=status.HTTP_404_NOT_FOUND)
        return await super().get_response(path, scope)


@asynccontextmanager
async def lifespan(_: FastAPI):
    SQLiteChatStore(settings).initialize()
    yield


app = FastAPI(
    title=settings.app_name,
    debug=settings.app_debug,
    lifespan=lifespan,
)

if FRONTEND_DIR.exists():
    app.mount(
        "/provider-dashboard-assets",
        DashboardStaticFiles(
            directory=FRONTEND_DIR,
            allowed_files={"sqlexplorer.css", "sqlexplorer.js"},
            allowed_directories={"provider-dashboard"},
        ),
        name="provider-dashboard-assets",
    )
    app.mount(
        "/client-dashboard-assets",
        DashboardStaticFiles(
            directory=FRONTEND_DIR,
            allowed_files={"app.js", "styles.css"},
            allowed_directories={"client-dashboard"},
        ),
        name="client-dashboard-assets",
    )
    app.mount(
        "/sqlexplorer-assets",
        DashboardStaticFiles(
            directory=FRONTEND_DIR,
            allowed_files={"sqlexplorer.css", "sqlexplorer.js"},
            allowed_directories={"provider-dashboard"},
        ),
        name="sqlexplorer-assets",
    )
    app.mount(
        "/dashboard-assets",
        DashboardStaticFiles(
            directory=FRONTEND_DIR,
            allowed_files={"app.js", "styles.css"},
            allowed_directories={"client-dashboard"},
        ),
        name="dashboard-assets",
    )
    app.mount(
        "/registration-assets",
        DashboardStaticFiles(
            directory=FRONTEND_DIR,
            allowed_files={"registration.css", "registration.js", "payment.js"},
        ),
        name="registration-assets",
    )


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "environment": settings.app_env,
        "version": settings.app_version,
        "build_commit": settings.app_build_commit,
        "build_commit_short": settings.app_build_commit[:8],
        "build_branch": settings.app_build_branch,
    }


@app.get("/register/{token}", include_in_schema=False)
def registration_form(token: str) -> FileResponse:
    index_file = FRONTEND_DIR / "registration.html"
    if not index_file.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registration frontend is not available.",
        )
    return FileResponse(index_file)


@app.get("/payment/{token}", include_in_schema=False)
def payment_form(token: str) -> FileResponse:
    index_file = FRONTEND_DIR / "payment.html"
    if not index_file.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment frontend is not available.",
        )
    return FileResponse(index_file)


app.include_router(auth_page_router)
app.include_router(provider_page_router)
app.include_router(client_page_router)
app.include_router(api_router, prefix=settings.api_v1_prefix)
