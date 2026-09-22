"""Instagram Direct Messaging adapter — Graph API webhooks and send."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from app.config import Settings
from app.models.channel_binding import ChannelType
from app.models.instagram_user_profile import InstagramUserProfile
from app.models.message import MessageChannel
from app.services.channel_binding_service import ChannelBindingService
from app.services.inbound_channel import (
    find_or_create_conversation,
    persist_operator_message,
    persist_user_message_and_maybe_reply,
)
from app.utils.datetime_utils import parse_utc_datetime, to_utc_iso_string, utc_now
from app.utils.enum_helpers import get_enum_value

logger = logging.getLogger(__name__)

TOKEN_REFRESH_INTERVAL_SECONDS = 6 * 3600
TOKEN_REFRESH_HORIZON_DAYS = 10
LONG_LIVED_TOKEN_DEFAULT_SECONDS = 60 * 24 * 3600

_APP_REVIEW_NEEDLES = (
    "advanced access",
    "development mode",
    "not been approved",
    "not in live mode",
    "live mode",
    "instagram_manage_messages",
    "insufficient permission",
    "does not have permission",
    "does not have the capability",
    "permission denied",
)
_APP_REVIEW_CODES = {10, 200}


def _graph_message_id(response: httpx.Response) -> Optional[str]:
    """Return Graph ``message_id`` from a successful JSON body, or None."""
    try:
        data = response.json()
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    mid = data.get("message_id")
    if mid is None:
        return None
    value = str(mid).strip()
    return value or None


def graph_error_text(response: httpx.Response) -> str:
    """Best-effort Graph error string; never includes tokens."""
    try:
        data = response.json()
    except Exception:
        data = None
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            msg = err.get("message") or err.get("error_user_msg") or err.get("error_user_title")
            if msg:
                return str(msg)
        if data.get("message"):
            return str(data["message"])
    text = (response.text or "").strip()
    return text[:400] if text else f"Graph API HTTP {response.status_code}"


def graph_error_code(response: httpx.Response) -> Optional[int]:
    try:
        err = (response.json() or {}).get("error") or {}
        code = err.get("code")
        return int(code) if code is not None else None
    except Exception:
        return None


def is_instagram_app_review_error(
    status_code: int,
    body: str,
    error_code: Optional[int] = None,
) -> bool:
    """True when Graph failed because the app lacks Live / Advanced Access."""
    if error_code in _APP_REVIEW_CODES:
        return True
    lower = (body or "").lower()
    return any(needle in lower for needle in _APP_REVIEW_NEEDLES)


@dataclass(frozen=True)
class InstagramTokenCheck:
    ok: bool
    app_review_pending: bool = False
    error: Optional[str] = None
    account_id: Optional[str] = None
    username: Optional[str] = None


class InstagramService:
    """Service for Instagram Direct Messaging integration."""

    GRAPH_API_BASE_URL = "https://graph.instagram.com/v21.0"

    def __init__(
        self,
        channel_binding_service: ChannelBindingService,
        db: Any,
        settings: Settings,
    ):
        self.channel_binding_service = channel_binding_service
        self.db = db
        self.settings = settings

    def verify_webhook(self, mode: str, token: str, challenge: str, verify_token: str) -> Optional[str]:
        """Return challenge when hub.mode/token match."""
        if mode == "subscribe" and verify_token and token == verify_token:
            logger.info("Instagram webhook verified successfully")
            return challenge
        logger.warning("Instagram webhook verification failed: mode=%s, token mismatch", mode)
        return None

    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
        app_secret: Optional[str] = None,
    ) -> bool:
        """Verify X-Hub-Signature-256 using the app secret."""
        secret = app_secret or self.settings.instagram_app_secret
        if not secret:
            logger.warning("Instagram app secret not configured, skipping signature verification")
            return True

        expected_signature = hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        if signature.startswith("sha256="):
            signature = signature[7:]
        return hmac.compare_digest(expected_signature, signature)

    async def handle_webhook_event(self, payload: dict[str, Any]) -> None:
        """Handle incoming webhook event from Instagram."""
        if payload.get("object") != "instagram":
            logger.warning("Unknown webhook object type: %s", payload.get("object"))
            return

        entries = payload.get("entry", [])
        for entry in entries:
            messaging = entry.get("messaging", [])
            for event in messaging:
                event_type = self._get_event_type(event)
                if event_type == "message":
                    await self._process_messaging_event(event)
                else:
                    logger.info("Skipping Instagram event type '%s'", event_type)

    def _get_event_type(self, event: dict[str, Any]) -> str:
        if "sender" in event and "recipient" in event:
            return "message"
        if "message" in event:
            return "message"
        if "message_edit" in event:
            return "message_edit"
        if "message_reaction" in event:
            return "message_reaction"
        if "message_unsend" in event:
            return "message_unsend"
        return "unknown"

    def _instagram_attachment_media(
        self, message_data: dict[str, Any]
    ) -> tuple[Optional[str], Optional[str]]:
        attachments = message_data.get("attachments") or []
        if not attachments:
            return None, None
        attachment = attachments[0]
        att_type = attachment.get("type", "")
        payload_data = attachment.get("payload") or {}
        att_url = payload_data.get("url")
        if not att_url:
            return None, None
        media_type = {
            "image": "image",
            "video": "video",
            "audio": "audio",
            "file": "document",
        }.get(att_type, "image")
        return att_url, media_type

    def _instagram_event_timestamp(self, event: dict[str, Any]) -> datetime:
        webhook_timestamp = utc_now()
        if "timestamp" in event:
            try:
                timestamp_ms = event["timestamp"]
                webhook_timestamp = datetime.fromtimestamp(
                    int(timestamp_ms) / 1000, tz=timezone.utc
                )
            except (ValueError, TypeError):
                pass
        return webhook_timestamp

    async def _process_messaging_event(self, event: dict[str, Any]) -> None:
        sender = event.get("sender", {})
        recipient = event.get("recipient", {})
        message_data = event.get("message", {})

        sender_id = sender.get("id")
        recipient_id = recipient.get("id")
        message_text = message_data.get("text", "") or ""
        message_id = message_data.get("mid")
        is_echo = message_data.get("is_echo", False)
        is_self = message_data.get("is_self", False)

        media_url, media_type = self._instagram_attachment_media(message_data)

        if not sender_id or not recipient_id or (not message_text and not media_url):
            logger.info("Ignoring incomplete Instagram messaging event")
            return

        if is_echo or is_self:
            await self._process_operator_echo(
                business_id=sender_id,
                customer_id=recipient_id,
                message_text=message_text,
                platform_id=message_id,
                media_url=media_url,
                media_type=media_type,
                timestamp=self._instagram_event_timestamp(event),
            )
            return

        binding = await self.channel_binding_service.get_binding_by_account_id(
            channel_type=ChannelType.INSTAGRAM.value, account_id=recipient_id
        )
        if not binding or not binding.is_active:
            binding = await self._binding_for_webhook_recipient(recipient_id)
        if not binding or not binding.is_active:
            logger.warning(
                "Received Instagram message for unbound or inactive account %s",
                recipient_id,
            )
            return

        conversation = await find_or_create_conversation(
            self.db,
            agent_id=binding.agent_id,
            channel=MessageChannel.INSTAGRAM,
            external_user_id=sender_id,
        )

        try:
            await self.refresh_user_profile(sender_id, binding.binding_id)
        except Exception as exc:
            logger.debug("Instagram profile refresh skipped: %s", exc)

        await persist_user_message_and_maybe_reply(
            self.db,
            conversation=conversation,
            agent_id=binding.agent_id,
            channel=MessageChannel.INSTAGRAM,
            external_user_id=sender_id,
            text=message_text,
            external_message_id=message_id,
            binding_id=binding.binding_id,
            media_url=media_url,
            media_type=media_type,
            timestamp=self._instagram_event_timestamp(event),
        )

    async def _process_operator_echo(
        self,
        *,
        business_id: str,
        customer_id: str,
        message_text: str,
        platform_id: Any,
        media_url: Optional[str],
        media_type: Optional[str],
        timestamp: datetime,
    ) -> None:
        binding = await self.channel_binding_service.get_binding_by_account_id(
            channel_type=ChannelType.INSTAGRAM.value, account_id=business_id
        )
        if not binding or not binding.is_active:
            binding = await self._binding_for_webhook_recipient(business_id)
        if not binding or not binding.is_active:
            logger.warning(
                "Received Instagram message for unbound or inactive account %s",
                business_id,
            )
            return

        mid = str(platform_id).strip() if platform_id is not None else ""
        if not mid:
            logger.info("Ignoring Instagram echo without message id")
            return

        conversation = await find_or_create_conversation(
            self.db,
            agent_id=binding.agent_id,
            channel=MessageChannel.INSTAGRAM,
            external_user_id=customer_id,
        )

        try:
            await self.refresh_user_profile(customer_id, binding.binding_id)
        except Exception as exc:
            logger.debug("Instagram profile refresh skipped: %s", exc)

        await persist_operator_message(
            self.db,
            conversation=conversation,
            agent_id=binding.agent_id,
            channel=MessageChannel.INSTAGRAM,
            external_user_id=customer_id,
            text=message_text,
            external_message_id=mid,
            binding_id=binding.binding_id,
            media_url=media_url,
            media_type=media_type,
            timestamp=timestamp,
            provider_message_ids=[mid],
        )

    async def send_message(
        self,
        binding_id: str,
        recipient_id: str,
        message_text: str,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
    ) -> list[str]:
        """Send text and/or media via Instagram Graph API.

        Returns Graph ``message_id`` strings from successful POSTs only.
        """
        access_token = await self.channel_binding_service.get_access_token(binding_id)
        binding = await self.channel_binding_service.get_binding(binding_id)
        if not binding:
            raise ValueError(f"Binding {binding_id} not found")

        graph_user_id = (
            (binding.metadata or {}).get("instagram_graph_user_id")
            or binding.channel_account_id
        )
        url = f"{self.GRAPH_API_BASE_URL}/{graph_user_id}/messages"
        headers = {"Authorization": f"Bearer {access_token}"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            if media_url and media_type:
                ig_type = {
                    "image": "image",
                    "video": "video",
                    "audio": "audio",
                    "document": "file",
                }.get(media_type, "image")
                media_payload = {
                    "recipient": {"id": recipient_id},
                    "message": {
                        "attachment": {
                            "type": ig_type,
                            "payload": {"url": media_url, "is_reusable": True},
                        }
                    },
                }
                resp = await client.post(url, json=media_payload, headers=headers)
                if resp.status_code != 200:
                    logger.error("Instagram media send failed: %s %s", resp.status_code, resp.text)
                else:
                    logger.info("Sent Instagram %s to %s", media_type, recipient_id)
                    ids: list[str] = []
                    media_id = _graph_message_id(resp)
                    if media_id:
                        ids.append(media_id)
                    if message_text:
                        text_resp = await client.post(
                            url,
                            json={
                                "recipient": {"id": recipient_id},
                                "message": {"text": message_text},
                            },
                            headers=headers,
                        )
                        if text_resp.status_code == 200:
                            text_id = _graph_message_id(text_resp)
                            if text_id:
                                ids.append(text_id)
                    return ids

            if message_text:
                payload = {
                    "recipient": {"id": recipient_id},
                    "message": {"text": message_text},
                }
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code != 200:
                    logger.error(
                        "Instagram send failed: %s %s", response.status_code, response.text
                    )
                    response.raise_for_status()
                logger.info("Sent Instagram message to %s", recipient_id)
                mid = _graph_message_id(response)
                return [mid] if mid else []

        return []

    async def verify_access_token(self, access_token: str, account_id: Optional[str] = None) -> bool:
        """Graph API profile check. Marks the token as usable without logging it."""
        check = await self.verify_access_token_detailed(access_token, account_id)
        return check.ok

    async def verify_access_token_detailed(
        self, access_token: str, account_id: Optional[str] = None
    ) -> InstagramTokenCheck:
        """Graph /me check. Instagram Login /me id is not the webhook IGSID."""
        del account_id
        url = f"{self.GRAPH_API_BASE_URL}/me"
        params = {"fields": "id,username"}
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, params=params, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    graph_user_id = str(data.get("id") or "")
                    username = data.get("username")
                    logger.info(
                        "Instagram token verified for account %s", graph_user_id or "me"
                    )
                    return InstagramTokenCheck(
                        ok=True, account_id=graph_user_id or None, username=username
                    )
                text = graph_error_text(response)
                pending = is_instagram_app_review_error(
                    response.status_code, text, graph_error_code(response)
                )
                logger.warning(
                    "Instagram token verification failed: status=%s pending_review=%s",
                    response.status_code,
                    pending,
                )
                return InstagramTokenCheck(
                    ok=False, app_review_pending=pending, error=text
                )
        except Exception as e:
            logger.error("Error verifying Instagram token: %s", e, exc_info=True)
            return InstagramTokenCheck(ok=False, error="Graph API request failed")

    async def resolve_account_from_token(
        self, access_token: str
    ) -> Optional[dict[str, str]]:
        """Return Graph /me id and username. Webhook recipient.id is a different IGSID."""
        check = await self.verify_access_token_detailed(access_token)
        if not check.ok or not check.account_id:
            return None
        return {
            "account_id": check.account_id,
            "username": check.username or "",
        }

    async def subscribe_messaging_webhooks(
        self, access_token: str, ig_user_id: str
    ) -> bool:
        """Best-effort per-account messages subscription (Meta also has an app-level callback)."""
        if not ig_user_id:
            return False
        url = f"{self.GRAPH_API_BASE_URL}/{ig_user_id}/subscribed_apps"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    url,
                    params={"subscribed_fields": "messages"},
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                if response.status_code == 200:
                    logger.info("Instagram subscribed_apps ok for %s", ig_user_id)
                    return True
                logger.warning(
                    "Instagram subscribed_apps failed: status=%s",
                    response.status_code,
                )
                return False
        except Exception as e:
            logger.warning("Instagram subscribed_apps error: %s", type(e).__name__)
            return False

    async def _binding_for_webhook_recipient(self, recipient_id: str) -> Optional[Any]:
        """Map webhook IGSID to a binding whose Graph /me id is different."""
        bindings = await self.channel_binding_service.list_bindings_by_channel(
            ChannelType.INSTAGRAM.value, active_only=True
        )
        for binding in bindings:
            if self._binding_knows_igsid(binding, recipient_id):
                return await self._heal_instagram_account_id(binding, recipient_id)

        token_matched: list[Any] = []
        for binding in bindings:
            try:
                token = await self.channel_binding_service.get_access_token(
                    binding.binding_id
                )
                resolved = await self.resolve_account_from_token(token)
            except Exception:
                continue
            me_id = (resolved or {}).get("account_id") or ""
            if not me_id:
                continue
            stored = str(binding.channel_account_id or "")
            meta = binding.metadata or {}
            aliases = {
                stored,
                str(meta.get("instagram_oauth_user_id") or ""),
                str(meta.get("instagram_graph_user_id") or ""),
            }
            if me_id in aliases or recipient_id in aliases:
                return await self._heal_instagram_account_id(binding, recipient_id)
            token_matched.append(binding)
        if len(token_matched) == 1:
            return await self._heal_instagram_account_id(token_matched[0], recipient_id)
        return None

    def _binding_knows_igsid(self, binding: Any, recipient_id: str) -> bool:
        meta = binding.metadata or {}
        return recipient_id in {
            str(binding.channel_account_id or ""),
            str(meta.get("instagram_oauth_user_id") or ""),
            str(meta.get("instagram_graph_user_id") or ""),
            str(meta.get("instagram_igsid") or ""),
        }

    async def _heal_instagram_account_id(self, binding: Any, igsid: str) -> Any:
        meta = dict(binding.metadata or {})
        stored = str(binding.channel_account_id or "")
        if stored and stored != igsid:
            meta.setdefault("instagram_oauth_user_id", stored)
            meta.setdefault("instagram_graph_user_id", stored)
        meta["instagram_igsid"] = igsid
        if stored == igsid and meta.get("instagram_igsid") == igsid:
            if binding.metadata == meta:
                return binding
        updated = await self.channel_binding_service.update_binding(
            binding.binding_id, channel_account_id=igsid, metadata=meta
        )
        logger.info(
            "Corrected Instagram binding %s account id to webhook IGSID",
            binding.binding_id,
        )
        return updated

    async def get_user_profile(
        self, igsid: str, access_token: str
    ) -> tuple[Optional[InstagramUserProfile], Optional[str]]:
        url = f"{self.GRAPH_API_BASE_URL}/{igsid}"
        params = {"fields": "name,username,profile_pic", "access_token": access_token}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=params)
                if response.status_code != 200:
                    error = graph_error_text(response)
                    logger.warning(
                        "Failed to fetch Instagram profile %s: %s",
                        igsid,
                        response.status_code,
                    )
                    return None, error
                data = response.json()
                updated_at = utc_now()
                return (
                    InstagramUserProfile(
                        external_user_id=igsid,
                        name=data.get("name"),
                        username=data.get("username"),
                        profile_pic=data.get("profile_pic"),
                        updated_at=updated_at,
                        ttl=int((updated_at + timedelta(days=5)).timestamp()),
                    ),
                    None,
                )
        except Exception as e:
            logger.error("Unexpected error fetching Instagram profile %s: %s", igsid, e)
            return None, "Graph API request failed"

    async def refresh_user_profile(
        self, external_user_id: str, binding_id: str
    ) -> tuple[Optional[InstagramUserProfile], Optional[str]]:
        access_token = await self.channel_binding_service.get_access_token(binding_id)
        profile, error = await self.get_user_profile(external_user_id, access_token)
        if profile:
            await self.db.create_or_update_instagram_profile(profile)
            logger.info("Refreshed Instagram profile for user %s", external_user_id)
        return profile, error

    async def refresh_profile_for_conversation(
        self, conversation: Any
    ) -> tuple[Optional[InstagramUserProfile], Optional[str]]:
        """Admin Inbox refresh. Raises ValueError when the conversation is not Instagram."""
        channel = get_enum_value(conversation.channel)
        if channel != MessageChannel.INSTAGRAM.value:
            raise ValueError("This endpoint is only available for Instagram conversations")
        external_user_id = getattr(conversation, "external_user_id", None)
        if not external_user_id:
            return None, "Conversation has no Instagram user id"
        bindings = await self.channel_binding_service.get_bindings_by_agent(
            conversation.agent_id,
            channel_type=ChannelType.INSTAGRAM.value,
            active_only=True,
        )
        if not bindings:
            return None, "No Instagram connection for this agent"
        return await self.refresh_user_profile(external_user_id, bindings[0].binding_id)

    async def refresh_long_lived_token(self, access_token: str) -> Optional[dict[str, Any]]:
        """Refresh an Instagram Login long-lived token (not a Page token)."""
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(
                    "https://graph.instagram.com/refresh_access_token",
                    params={
                        "grant_type": "ig_refresh_token",
                        "access_token": access_token,
                    },
                )
                if resp.status_code != 200:
                    logger.warning(
                        "Instagram token refresh failed: status=%s", resp.status_code
                    )
                    return None
                data = resp.json()
                token = data.get("access_token")
                if not token:
                    return None
                expires_in = int(data.get("expires_in") or LONG_LIVED_TOKEN_DEFAULT_SECONDS)
                return {
                    "access_token": token,
                    "expires_in": expires_in,
                    "token_expires_at": to_utc_iso_string(
                        utc_now() + timedelta(seconds=expires_in)
                    ),
                }
        except Exception as e:
            logger.error("Instagram token refresh error: %s", e, exc_info=True)
            return None

    async def exchange_oauth_code(
        self, code: str, redirect_uri: str
    ) -> Optional[dict[str, Any]]:
        """Exchange an Instagram Login authorization code for a token + account id."""
        app_id = self.settings.instagram_app_id
        app_secret = self.settings.instagram_app_secret
        if not app_id or not app_secret:
            return None
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    "https://api.instagram.com/oauth/access_token",
                    data={
                        "client_id": app_id,
                        "client_secret": app_secret,
                        "grant_type": "authorization_code",
                        "redirect_uri": redirect_uri,
                        "code": code,
                    },
                )
                if resp.status_code != 200:
                    logger.warning("Instagram OAuth token exchange failed: %s", resp.status_code)
                    return None
                data = resp.json()
                short_token = data.get("access_token")
                user_id = str(data.get("user_id") or "")
                if not short_token:
                    return None
                long_resp = await client.get(
                    "https://graph.instagram.com/access_token",
                    params={
                        "grant_type": "ig_exchange_token",
                        "client_secret": app_secret,
                        "access_token": short_token,
                    },
                )
                token = short_token
                expires_in = LONG_LIVED_TOKEN_DEFAULT_SECONDS
                if long_resp.status_code == 200:
                    long_data = long_resp.json()
                    token = long_data.get("access_token") or short_token
                    if long_data.get("expires_in"):
                        expires_in = int(long_data["expires_in"])
                resolved = await self.resolve_account_from_token(token)
                if not resolved or not resolved.get("account_id"):
                    logger.warning("Instagram OAuth /me did not return an IGSID")
                    return None
                igsid = resolved["account_id"]
                result: dict[str, Any] = {
                    "access_token": token,
                    "account_id": igsid,
                    "username": resolved.get("username") or None,
                    "expires_in": expires_in,
                    "token_expires_at": to_utc_iso_string(
                        utc_now() + timedelta(seconds=expires_in)
                    ),
                }
                if user_id and user_id != igsid:
                    result["oauth_user_id"] = user_id
                return result
        except Exception as e:
            logger.error("Instagram OAuth exchange error: %s", e, exc_info=True)
            return None


def _oauth_token_refresh_due(metadata: dict[str, Any]) -> bool:
    if metadata.get("connected_via") != "oauth":
        return False
    raw = metadata.get("token_expires_at")
    if not raw:
        return True
    try:
        exp = parse_utc_datetime(str(raw))
    except Exception:
        return True
    if exp is None:
        return True
    return exp <= utc_now() + timedelta(days=TOKEN_REFRESH_HORIZON_DAYS)


async def refresh_expiring_instagram_oauth_tokens() -> int:
    """Refresh Instagram Login tokens within TOKEN_REFRESH_HORIZON_DAYS of expiry."""
    from app.config import get_settings
    from app.dependencies import get_db
    from app.storage.resolver import get_secrets_manager

    settings = get_settings()
    db = get_db()
    if not hasattr(db, "list_channel_bindings_by_channel"):
        return 0
    secrets_manager = get_secrets_manager()
    binding_service = ChannelBindingService(db, secrets_manager)
    svc = InstagramService(binding_service, db, settings)
    bindings = await db.list_channel_bindings_by_channel(
        ChannelType.INSTAGRAM.value, active_only=True
    )
    refreshed = 0
    for binding in bindings:
        meta = dict(binding.metadata or {})
        if not _oauth_token_refresh_due(meta):
            continue
        try:
            token = await binding_service.get_access_token(binding.binding_id)
            result = await svc.refresh_long_lived_token(token)
            if not result or not result.get("access_token"):
                continue
            was_verified = binding.is_verified
            meta["token_expires_at"] = result["token_expires_at"]
            await binding_service.update_binding(
                binding.binding_id,
                access_token=result["access_token"],
                metadata=meta,
            )
            await binding_service.update_binding(
                binding.binding_id, is_verified=was_verified
            )
            refreshed += 1
        except Exception as e:
            logger.warning(
                "Instagram OAuth token refresh skipped for binding %s: %s",
                binding.binding_id,
                type(e).__name__,
            )
    if refreshed:
        logger.info("Refreshed %s Instagram OAuth token(s)", refreshed)
    return refreshed


async def run_instagram_token_refresh_loop(shutdown: asyncio.Event) -> None:
    """Periodic Instagram Login token refresh until shutdown."""
    while not shutdown.is_set():
        try:
            await refresh_expiring_instagram_oauth_tokens()
        except Exception:
            logger.exception("Instagram OAuth token refresh loop failed")
        try:
            await asyncio.wait_for(shutdown.wait(), timeout=TOKEN_REFRESH_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass
