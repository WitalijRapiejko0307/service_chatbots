"""Telegram webhook API endpoints."""

import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.auth import require_admin
from app.dependencies import CommonDependencies
from app.services.channel_binding_service import ChannelBindingService
from app.services.telegram_service import TelegramService
from app.storage.resolver import get_secrets_manager
from app.utils.enum_helpers import get_enum_value

logger = logging.getLogger(__name__)

router = APIRouter()


def get_telegram_service(
    deps: CommonDependencies = Depends(),
) -> TelegramService:
    from app.config import get_settings

    settings = get_settings()
    secrets_manager = get_secrets_manager()
    binding_service = ChannelBindingService(deps.db, secrets_manager)
    return TelegramService(binding_service, deps.db, settings)


@router.post("/telegram/webhook/{binding_id}")
async def handle_webhook(
    binding_id: str,
    request: Request,
    telegram_service: TelegramService = Depends(get_telegram_service),
):
    """Handle Telegram webhook events. Always 200 after parse so Telegram does not retry forever."""
    try:
        UUID(binding_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid binding ID format",
        )

    try:
        body = await request.body()
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as e:
        logger.error("Failed to parse Telegram webhook payload: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    logger.info(
        "Telegram webhook event received",
        extra={"binding_id": binding_id, "payload_keys": list(payload.keys())},
    )

    try:
        from app.services.webhook_event_store import add_webhook_event

        add_webhook_event("telegram_webhook", payload)
    except Exception as e:
        logger.debug("Failed to store webhook event: %s", e)

    try:
        await telegram_service.handle_webhook_event(payload, binding_id)
    except Exception as e:
        logger.error("Error handling Telegram webhook event: %s", e, exc_info=True)
        return {"status": "error", "message": "Event processing failed"}

    return {"status": "ok"}


@router.post("/telegram/webhook/{binding_id}/set")
async def set_webhook(
    binding_id: str,
    deps: CommonDependencies = Depends(),
    telegram_service: TelegramService = Depends(get_telegram_service),
    _admin: str = require_admin(),
):
    try:
        UUID(binding_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid binding ID format",
        )

    secrets_manager = get_secrets_manager()
    binding_service = ChannelBindingService(deps.db, secrets_manager)
    binding = await binding_service.get_binding(binding_id)
    if not binding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Binding {binding_id} not found",
        )
    if get_enum_value(binding.channel_type) != "telegram":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Binding {binding_id} is not a Telegram binding",
        )

    from app.config import get_settings

    settings = get_settings()
    base_url = settings.app_url.rstrip("/") if settings.app_url else ""
    webhook_url = f"{base_url}/api/v1/telegram/webhook/{binding_id}"
    success = await telegram_service.set_webhook(binding_id, webhook_url)
    if success:
        return {
            "status": "ok",
            "message": "Webhook set successfully",
            "webhook_url": webhook_url,
        }
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Failed to set webhook. Check logs for details.",
    )


@router.get("/telegram/webhook/{binding_id}/status")
async def get_webhook_status(
    binding_id: str,
    deps: CommonDependencies = Depends(),
    telegram_service: TelegramService = Depends(get_telegram_service),
    _admin: str = require_admin(),
):
    try:
        UUID(binding_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid binding ID format",
        )

    secrets_manager = get_secrets_manager()
    binding_service = ChannelBindingService(deps.db, secrets_manager)
    binding = await binding_service.get_binding(binding_id)
    if not binding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Binding {binding_id} not found",
        )
    if get_enum_value(binding.channel_type) != "telegram":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Binding {binding_id} is not a Telegram binding",
        )

    import httpx

    bot_token = await binding_service.get_access_token(binding_id)
    url = f"{telegram_service.TELEGRAM_API_BASE_URL}{bot_token}/getWebhookInfo"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to get webhook info",
                )
            result = response.json()
            if result.get("ok"):
                webhook_info = result.get("result", {})
                from app.config import get_settings as _get_settings

                _s = _get_settings()
                _base = _s.app_url.rstrip("/") if _s.app_url else ""
                return {
                    "status": "ok",
                    "webhook_info": webhook_info,
                    "expected_url": f"{_base}/api/v1/telegram/webhook/{binding_id}",
                }
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Telegram API error: {result.get('description', 'Unknown error')}",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting webhook status: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get webhook status: {str(e)}",
        )
