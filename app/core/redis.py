from typing import Optional
import redis.asyncio as aioredis
from app.core.config import get_settings

settings = get_settings()

_redis_client: Optional[aioredis.Redis] = None


def get_redis_client() -> aioredis.Redis:
    """Get or create singleton async Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def close_redis_client() -> None:
    """Close the active Redis client connection."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None


async def check_redis_connection() -> bool:
    """Check if the Redis connection is healthy."""
    try:
        client = get_redis_client()
        return bool(await client.ping())
    except Exception:
        return False


async def broadcast_sentinel_event(event_type: str, data: dict) -> None:
    """Broadcast real-time Sentinel event to Redis pub/sub channel for live UI updates."""
    import json
    import logging
    from datetime import datetime, timezone

    logger = logging.getLogger("core.redis")
    try:
        client = get_redis_client()
        message = json.dumps({
            "type": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        await client.publish("sentinel:events", message)
    except Exception as exc:
        logger.debug("Failed to broadcast event to Redis: %s", exc)
