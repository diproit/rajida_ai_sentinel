from fastapi import APIRouter
from app.api.v1.endpoints import health, webhooks, workflows

api_router = APIRouter()
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(workflows.router, prefix="/workflows", tags=["Workflows"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])
