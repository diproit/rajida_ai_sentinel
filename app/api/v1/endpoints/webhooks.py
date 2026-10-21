import logging
from typing import Any
from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import verify_webhook_auth
from app.core.redis import get_redis_client
from app.db.session import async_session_maker, get_async_session
from app.schemas.webhook import DigiValuerWebhookPayload, WebhookResponse
from app.services.webhook_processor import process_webhook_payload

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
    background_tasks: BackgroundTasks,
    authenticated: bool = Depends(verify_webhook_auth),
    session: AsyncSession = Depends(get_async_session),
) -> Any:
    """Receive, deduplicate (via Redis SETNX), and immediately process DigiValuer webhook events."""
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
        logger.debug("Redis deduplication check skipped: %s", redis_exc)

    # 2. Run background processor immediately (guarantees execution and live SSE broadcast)
    async def _run_background(p: DigiValuerWebhookPayload):
        try:
            async with async_session_maker() as new_session:
                await process_webhook_payload(p, new_session)
                logger.info("Webhook event %s processed successfully in background task", p.event_id)
        except Exception as exc:
            logger.error("Failed to process webhook event %s in background: %s", p.event_id, exc, exc_info=True)

    background_tasks.add_task(_run_background, payload)

    return WebhookResponse(
        status="accepted",
        event_id=event_id,
        message="DigiValuer webhook accepted for processing.",
        task_id=f"bg_{event_id[:8]}",
        action_taken="processed",
    )
