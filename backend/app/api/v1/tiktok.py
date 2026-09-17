"""TikTok webhook and OAuth stub endpoints."""

import json
import logging
from typing import Optional
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.auth import require_admin
from app.config import get_settings
from app.dependencies import CommonDependencies
from app.services.channel_binding_service import ChannelBindingService
from app.services.tiktok_service import TikTokService, verify_tiktok_signature
from app.storage.resolver import get_secrets_manager

logger = logging.getLogger(__name__)

router = APIRouter()


def get_tiktok_service(
    deps: CommonDependencies = Depends(),
) -> TikTokService:
    settings = get_settings()
    secrets_manager = get_secrets_manager()
    binding_service = ChannelBindingService(deps.db, secrets_manager)
    return TikTokService(binding_service, deps.db, settings)


@router.post("/tiktok/webhook/{binding_id}")
async def handle_webhook(
    binding_id: str,
    request: Request,
    tiktok_service: TikTokService = Depends(get_tiktok_service),
):
    try:
        UUID(binding_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid binding ID format",
        )

    body = await request.body()
    settings = get_settings()

    if not settings.tiktok_messaging_enabled:
        return {"status": "ok", "pending_access": True}

    secret = settings.tiktok_app_secret or ""
    signature = (
        request.headers.get("X-TikTok-Signature")
        or request.headers.get("TikTok-Signature")
        or request.headers.get("x-tiktok-signature")
        or ""
    )
    if secret:
        if not signature or not verify_tiktok_signature(body, signature, secret):
            logger.warning("TikTok webhook signature rejected for binding %s", binding_id)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid webhook signature",
            )

    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload"
        )

    try:
        await tiktok_service.handle_webhook_event(payload, binding_id)
    except Exception as e:
        logger.error("Error handling TikTok webhook: %s", e, exc_info=True)
        return {"status": "error", "message": "Event processing failed"}

    return {"status": "ok"}


def _client_wants_json(request: Request) -> bool:
    """JSON for fetch/API clients; 302 only when the browser navigates (text/html)."""
    accept = (request.headers.get("accept") or "").lower()
    if "application/json" in accept:
        return True
    if "text/html" in accept and "application/json" not in accept:
        return False
    return True


@router.get("/tiktok/oauth/start")
async def oauth_start(
    request: Request,
    agent_id: str = Query(...),
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    settings = get_settings()
    if not settings.tiktok_app_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TIKTOK_APP_ID is not configured. Use paste-token connect instead.",
        )
    agent = await deps.db.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    base = (settings.app_url or "").rstrip("/")
    redirect_uri = f"{base}/api/v1/tiktok/oauth/callback"
    params = {
        "client_key": settings.tiktok_app_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "user.info.basic,business.messaging",
        "state": agent_id,
    }
    url = f"https://www.tiktok.com/v2/auth/authorize/?{urlencode(params)}"
    if _client_wants_json(request):
        return JSONResponse({"authorization_url": url})
    return RedirectResponse(url=url, status_code=302)


@router.get("/tiktok/oauth/callback")
async def oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    deps: CommonDependencies = Depends(),
    tiktok_service: TikTokService = Depends(get_tiktok_service),
):
    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"OAuth error: {error}")
    if not code or not state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing code or state")

    settings = get_settings()
    base = (settings.app_url or "").rstrip("/")
    redirect_uri = f"{base}/api/v1/tiktok/oauth/callback"
    exchanged = await tiktok_service.exchange_oauth_code(code, redirect_uri)

    secrets_manager = get_secrets_manager()
    binding_service = ChannelBindingService(deps.db, secrets_manager)
    agent_id = state
    metadata = {"connected_via": "oauth"}
    if not settings.tiktok_messaging_enabled:
        metadata["pending_access"] = True

    if exchanged and exchanged.get("access_token"):
        binding = await binding_service.create_binding(
            agent_id=agent_id,
            channel_type="tiktok",
            channel_account_id=exchanged.get("account_id") or "tiktok",
            access_token=exchanged["access_token"],
            metadata=metadata,
        )
        await binding_service.verify_binding(binding.binding_id)
        binding_id = binding.binding_id
    else:
        # Credentials missing or exchange failed — still record a pending binding if possible.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to exchange TikTok authorization code",
        )

    admin_url = f"{base}/admin/agents/{agent_id}/channels"
    return RedirectResponse(url=f"{admin_url}?tiktok_binding={binding_id}", status_code=302)
