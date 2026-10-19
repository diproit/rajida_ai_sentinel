from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from app.core.config import get_settings
from app.core.database import check_database_connection
from app.core.redis import check_redis_connection

router = APIRouter()
settings = get_settings()


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> dict:
    """General health check endpoint returning 200 OK."""
    db_healthy = await check_database_connection()
    redis_healthy = await check_redis_connection()

    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "services": {
            "database": "connected" if db_healthy else "disconnected",
            "redis": "connected" if redis_healthy else "disconnected",
        },
    }


@router.get("/health/ready")
async def readiness_check() -> JSONResponse:
    """Readiness probe checking database and redis dependencies."""
    db_ok = await check_database_connection()
    redis_ok = await check_redis_connection()

    all_ready = db_ok and redis_ok
    status_code = status.HTTP_200_OK if all_ready else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if all_ready else "not_ready",
            "database": "ready" if db_ok else "unavailable",
            "redis": "ready" if redis_ok else "unavailable",
        },
    )


@router.get("/health/live", status_code=status.HTTP_200_OK)
async def liveness_check() -> dict:
    """Liveness probe verifying that the application process is running."""
    return {"status": "live"}
