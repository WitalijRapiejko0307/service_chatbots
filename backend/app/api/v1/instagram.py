"""Instagram webhook and optional OAuth endpoints."""

import json
import logging
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse

from app.api.auth import require_admin
from app.api.webhook_guards import enforce_or_warn_missing_webhook_secret
from app.config import get_settings
from app.dependencies import CommonDependencies
from app.services.channel_binding_service import ChannelBindingService
from app.services.instagram_service import InstagramService
from app.storage.resolver import get_secrets_manager
from app.utils.oauth_state import make_oauth_state, parse_oauth_state
from app.utils.operator_origin import operator_origin

logger = logging.getLogger(__name__)

router = APIRouter()


def get_instagram_service(
    deps: CommonDependencies = Depends(),
) -> InstagramService:
    settings = get_settings()
    secrets_manager = get_secrets_manager()
    binding_service = ChannelBindingService(deps.db, secrets_manager)
    return InstagramService(binding_service, deps.db, settings)


async def _get_instagram_verify_token() -> str:
    from app.storage.postgres_secrets import get_postgres_secrets_manager

    mgr = get_postgres_secrets_manager()
    db_token = await mgr.get_global_setting("instagram_verify_token")
    if db_token:
        return db_token
    settings = get_settings()
    return settings.instagram_webhook_verify_token or ""


async def _get_instagram_app_secret() -> str:
    from app.storage.postgres_secrets import get_postgres_secrets_manager

    mgr = get_postgres_secrets_manager()
    db_secret = await mgr.get_global_setting("instagram_app_secret")
    if db_secret:
        return db_secret
    settings = get_settings()
    return settings.instagram_app_secret or ""


@router.get("/instagram/webhook")
async def verify_webhook(
    mode: str = Query(..., alias="hub.mode", description="Webhook verification mode"),
    token: str = Query(..., alias="hub.verify_token", description="Verification token"),
    challenge: str = Query(..., alias="hub.challenge", description="Challenge string"),
):
    """Meta GET verify: return the challenge as plain text."""
    logger.info("Webhook verification request: mode=%s", mode)
    verify_token = await _get_instagram_verify_token()
    if not verify_token:
        logger.warning("Instagram verify token not configured")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Instagram not configured. Set verify token in Channel Settings.",
        )
    if mode == "subscribe" and token == verify_token:
        logger.info("Instagram webhook verified successfully")
        return PlainTextResponse(content=challenge, status_code=200)
    logger.warning("Instagram webhook verification failed: mode=%s, token mismatch", mode)
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Webhook verification failed",
    )


@router.post("/instagram/webhook")
async def handle_webhook(
    request: Request,
    instagram_service: InstagramService = Depends(get_instagram_service),
    x_hub_signature_256: Optional[str] = Header(
        None, alias="X-Hub-Signature-256", description="Webhook signature"
    ),
):
    body = await request.body()
    app_secret = await _get_instagram_app_secret()
    if app_secret:
        if not x_hub_signature_256 or not instagram_service.verify_webhook_signature(
            body, x_hub_signature_256, app_secret=app_secret
        ):
            logger.warning("Instagram webhook signature verification failed")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid webhook signature",
            )
    else:
        enforce_or_warn_missing_webhook_secret("instagram")

    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception as e:
        logger.error("Failed to parse Instagram webhook payload: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    try:
        from app.services.webhook_event_store import add_webhook_event

        add_webhook_event("instagram_webhook", payload)
    except Exception as store_exc:
        logger.debug("Instagram: could not store event: %s", store_exc)

    try:
        await instagram_service.handle_webhook_event(payload)
    except Exception as e:
        logger.error("Error handling webhook event: %s", e, exc_info=True)
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


@router.get("/instagram/oauth/start")
async def oauth_start(
    request: Request,
    agent_id: str = Query(...),
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Start Instagram Login OAuth when INSTAGRAM_APP_ID is set. Paste-token remains available."""
    settings = get_settings()
    if not settings.instagram_app_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="INSTAGRAM_APP_ID is not configured. Use paste-token connect instead.",
        )
    agent = await deps.db.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    base = (settings.app_url or "").rstrip("/")
    redirect_uri = f"{base}/api/v1/instagram/oauth/callback"
    secret = settings.jwt_secret_key or settings.secret_encryption_key or "dev"
    state = make_oauth_state(agent_id, secret)
    params = {
        "client_id": settings.instagram_app_id,
        "redirect_uri": redirect_uri,
        "scope": "instagram_business_basic,instagram_business_manage_messages",
        "response_type": "code",
        "state": state,
    }
    url = f"https://www.instagram.com/oauth/authorize?{urlencode(params)}"
    if _client_wants_json(request):
        return JSONResponse({"authorization_url": url})
    return RedirectResponse(url=url, status_code=302)


@router.get("/instagram/oauth/callback")
async def oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    deps: CommonDependencies = Depends(),
    instagram_service: InstagramService = Depends(get_instagram_service),
):
    settings = get_settings()
    origin = operator_origin(settings)
    secret = settings.jwt_secret_key or settings.secret_encryption_key or "dev"
    agent_id = parse_oauth_state(state, secret) if state else None

    def _fail(reason: str):
        if agent_id:
            return _channels_redirect(origin, agent_id, instagram_error=reason)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)

    if error:
        return _fail(error)
    if not code or not state:
        return _fail("missing_code" if not code else "missing_state")
    if not agent_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state")

    base = (settings.app_url or "").rstrip("/")
    redirect_uri = f"{base}/api/v1/instagram/oauth/callback"
    exchanged = await instagram_service.exchange_oauth_code(code, redirect_uri)
    if not exchanged or not exchanged.get("access_token"):
        return _fail("exchange_failed")

    secrets_manager = get_secrets_manager()
    binding_service = ChannelBindingService(deps.db, secrets_manager)
    metadata = {"connected_via": "oauth"}
    if exchanged.get("token_expires_at"):
        metadata["token_expires_at"] = exchanged["token_expires_at"]
    if exchanged.get("oauth_user_id"):
        metadata["instagram_oauth_user_id"] = exchanged["oauth_user_id"]
    account_id = exchanged["account_id"]
    existing = await binding_service.get_binding_by_account_id(
        channel_type="instagram", account_id=account_id
    )
    if not existing and exchanged.get("oauth_user_id"):
        existing = await binding_service.get_binding_by_account_id(
            channel_type="instagram", account_id=str(exchanged["oauth_user_id"])
        )
    if existing:
        await binding_service.update_binding(
            existing.binding_id,
            access_token=exchanged["access_token"],
            metadata=metadata,
            channel_account_id=account_id,
            channel_username=exchanged.get("username"),
        )
        await binding_service.verify_binding(existing.binding_id)
        binding_id = existing.binding_id
    else:
        binding = await binding_service.create_binding(
            agent_id=agent_id,
            channel_type="instagram",
            channel_account_id=exchanged["account_id"],
            access_token=exchanged["access_token"],
            metadata=metadata,
            channel_username=exchanged.get("username"),
        )
        await binding_service.verify_binding(binding.binding_id)
        binding_id = binding.binding_id

    return _channels_redirect(origin, agent_id, instagram_binding=binding_id)
