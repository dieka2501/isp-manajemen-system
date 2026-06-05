from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import get_settings
from app.services.chat_store import SQLiteChatStore

settings = get_settings()
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    SQLiteChatStore(settings).initialize()
    yield


app = FastAPI(
    title=settings.app_name,
    debug=settings.app_debug,
    lifespan=lifespan,
)


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "environment": settings.app_env,
    }


app.include_router(api_router, prefix=settings.api_v1_prefix)
