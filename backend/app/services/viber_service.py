"""Viber Public Account adapter — inbound webhooks and outbound send."""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any, Literal, Optional

import httpx

from app.config import Settings
from app.models.channel_binding import ChannelType
from app.models.message import MessageChannel
from app.services.channel_binding_service import ChannelBindingService
from app.services.inbound_channel import (
    find_or_create_conversation,
    persist_operator_message,
    persist_user_message_and_maybe_reply,
)
from app.utils.enum_helpers import get_enum_value

logger = logging.getLogger(__name__)

VIBER_API_BASE = "https://chatapi.viber.com/pa"
VIBER_EVENT_TYPES = [
    "message",
    "conversation_started",
    "delivered",
    "seen",
    "failed",
    "subscribed",
    "unsubscribed",
]

ViberEventKind = Literal["ignore", "customer", "operator"]


def classify_viber_event(payload: dict[str, Any]) -> ViberEventKind:
    """Classify a Viber callback. User ``message`` stays customer.

    Operator only when the sender is explicitly the business account
    (``sender.role`` in {business, pa, account} or ``from_business`` True).
    Viber does not send those fields on user message callbacks today.
    """
    if payload.get("event") != "message":
        return "ignore"
    sender = payload.get("sender") or {}
    role = str(sender.get("role") or "").strip().lower()
    if role in {"business", "pa", "account"}:
        return "operator"
    if payload.get("from_business") is True:
        return "operator"
    return "customer"


def verify_viber_signature(raw_body: bytes, signature_hex: str, auth_token: str) -> bool:
    """X-Viber-Content-Signature = hex HMAC-SHA256(body, key=auth_token)."""
    if not auth_token or not signature_hex:
        return False
    expected = hmac.new(
        auth_token.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected.lower(), signature_hex.strip().lower())


