"""Instagram Direct Messaging adapter — Graph API webhooks and send."""

from __future__ import annotations

import hashlib
import hmac
import logging
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
    persist_user_message_and_maybe_reply,
)
from app.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


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

        if is_echo or is_self:
            logger.info(
                "Ignoring Instagram echo/self message mid=%s",
                message_id,
            )
            return

        media_url: Optional[str] = None
        media_type: Optional[str] = None
        attachments = message_data.get("attachments", [])
        if attachments:
            attachment = attachments[0]
            att_type = attachment.get("type", "")
            payload_data = attachment.get("payload", {})
            att_url = payload_data.get("url")
            if att_url:
                media_url = att_url
                media_type = {
                    "image": "image",
                    "video": "video",
                    "audio": "audio",
                    "file": "document",
                }.get(att_type, "image")

        if not sender_id or not recipient_id or (not message_text and not media_url):
            logger.info("Ignoring incomplete Instagram messaging event")
            return

        binding = await self.channel_binding_service.get_binding_by_account_id(
            channel_type=ChannelType.INSTAGRAM.value, account_id=recipient_id
        )
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

        webhook_timestamp = utc_now()
        if "timestamp" in event:
            try:
                timestamp_ms = event["timestamp"]
                webhook_timestamp = datetime.fromtimestamp(
                    int(timestamp_ms) / 1000, tz=timezone.utc
                )
            except (ValueError, TypeError):
                pass

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
            timestamp=webhook_timestamp,
        )

    async def send_message(
        self,
        binding_id: str,
        recipient_id: str,
        message_text: str,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
    ) -> dict[str, Any]:
        """Send text and/or media via Instagram Graph API."""
        access_token = await self.channel_binding_service.get_access_token(binding_id)
        binding = await self.channel_binding_service.get_binding(binding_id)
        if not binding:
            raise ValueError(f"Binding {binding_id} not found")

        url = f"{self.GRAPH_API_BASE_URL}/{binding.channel_account_id}/messages"
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
                    if message_text:
                        await client.post(
                            url,
                            json={
                                "recipient": {"id": recipient_id},
                                "message": {"text": message_text},
                            },
                            headers=headers,
                        )
                    return resp.json()

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
                return response.json()

        return {}

    async def verify_access_token(self, access_token: str, account_id: Optional[str] = None) -> bool:
        """Graph API profile check. Marks the token as usable without logging it."""
        target = account_id or "me"
        url = f"{self.GRAPH_API_BASE_URL}/{target}"
        params = {"fields": "id,username", "access_token": access_token}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, params=params)
                if response.status_code == 200:
                    logger.info("Instagram token verified for account %s", target)
                    return True
                logger.warning(
                    "Instagram token verification failed: status=%s", response.status_code
                )
                return False
        except Exception as e:
            logger.error("Error verifying Instagram token: %s", e, exc_info=True)
            return False

    async def get_user_profile(
        self, igsid: str, access_token: str
    ) -> Optional[InstagramUserProfile]:
        url = f"{self.GRAPH_API_BASE_URL}/{igsid}"
        params = {"fields": "name,username,profile_pic", "access_token": access_token}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=params)
                if response.status_code != 200:
                    logger.warning(
                        "Failed to fetch Instagram profile %s: %s",
                        igsid,
                        response.status_code,
                    )
                    return None
                data = response.json()
                updated_at = utc_now()
                return InstagramUserProfile(
                    external_user_id=igsid,
                    name=data.get("name"),
                    username=data.get("username"),
                    profile_pic=data.get("profile_pic"),
                    updated_at=updated_at,
                    ttl=int((updated_at + timedelta(days=5)).timestamp()),
                )
        except Exception as e:
            logger.error("Unexpected error fetching Instagram profile %s: %s", igsid, e)
            return None

    async def refresh_user_profile(
        self, external_user_id: str, binding_id: str
    ) -> Optional[InstagramUserProfile]:
        access_token = await self.channel_binding_service.get_access_token(binding_id)
        profile = await self.get_user_profile(external_user_id, access_token)
        if profile:
            await self.db.create_or_update_instagram_profile(profile)
            logger.info("Refreshed Instagram profile for user %s", external_user_id)
        return profile

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
                if long_resp.status_code == 200:
                    token = long_resp.json().get("access_token") or short_token
                me = await client.get(
                    f"{self.GRAPH_API_BASE_URL}/me",
                    params={"fields": "id,username", "access_token": token},
                )
                username = None
                if me.status_code == 200:
                    me_data = me.json()
                    user_id = str(me_data.get("id") or user_id)
                    username = me_data.get("username")
                return {
                    "access_token": token,
                    "account_id": user_id,
                    "username": username,
                }
        except Exception as e:
            logger.error("Instagram OAuth exchange error: %s", e, exc_info=True)
            return None
