"""TikTok Business Messaging adapter.

When ``TIKTOK_MESSAGING_ENABLED`` is false, webhooks 200 no-op and send_message
logs without calling the network. Policy: user-initiated + 48h window, max 10
bot messages — counters live on conversation.metadata.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import timedelta, timezone
from typing import Any, Optional
from urllib.parse import unquote

import httpx

from app.config import Settings
from app.models.channel_binding import ChannelType
from app.models.message import MessageChannel
from app.services.channel_binding_service import ChannelBindingService
from app.services.inbound_channel import (
    find_or_create_conversation,
    persist_user_message_and_maybe_reply,
)
from app.utils.datetime_utils import parse_utc_datetime, utc_now
from app.utils.enum_helpers import get_enum_value
from app.utils.logging_config import redact_secrets

logger = logging.getLogger(__name__)

# Isolated HTTP surface — update here if TikTok publishes a new path.
TIKTOK_API_BASE = "https://business-api.tiktok.com/open_api/v1.3"
TIKTOK_SEND_PATH = "/business/message/send/"
TIKTOK_TOKEN_INFO_PATH = "/business/get/"
TIKTOK_OAUTH_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
TIKTOK_OAUTH_REVOKE_URL = "https://open.tiktokapis.com/v2/oauth/revoke/"
TIKTOK_WINDOW = timedelta(hours=48)
TIKTOK_MAX_OUTBOUND = 10
INBOUND_EVENT_TYPES = frozenset({"im_receive_msg", "im.receive_msg", "message", "receive_msg"})


def verify_tiktok_signature(raw_body: bytes, signature: str, app_secret: str) -> bool:
    """HMAC-SHA256 hex digest of the raw body using the app secret."""
    if not app_secret or not signature:
        return False
    expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    sig = signature.strip()
    if sig.startswith("sha256="):
        sig = sig[7:]
    return hmac.compare_digest(expected.lower(), sig.lower())


class TikTokService:
    """Service for TikTok Business Messaging."""

    def __init__(
        self,
        channel_binding_service: ChannelBindingService,
        db: Any,
        settings: Settings,
    ):
        self.channel_binding_service = channel_binding_service
        self.db = db
        self.settings = settings
        self.messaging_enabled = bool(settings.tiktok_messaging_enabled)

    async def handle_webhook_event(self, payload: dict[str, Any], binding_id: str) -> None:
        if not self.messaging_enabled:
            logger.info("TikTok messaging disabled — webhook no-op for binding %s", binding_id)
            return

        binding = await self.channel_binding_service.get_binding(binding_id)
        if not binding or not binding.is_active:
            logger.warning("TikTok binding %s not found or inactive", binding_id)
            return
        if get_enum_value(binding.channel_type) != ChannelType.TIKTOK.value:
            return

        event_type = str(
            payload.get("event")
            or payload.get("type")
            or (payload.get("data") or {}).get("event")
            or ""
        ).lower()
        if event_type and event_type not in INBOUND_EVENT_TYPES:
            logger.debug("Ignoring TikTok event %s", event_type)
            return

        data = payload.get("data") or payload
        user_id = str(
            data.get("from_user_id")
            or data.get("open_id")
            or data.get("user_openid")
            or data.get("sender_id")
            or ""
        )
        text = (
            data.get("text")
            or (data.get("message") or {}).get("text")
            or data.get("content")
            or ""
        )
        if isinstance(text, dict):
            text = text.get("text") or ""
        message_id = data.get("message_id") or data.get("msg_id") or payload.get("event_id")

        if not user_id:
            logger.info("TikTok inbound without user id — skipping")
            return

        conversation = await find_or_create_conversation(
            self.db,
            agent_id=binding.agent_id,
            channel=MessageChannel.TIKTOK,
            external_user_id=user_id,
        )
        await persist_user_message_and_maybe_reply(
            self.db,
            conversation=conversation,
            agent_id=binding.agent_id,
            channel=MessageChannel.TIKTOK,
            external_user_id=user_id,
            text=str(text or ""),
            external_message_id=str(message_id) if message_id else None,
            binding_id=binding_id,
        )

    async def send_message(
        self,
        binding_id: str,
        recipient_id: str,
        message_text: str,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
    ) -> bool:
        if not self.messaging_enabled:
            logger.info("TikTok messaging disabled — send no-op")
            return False

        access_token = await self.channel_binding_service.get_access_token(binding_id)
        binding = await self.channel_binding_service.get_binding(binding_id)
        if not binding:
            raise ValueError(f"Binding {binding_id} not found")

        payload: dict[str, Any] = {
            "business_id": binding.channel_account_id,
            "recipient_id": recipient_id,
            "message_type": "text",
            "text": message_text or "",
        }

        url = f"{TIKTOK_API_BASE}{TIKTOK_SEND_PATH}"
        headers = {
            "Access-Token": access_token,
            "Content-Type": "application/json",
        }

        async def _post(body: dict[str, Any]) -> bool:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json=body, headers=headers)
                if resp.status_code != 200:
                    logger.error(
                        "TikTok send failed: %s %s",
                        resp.status_code,
                        redact_secrets(resp.text or ""),
                    )
                    return False
                data = resp.json()
                if data.get("code") not in (0, None, "0"):
                    logger.error(
                        "TikTok send API error: %s",
                        redact_secrets(str(data.get("message") or data)),
                    )
                    return False
                return True

        try:
            if media_url:
                media_payload = dict(payload)
                media_payload["message_type"] = "image" if media_type == "image" else "file"
                media_payload["media_url"] = media_url
                if await _post(media_payload):
                    logger.info("Sent TikTok message to %s", recipient_id)
                    return True
                logger.info(
                    "TikTok media send failed; falling back to text-only for recipient %s",
                    recipient_id,
                )
            if await _post(payload):
                logger.info("Sent TikTok message to %s", recipient_id)
                return True
            return False
        except Exception as e:
            logger.error("TikTok send error: %s", e, exc_info=True)
            return False

    async def verify_access_token(self, access_token: str) -> bool:
        if not self.messaging_enabled:
            return False
        url = f"{TIKTOK_API_BASE}{TIKTOK_TOKEN_INFO_PATH}"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    url, headers={"Access-Token": access_token}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("code") in (0, None, "0")
                logger.warning("TikTok token check failed: status=%s", resp.status_code)
                return False
        except Exception as e:
            logger.error("Error verifying TikTok token: %s", e, exc_info=True)
            return False

    async def set_webhook(self, binding_id: str, webhook_url: str) -> bool:
        """Best-effort webhook registration. Isolated so API shape changes stay here."""
        if not self.messaging_enabled:
            return False
        logger.info(
            "TikTok webhook URL for binding %s (configure in TikTok developer portal): %s",
            binding_id,
            webhook_url,
        )
        return True

    async def unset_webhook(self, binding_id: str) -> bool:
        """No public unregister API in current TikTok messaging docs — log only."""
        logger.info(
            "TikTok webhook unregister is not available via API; unbind locally for %s",
            binding_id,
        )
        return True

    async def can_send_ai_message(self, db: Any, conversation_id: str) -> bool:
        conversation = await db.get_conversation(conversation_id)
        if not conversation:
            return False
        meta = conversation.metadata or {}
        started_raw = meta.get("tiktok_window_started_at")
        count = int(meta.get("tiktok_outbound_count") or 0)
        if not started_raw:
            return False
        started = parse_utc_datetime(started_raw) if isinstance(started_raw, str) else started_raw
        if started is None:
            return False
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        if utc_now() - started > TIKTOK_WINDOW:
            return False
        if count >= TIKTOK_MAX_OUTBOUND:
            return False
        return True

    async def record_outbound(self, db: Any, conversation_id: str) -> None:
        conversation = await db.get_conversation(conversation_id)
        if not conversation:
            return
        meta = dict(conversation.metadata or {})
        meta["tiktok_outbound_count"] = int(meta.get("tiktok_outbound_count") or 0) + 1
        try:
            await db.update_conversation(conversation_id, metadata=meta)
        except Exception as exc:
            logger.warning(
                "Could not increment TikTok outbound count for %s: %s",
                conversation_id,
                exc,
            )

    async def revoke_access_token(self, access_token: str) -> bool:
        """Best-effort Login Kit token revoke. Never raises."""
        token = (access_token or "").strip()
        app_id = self.settings.tiktok_app_id
        app_secret = self.settings.tiktok_app_secret
        if not app_id or not app_secret or not token:
            return False
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    TIKTOK_OAUTH_REVOKE_URL,
                    data={
                        "client_key": app_id,
                        "client_secret": app_secret,
                        "token": token,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            if resp.status_code != 200:
                logger.warning("TikTok token revoke failed: status=%s", resp.status_code)
                return False
            return True
        except Exception as e:
            logger.warning("TikTok token revoke error: %s", type(e).__name__)
            return False

    async def exchange_oauth_code(
        self, code: str, redirect_uri: str
    ) -> Optional[dict[str, Any]]:
        """Login Kit v2 authorization-code exchange."""
        app_id = self.settings.tiktok_app_id
        app_secret = self.settings.tiktok_app_secret
        decoded_code = unquote(code or "")
        if not app_id or not app_secret or not decoded_code:
            return None
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    TIKTOK_OAUTH_TOKEN_URL,
                    data={
                        "client_key": app_id,
                        "client_secret": app_secret,
                        "code": decoded_code,
                        "grant_type": "authorization_code",
                        "redirect_uri": redirect_uri,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            try:
                body = resp.json() or {}
            except Exception:
                body = {}
            nested = body.get("data") if isinstance(body.get("data"), dict) else {}
            log_id = body.get("log_id") or nested.get("log_id")
            logger.info(
                "TikTok OAuth token exchange status=%s log_id=%s",
                resp.status_code,
                log_id,
            )
            if resp.status_code != 200:
                return None
            token = nested.get("access_token") or body.get("access_token")
            open_id = nested.get("open_id") or body.get("open_id")
            refresh_token = nested.get("refresh_token") or body.get("refresh_token")
            if not token or not open_id:
                return None
            result: dict[str, Any] = {
                "access_token": token,
                "account_id": str(open_id),
            }
            if refresh_token:
                result["refresh_token"] = refresh_token
            return result
        except Exception as e:
            logger.error("TikTok OAuth exchange error: %s", type(e).__name__, exc_info=True)
            return None
