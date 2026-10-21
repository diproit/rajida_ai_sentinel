import hmac
import logging
from typing import Optional
from fastapi import Header, HTTPException, status

from app.core.config import get_settings

logger = logging.getLogger("api.deps")
settings = get_settings()


async def verify_webhook_auth(
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> bool:
    """Validate incoming DigiValuer webhook static Bearer token against configured secret."""
    expected_secret = settings.DIGIVALUER_WEBHOOK_SECRET

    if not authorization:
        logger.warning("Rejected webhook: Missing Authorization header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        logger.warning("Rejected webhook: Invalid Authorization header format")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Expected 'Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    provided_token = parts[1]
    # Constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(provided_token.encode("utf-8"), expected_secret.encode("utf-8")):
        logger.warning("Rejected webhook: Unauthorized Bearer token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook authorization token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return True
