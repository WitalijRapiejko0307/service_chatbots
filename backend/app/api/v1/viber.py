"""Viber webhook API endpoints."""

import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.auth import require_admin
from app.dependencies import CommonDependencies
from app.services.channel_binding_service import ChannelBindingService
from app.services.viber_service import ViberService, verify_viber_signature
from app.storage.resolver import get_secrets_manager
from app.utils.enum_helpers import get_enum_value

logger = logging.getLogger(__name__)

router = APIRouter()


def get_viber_service(
    deps: CommonDependencies = Depends(),
) -> ViberService:
    from app.config import get_settings

    settings = get_settings()
    secrets_manager = get_secrets_manager()
    binding_service = ChannelBindingService(deps.db, secrets_manager)
    return ViberService(binding_service, deps.db, settings)


@router.post("/viber/webhook/{binding_id}")
async def handle_webhook(
    binding_id: str,
    request: Request,
    viber_service: ViberService = Depends(get_viber_service),
    deps: CommonDependencies = Depends(),
):
    try:
        UUID(binding_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid binding ID format",
        )

    body = await request.body()
    signature = request.headers.get("X-Viber-Content-Signature") or request.headers.get(
        "x-viber-content-signature", ""
    )

    secrets_manager = get_secrets_manager()
    binding_service = ChannelBindingService(deps.db, secrets_manager)
    try:
        token = await binding_service.get_access_token(binding_id)
    except Exception:
        token = None

    if token:
        if not signature or not verify_viber_signature(body, signature, token):
            logger.warning("Viber webhook signature rejected for binding %s", binding_id)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid webhook signature",
            )

    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except json.JSONDecodeError as e:
        logger.error("Failed to parse Viber webhook payload: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    # Viber sends a handshake POST when set_webhook is called.
    if payload.get("event") == "webhook":
        return {"status": "ok"}

    try:
        from app.services.webhook_event_store import add_webhook_event

        add_webhook_event("viber_webhook", payload)
    except Exception as e:
        logger.debug("Failed to store webhook event: %s", e)

    try:
        await viber_service.handle_webhook_event(payload, binding_id)
    except Exception as e:
        logger.error("Error handling Viber webhook event: %s", e, exc_info=True)
        return {"status": "error", "message": "Event processing failed"}

    return {"status": "ok"}


@router.post("/viber/webhook/{binding_id}/set")
async def set_webhook(
    binding_id: str,
    deps: CommonDependencies = Depends(),
    viber_service: ViberService = Depends(get_viber_service),
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Binding not found")
    if get_enum_value(binding.channel_type) != "viber":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Binding is not a Viber binding",
        )

    from app.config import get_settings

    settings = get_settings()
    base_url = settings.app_url.rstrip("/") if settings.app_url else ""
    webhook_url = f"{base_url}/api/v1/viber/webhook/{binding_id}"
    success = await viber_service.set_webhook(binding_id, webhook_url)
    if success:
        metadata = dict(binding.metadata or {})
        metadata["webhook_url"] = webhook_url
        await binding_service.update_binding(binding_id, metadata=metadata)
        return {"status": "ok", "webhook_url": webhook_url}
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Failed to set Viber webhook. APP_URL must be HTTPS in production.",
    )
