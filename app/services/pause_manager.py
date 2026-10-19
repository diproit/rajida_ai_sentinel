import logging
from typing import Set
from app.core.redis import get_redis_client

logger = logging.getLogger("services.pause_manager")
REDIS_PAUSED_SET_KEY = "sentinel:paused_cases"
_in_memory_paused_cases: Set[str] = set()


async def is_case_paused(case_id: str) -> bool:
    """Check if monitoring is paused for a specific case."""
    try:
        redis = get_redis_client()
        return bool(await redis.sismember(REDIS_PAUSED_SET_KEY, case_id))
    except Exception as exc:
        logger.debug("Redis unavailable for pause check, using memory fallback: %s", exc)
        return case_id in _in_memory_paused_cases


async def toggle_case_pause(case_id: str) -> bool:
    """Toggle monitoring pause state for a case.

    Returns:
        True if the case is now paused, False if unpaused.
    """
    currently_paused = await is_case_paused(case_id)
    new_state = not currently_paused

    try:
        redis = get_redis_client()
        if new_state:
            await redis.sadd(REDIS_PAUSED_SET_KEY, case_id)
        else:
            await redis.srem(REDIS_PAUSED_SET_KEY, case_id)
    except Exception as exc:
        logger.debug("Redis unavailable for pause toggle, using memory fallback: %s", exc)

    if new_state:
        _in_memory_paused_cases.add(case_id)
    else:
        _in_memory_paused_cases.discard(case_id)

    logger.info("Case %s monitoring pause state toggled to: %s", case_id, new_state)
    return new_state


async def get_all_paused_cases() -> Set[str]:
    """Retrieve all case IDs currently paused from agent monitoring."""
    try:
        redis = get_redis_client()
        members = await redis.smembers(REDIS_PAUSED_SET_KEY)
        return set(members)
    except Exception as exc:
        logger.debug("Redis unavailable for paused set, using memory fallback: %s", exc)
        return set(_in_memory_paused_cases)
