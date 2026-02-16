import hmac
import logging
from fastapi import Header, HTTPException, status
from app.core.config import settings

logger = logging.getLogger(__name__)


async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")):
    """
    Verify the API key from the X-API-Key header.
    Used for service-to-service authentication from Meahana Backend.
    """
    if not hmac.compare_digest(x_api_key, settings.meahana_api_key):
        logger.warning("Invalid API key received")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