class ViberService:
    """Service for Viber Public Account messaging."""

    def __init__(
        self,
        channel_binding_service: ChannelBindingService,
        db: Any,
        settings: Settings,
    ):
        self.channel_binding_service = channel_binding_service
        self.db = db
        self.settings = settings

    async def handle_webhook_event(self, payload: dict[str, Any], binding_id: str) -> None:
        """Handle an inbound Viber event for a binding."""
        binding = await self.channel_binding_service.get_binding(binding_id)
        if not binding or not binding.is_active:
            logger.warning("Viber binding %s not found or inactive", binding_id)
            return
        if get_enum_value(binding.channel_type) != ChannelType.VIBER.value:
            return

        event = payload.get("event")
        if event == "conversation_started":
            await self._handle_conversation_started(payload, binding)
            return
        if event == "message":
            await self._handle_message(payload, binding)
            return
        logger.debug("Ignoring Viber event %s for binding %s", event, binding_id)

    async def _handle_conversation_started(self, payload: dict[str, Any], binding: Any) -> None:
        user = payload.get("user") or {}
        user_id = str(user.get("id") or "")
        if not user_id:
            logger.warning("Viber conversation_started without user id")
            return

        name = user.get("name")
        await find_or_create_conversation(
            self.db,
            agent_id=binding.agent_id,
            channel=MessageChannel.VIBER,
            external_user_id=user_id,
            name=name,
        )

        display_name = "наш помощник"
        try:
            agent_data = await self.db.get_agent(binding.agent_id)
            if agent_data and "config" in agent_data:
                profile = (agent_data["config"] or {}).get("profile") or {}
                display_name = profile.get("agent_display_name") or display_name
        except Exception as exc:
            logger.debug("Could not load agent display name for Viber welcome: %s", exc)

        welcome = f"Здравствуйте! Это {display_name}. Напишите, чем можем помочь."
        try:
            await self.send_message(
                binding_id=binding.binding_id,
                receiver_id=user_id,
                message_text=welcome,
            )
        except Exception as exc:
            logger.warning("Viber welcome send failed: %s", exc)

    async def _handle_message(self, payload: dict[str, Any], binding: Any) -> None:
        sender = payload.get("sender") or {}
        user_id = str(sender.get("id") or "")
        if not user_id:
            return

        message = payload.get("message") or {}
        msg_type = (message.get("type") or "text").lower()
        text = message.get("text") or ""
        media_url: Optional[str] = None
        media_type: Optional[str] = None

        if msg_type == "picture":
            media_url = message.get("media")
            media_type = "image"
        elif msg_type == "video":
            media_url = message.get("media")
            media_type = "video"
        elif msg_type in ("file", "url"):
            media_url = message.get("media") or message.get("url")
            media_type = "document"

        external_message_id = (
            payload.get("message_token")
            or message.get("token")
            or None
        )

        kind = classify_viber_event(payload)
        if kind == "operator":
            await self._persist_viber_operator(
                payload=payload,
                binding=binding,
                text=text,
                platform_id=external_message_id,
                media_url=media_url,
                media_type=media_type,
            )
            return

        conversation = await find_or_create_conversation(
            self.db,
            agent_id=binding.agent_id,
            channel=MessageChannel.VIBER,
            external_user_id=user_id,
            name=sender.get("name"),
        )

        await persist_user_message_and_maybe_reply(
            self.db,
            conversation=conversation,
            agent_id=binding.agent_id,
            channel=MessageChannel.VIBER,
            external_user_id=user_id,
            text=text,
            external_message_id=str(external_message_id) if external_message_id else None,
            binding_id=binding.binding_id,
            media_url=media_url,
            media_type=media_type,
        )

    async def _persist_viber_operator(
        self,
        *,
        payload: dict[str, Any],
        binding: Any,
        text: str,
        platform_id: Any,
        media_url: Optional[str],
        media_type: Optional[str],
    ) -> None:
        receiver = payload.get("receiver")
        if isinstance(receiver, dict):
            customer_id = str(receiver.get("id") or "")
        elif isinstance(receiver, str):
            customer_id = receiver
        else:
            customer_id = str((payload.get("user") or {}).get("id") or "")
        if not customer_id:
            logger.info("Viber operator event without customer id — skipping")
            return
        mid = str(platform_id).strip() if platform_id is not None else ""
        if not mid:
            logger.info("Viber operator event without message_token — skipping")
            return

        conversation = await find_or_create_conversation(
            self.db,
            agent_id=binding.agent_id,
            channel=MessageChannel.VIBER,
            external_user_id=customer_id,
        )
        await persist_operator_message(
            self.db,
            conversation=conversation,
            agent_id=binding.agent_id,
            channel=MessageChannel.VIBER,
            external_user_id=customer_id,
            text=text,
            external_message_id=mid,
            binding_id=binding.binding_id,
            media_url=media_url,
            media_type=media_type,
            provider_message_ids=[mid],
        )

    async def send_message(
        self,
        binding_id: str,
        receiver_id: str,
        message_text: str,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
        keyboard: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        token = await self.channel_binding_service.get_access_token(binding_id)
        headers = {"X-Viber-Auth-Token": token}

        async with httpx.AsyncClient(timeout=30.0) as client:
            if media_url and media_type == "image":
                payload: dict[str, Any] = {
                    "receiver": receiver_id,
                    "type": "picture",
                    "media": media_url,
                    "text": message_text or "",
                }
                if keyboard:
                    payload["keyboard"] = keyboard
                resp = await client.post(
                    f"{VIBER_API_BASE}/send_message", json=payload, headers=headers
                )
                if resp.status_code != 200 or resp.json().get("status") not in (0, None):
                    logger.error("Viber picture send failed: %s", resp.text)
                    if message_text:
                        return await self._send_text(
                            client, headers, receiver_id, message_text, keyboard
                        )
                    return {}
                return resp.json()

            if message_text:
                return await self._send_text(
                    client, headers, receiver_id, message_text, keyboard
                )
        return {}

    async def _send_text(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        receiver_id: str,
        text: str,
        keyboard: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "receiver": receiver_id,
            "type": "text",
            "text": text,
        }
        if keyboard:
            payload["keyboard"] = keyboard
        resp = await client.post(
            f"{VIBER_API_BASE}/send_message", json=payload, headers=headers
        )
        if resp.status_code != 200:
            logger.error("Viber send failed: %s", resp.text)
            resp.raise_for_status()
        data = resp.json()
        if data.get("status") not in (0, None):
            logger.error("Viber send status error: %s", data)
        else:
            logger.info("Sent Viber message to %s", receiver_id)
        return data

    async def verify_auth_token(self, auth_token: str) -> bool:
        """Verify PA token via get_account_info. Does not log the token."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{VIBER_API_BASE}/get_account_info",
                    json={},
                    headers={"X-Viber-Auth-Token": auth_token},
                )
                data = resp.json()
                if resp.status_code == 200 and data.get("status") == 0:
                    logger.info(
                        "Viber account verified: %s",
                        data.get("name") or data.get("uri"),
                    )
                    return True
                logger.warning("Viber get_account_info failed: status=%s", data.get("status"))
                return False
        except Exception as e:
            logger.error("Error verifying Viber token: %s", e, exc_info=True)
            return False

    async def set_webhook(self, binding_id: str, webhook_url: str) -> bool:
        """Register the Viber webhook. APP_URL should be HTTPS in production."""
        token = await self.channel_binding_service.get_access_token(binding_id)
        payload = {"url": webhook_url, "event_types": VIBER_EVENT_TYPES, "send_name": True}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{VIBER_API_BASE}/set_webhook",
                    json=payload,
                    headers={"X-Viber-Auth-Token": token},
                )
                data = resp.json()
                if resp.status_code == 200 and data.get("status") == 0:
                    logger.info("Viber webhook set: %s", webhook_url)
                    return True
                logger.error("Viber set_webhook failed: %s", data)
                return False
        except Exception as e:
            logger.error("Error setting Viber webhook: %s", e, exc_info=True)
            return False

    async def unset_webhook(self, auth_token: str, binding_id: str) -> bool:
        """Best-effort Viber set_webhook with empty URL. Never logs the token."""
        payload = {"url": "", "event_types": []}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{VIBER_API_BASE}/set_webhook",
                    json=payload,
                    headers={"X-Viber-Auth-Token": auth_token},
                )
                data = resp.json()
                if resp.status_code == 200 and data.get("status") == 0:
                    logger.info("Viber webhook unset for binding %s", binding_id)
                    return True
                logger.warning("Viber unset webhook failed for binding %s", binding_id)
                return False
        except Exception as e:
            logger.warning(
                "Error unsetting Viber webhook for binding %s: %s",
                binding_id,
                type(e).__name__,
            )
            return False
