import logging
from typing import Any
from fastapi import APIRouter, Depends, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import verify_webhook_auth
from app.core.redis import get_redis_client
from app.db.session import get_async_session
from app.schemas.webhook import DigiValuerWebhookPayload, WebhookResponse
from app.services.webhook_processor import process_webhook_payload
from app.workers.celery_app import process_digivaluer_webhook_event

logger = logging.getLogger("api.webhooks")
router = APIRouter()


@router.post(
    "/digivaluer",
    response_model=WebhookResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Receive DigiValuer platform webhooks",
    description="Endpoint for receiving real-time case events (STATUS_CHANGED, UNRESPONSIVE_PARTY, SLA_DELAY_WARNING) from DigiValuer (mekamu_mowheel).",
)
async def receive_digivaluer_webhook(
    payload: DigiValuerWebhookPayload,
    authenticated: bool = Depends(verify_webhook_auth),
    session: AsyncSession = Depends(get_async_session),
) -> Any:
    """Receive, deduplicate (via Redis SETNX), and enqueue DigiValuer webhook events."""
    event_id = payload.event_id
    dedup_key = f"sentinel:webhook:event:{event_id}"

    # 1. Idempotency Check with 48h TTL
    try:
        redis_client = get_redis_client()
        is_new = await redis_client.set(dedup_key, "received", ex=172800, nx=True)
        if not is_new:
            logger.info("Idempotent duplicate webhook skipped: event_id=%s", event_id)
            return WebhookResponse(
                status="duplicate",
                event_id=event_id,
                message="Duplicate event detected. Already processed (idempotent skip).",
                action_taken="skipped",
            )
    except Exception as redis_exc:
        logger.debug("Redis deduplication check skipped (Redis unavailable: %s)", redis_exc)

    # 2. Dispatch to Celery Queue with resilient inline fallback
    task_id = None
    action_taken = "enqueued"

    try:
        # Enqueue Celery task with JSON-serialized payload
        payload_dict = payload.model_dump(mode="json")
        task = process_digivaluer_webhook_event.delay(payload_dict)
        task_id = str(task.id)
        logger.info("Enqueued webhook event %s to Celery task %s", event_id, task_id)
    except Exception as celery_exc:
        logger.info("Celery unavailable (%s). Processing webhook event %s inline.", celery_exc, event_id)
        # Resilient fallback: process directly using existing DB session
        result = await process_webhook_payload(payload, session)
        action_taken = result.get("action", "processed_inline")

    return WebhookResponse(
        status="accepted",
        event_id=event_id,
        message="DigiValuer webhook accepted for processing.",
        task_id=task_id,
        action_taken=action_taken,
    )
