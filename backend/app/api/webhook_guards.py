"""Shared guards for inbound messenger webhooks."""

import logging

from fastapi import HTTPException, status

from app.config import get_settings

logger = logging.getLogger(__name__)


def enforce_or_warn_missing_webhook_secret(channel: str, binding_id: str | None = None) -> None:
    """Reject unsigned webhooks in production; warn in other environments."""
    settings = get_settings()
    if settings.environment.lower() == "production":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Webhook signature verification not configured",
        )
    logger.warning(
        "webhook accepted without signature verification — %s%s",
        channel,
        f", binding {binding_id}" if binding_id else "",
    )
