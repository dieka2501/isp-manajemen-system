from fastapi import APIRouter
from app.api.registrations import public_registration_router
from app.api.webhooks import webhooks_router
from app.client_dashboard.api import client_api_router, legacy_client_api_router
from app.provider_dashboard.api import provider_api_router

api_router = APIRouter()


@api_router.get("", tags=["root"])
def api_root() -> dict[str, str]:
    return {
        "message": "ISP Manajemen Backend API is running",
    }


api_router.include_router(webhooks_router)
api_router.include_router(public_registration_router, prefix="/registrations")
api_router.include_router(provider_api_router)
api_router.include_router(client_api_router)
api_router.include_router(legacy_client_api_router)
