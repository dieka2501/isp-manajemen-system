from fastapi import APIRouter
from app.api.chat import chat_router
from app.api.client_dashboard import client_dashboard_router
from app.api.sqlite_explorer import sqlite_explorer_router
from app.api.webhooks import webhooks_router

api_router = APIRouter()


@api_router.get("", tags=["root"])
def api_root() -> dict[str, str]:
    return {
        "message": "ISP Manajemen Backend API is running",
    }


api_router.include_router(webhooks_router)
api_router.include_router(chat_router)
api_router.include_router(client_dashboard_router)
api_router.include_router(sqlite_explorer_router)
