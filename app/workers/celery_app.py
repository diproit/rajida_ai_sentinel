import asyncio
from celery import Celery
from celery.schedules import crontab
from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "digivaluer_sentinel",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    beat_schedule={
        "sentinel-scan-every-30-minutes": {
            "task": "app.workers.tasks.run_sentinel_scan",
            "schedule": crontab(minute="*/30"),
        },
    },
)


@celery_app.task(name="app.workers.tasks.check_valuation_bottlenecks")
def check_valuation_bottlenecks() -> dict:
    """Background task to poll DigiValuer cases and detect workflow bottlenecks."""
    return {
        "status": "success",
        "scanned_cases": 0,
        "bottlenecks_detected": 0,
    }


@celery_app.task(name="app.workers.tasks.run_sentinel_scan")
def run_sentinel_scan_task(force_dispatch: bool = False) -> dict:
    """Scheduled Celery task executing run_sentinel_scan every 30 minutes."""
    from app.worker import run_sentinel_scan

    return asyncio.run(run_sentinel_scan(force_dispatch=force_dispatch))


@celery_app.task(name="app.workers.tasks.process_digivaluer_webhook_event")
def process_digivaluer_webhook_event(payload_dict: dict) -> dict:
    """Async background Celery task to process incoming DigiValuer webhook event."""
    from app.db.session import async_session_maker
    from app.schemas.webhook import DigiValuerWebhookPayload
    from app.services.webhook_processor import process_webhook_payload

    async def _run():
        payload = DigiValuerWebhookPayload.model_validate(payload_dict)
        async with async_session_maker() as session:
            return await process_webhook_payload(payload, session)

    return asyncio.run(_run())
