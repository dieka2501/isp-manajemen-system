from fastapi import APIRouter

from app.api.client_dashboard import client_dashboard_router

client_api_router = APIRouter(prefix="/client")
client_api_router.include_router(client_dashboard_router)

legacy_client_api_router = APIRouter(prefix="/client-dashboard")
legacy_client_api_router.include_router(client_dashboard_router, deprecated=True)
