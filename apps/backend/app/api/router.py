from fastapi import APIRouter
from app.api.webhooks import webhooks_router

api_router = APIRouter()


@api_router.get("", tags=["root"])
def api_root() -> dict[str, str]:
    return {
        "message": "ISP Manajemen Backend API is running",
    }


api_router.include_router(webhooks_router)
