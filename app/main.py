import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router
from app.core.config import get_settings
from app.core.database import check_database_connection, init_db
from app.core.redis import check_redis_connection, close_redis_client

logger = logging.getLogger("uvicorn.info")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan for startup and shutdown event handling."""
    logger.info("Starting up %s...", settings.APP_NAME)
    # Attempt to initialize DB if available
    try:
        if await check_database_connection():
            await init_db()
            logger.info("Database tables initialized successfully.")
        else:
            logger.warning("Database not reachable during startup. Tables not initialized.")
    except Exception as exc:
        logger.warning("Database initialization check skipped/failed: %s", exc)

    yield

    logger.info("Shutting down %s...", settings.APP_NAME)
    await close_redis_client()


app = FastAPI(
    title=settings.APP_NAME,
    description="AI/ML Agentic Workflow Service for DigiValuer Workflow Bottlenecks",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["Root"])
async def root() -> dict:
    """Root metadata endpoint."""
    return {
        "service": settings.APP_NAME,
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health", status_code=status.HTTP_200_OK, tags=["Health"])
async def health_check() -> dict:
    """Top-level health check endpoint."""
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


# Include API v1 router
app.include_router(api_router, prefix=settings.API_V1_STR)

# Include Dashboard router
from app.routers.dashboard import router as dashboard_router
app.include_router(dashboard_router)

# Mount Frontend static dashboard if built
import os
from fastapi.staticfiles import StaticFiles

frontend_dist = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")
if os.path.exists(frontend_dist):
    frontend_dist_assets = os.path.join(frontend_dist, "assets")
    if os.path.exists(frontend_dist_assets):
        app.mount("/assets", StaticFiles(directory=frontend_dist_assets), name="static_root_assets")
    app.mount("/dashboard", StaticFiles(directory=frontend_dist, html=True), name="dashboard")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.DEBUG,
    )
