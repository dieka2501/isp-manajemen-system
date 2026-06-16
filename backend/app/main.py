from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import get_settings
from app.services.chat_store import SQLiteChatStore

settings = get_settings()
logging.basicConfig(level=logging.INFO)
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


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
    app.mount("/sqlexplorer-assets", StaticFiles(directory=FRONTEND_DIR), name="sqlexplorer-assets")
    app.mount("/dashboard-assets", StaticFiles(directory=FRONTEND_DIR), name="dashboard-assets")


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "environment": settings.app_env,
    }


@app.get("/", include_in_schema=False)
@app.get("/dashboard", include_in_schema=False)
@app.get("/dashboard/", include_in_schema=False)
@app.get("/client-dashboard", include_in_schema=False)
@app.get("/client-dashboard/", include_in_schema=False)
def dashboard_root() -> FileResponse:
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dashboard frontend is not available.",
        )
    return FileResponse(index_file)


@app.get("/sqlexplorer", include_in_schema=False)
@app.get("/sqlexplorer/", include_in_schema=False)
def dashboard() -> FileResponse:
    index_file = FRONTEND_DIR / "sqlexplorer.html"
    if not index_file.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SQLite explorer frontend is not available.",
        )
    return FileResponse(index_file)


app.include_router(api_router, prefix=settings.api_v1_prefix)
