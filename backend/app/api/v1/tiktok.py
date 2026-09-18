"""TikTok webhook and Login Kit OAuth endpoints."""

import json
import logging
from typing import Optional
from urllib.parse import unquote, urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.auth import require_admin
from app.config import get_settings
from app.dependencies import CommonDependencies
from app.services.channel_binding_service import ChannelBindingService
from app.services.tiktok_service import TikTokService, verify_tiktok_signature
from app.storage.resolver import get_secrets_manager
from app.utils.oauth_state import make_oauth_state, parse_oauth_state
from app.utils.operator_origin import operator_origin

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


def _channels_redirect(origin: str, agent_id: str, **params: str) -> RedirectResponse:
    return RedirectResponse(
        url=f"{origin}/admin/agents/{agent_id}/channels?{urlencode(params)}",
        status_code=302,
    )


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
    secret = settings.jwt_secret_key or settings.secret_encryption_key or "dev"
    state = make_oauth_state(agent_id, secret)
    scope = (
        "user.info.basic,business.messaging"
        if settings.tiktok_messaging_enabled
        else "user.info.basic"
    )
    params = {
        "client_key": settings.tiktok_app_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "state": state,
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
    settings = get_settings()
    origin = operator_origin(settings)
    secret = settings.jwt_secret_key or settings.secret_encryption_key or "dev"
    agent_id = parse_oauth_state(state, secret) if state else None

    def _fail(reason: str):
        if agent_id:
            return _channels_redirect(origin, agent_id, tiktok_error=reason)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)

    if error:
        return _fail(error)
    if not code or not state:
        return _fail("missing_code" if not code else "missing_state")
    if not agent_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state"
        )

    base = (settings.app_url or "").rstrip("/")
    redirect_uri = f"{base}/api/v1/tiktok/oauth/callback"
    exchanged = await tiktok_service.exchange_oauth_code(unquote(code), redirect_uri)
    if not exchanged or not exchanged.get("access_token") or not exchanged.get("account_id"):
        return _fail("exchange_failed")

    secrets_manager = get_secrets_manager()
    binding_service = ChannelBindingService(deps.db, secrets_manager)
    metadata = {"connected_via": "oauth"}
    if not settings.tiktok_messaging_enabled:
        metadata["pending_access"] = True
    if exchanged.get("refresh_token"):
        metadata["refresh_token"] = exchanged["refresh_token"]

    existing = await binding_service.get_binding_by_account_id(
        channel_type="tiktok", account_id=exchanged["account_id"]
    )
    if existing:
        await binding_service.update_binding(
            existing.binding_id,
            access_token=exchanged["access_token"],
            metadata=metadata,
        )
        await binding_service.verify_binding(existing.binding_id)
        binding_id = existing.binding_id
    else:
        binding = await binding_service.create_binding(
            agent_id=agent_id,
            channel_type="tiktok",
            channel_account_id=exchanged["account_id"],
            access_token=exchanged["access_token"],
            metadata=metadata,
        )
        await binding_service.verify_binding(binding.binding_id)
        binding_id = binding.binding_id

    return _channels_redirect(origin, agent_id, tiktok_binding=binding_id)
