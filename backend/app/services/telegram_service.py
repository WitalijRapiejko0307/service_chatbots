"""Telegram Bot API adapter — inbound webhooks and outbound send."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.config import Settings
from app.models.channel_binding import ChannelType
from app.models.message import MessageChannel
from app.services.channel_binding_service import ChannelBindingService
from app.services.inbound_channel import (
    find_or_create_conversation,
    persist_user_message_and_maybe_reply,
)
from app.utils.datetime_utils import utc_now
from app.utils.enum_helpers import get_enum_value

logger = logging.getLogger(__name__)

TELEGRAM_MESSAGE_MAX_LENGTH = 4096


def _truncate_for_telegram_text(text: str, max_len: int = TELEGRAM_MESSAGE_MAX_LENGTH) -> str:
    """Telegram returns 400 if text exceeds the limit."""
    if len(text) <= max_len:
        return text
    suffix = "\n…(truncated)"
    take = max_len - len(suffix)
    if take < 64:
        return text[:max_len]
    return text[:take] + suffix


class TelegramService:
    """Service for Telegram Bot messaging integration."""

    TELEGRAM_API_BASE_URL = "https://api.telegram.org/bot"

    def __init__(
        self,
        channel_binding_service: ChannelBindingService,
        db: Any,
        settings: Settings,
    ):
        self.channel_binding_service = channel_binding_service
        self.db = db
        self.settings = settings

    async def _get_file_url(self, bot_token: str, file_id: str) -> Optional[str]:
        """Resolve a Telegram file_id to a download URL."""
        url = f"{self.TELEGRAM_API_BASE_URL}{bot_token}/getFile?file_id={file_id}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                data = resp.json()
                if data.get("ok") and data.get("result", {}).get("file_path"):
                    file_path = data["result"]["file_path"]
                    return f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
        except Exception as e:
            logger.warning("Could not resolve Telegram file_id: %s", e)
        return None

    async def handle_webhook_event(self, payload: dict[str, Any], binding_id: str) -> None:
        """Handle incoming webhook event from Telegram."""
        try:
            binding = await self.channel_binding_service.get_binding(binding_id)
            if not binding or not binding.is_active:
                logger.warning("Binding %s not found or inactive", binding_id)
                return
            if get_enum_value(binding.channel_type) != ChannelType.TELEGRAM.value:
                return

            if "pre_checkout_query" in payload or "callback_query" in payload:
                logger.debug("Ignoring Telegram payment/callback update %s", payload.get("update_id"))
                return

            message_data = payload.get("message")
            if not message_data:
                logger.debug("Telegram update without message: %s", payload.get("update_id"))
                return

            if "successful_payment" in message_data:
                logger.debug("Ignoring Telegram successful_payment (payments out of scope)")
                return

            chat = message_data.get("chat", {})
            chat_id = str(chat.get("id", "") or "")
            message_text = message_data.get("text") or message_data.get("caption") or ""
            message_id = message_data.get("message_id")
            from_user = message_data.get("from", {})

            if from_user.get("is_bot", False):
                return
            if not chat_id:
                return

            media_url: Optional[str] = None
            media_type: Optional[str] = None
            bot_token: Optional[str] = None
            is_voice = False

            has_photo = bool(message_data.get("photo"))
            has_video = bool(message_data.get("video"))
            has_audio = bool(message_data.get("audio") or message_data.get("voice"))
            has_document = bool(message_data.get("document"))
            has_sticker = bool(message_data.get("sticker"))

            if has_photo or has_video or has_audio or has_document or has_sticker:
                try:
                    bot_token = await self.channel_binding_service.get_access_token(binding_id)
                except Exception:
                    bot_token = None

                if has_photo and bot_token:
                    photos = message_data["photo"]
                    file_id = photos[-1]["file_id"]
                    media_url = await self._get_file_url(bot_token, file_id)
                    media_type = "image"
                elif has_video and bot_token:
                    file_id = message_data["video"]["file_id"]
                    media_url = await self._get_file_url(bot_token, file_id)
                    media_type = "video"
                elif has_audio and bot_token:
                    is_voice = bool(message_data.get("voice"))
                    audio = message_data.get("audio") or message_data.get("voice", {})
                    file_id = audio.get("file_id")
                    if file_id:
                        media_url = await self._get_file_url(bot_token, file_id)
                    media_type = "audio"
                elif has_document and bot_token:
                    file_id = message_data["document"]["file_id"]
                    media_url = await self._get_file_url(bot_token, file_id)
                    media_type = "document"
                elif has_sticker and bot_token:
                    st = message_data.get("sticker") or {}
                    fid = st.get("file_id") or (st.get("thumb") or {}).get("file_id")
                    if fid:
                        media_url = await self._get_file_url(bot_token, fid)
                    media_type = "image"

            vision_user_media_url = media_url if media_type == "image" and media_url else None

            if not message_text and not media_url and not has_sticker:
                logger.debug("Telegram message with no content (chat_id=%s), skipping", chat_id)
                return

            message_timestamp = utc_now()
            if "date" in message_data:
                try:
                    message_timestamp = datetime.fromtimestamp(
                        int(message_data["date"]), tz=timezone.utc
                    )
                except (ValueError, TypeError):
                    pass

            first_name = from_user.get("first_name", "")
            last_name = from_user.get("last_name", "")
            username = from_user.get("username")
            user_name = f"{first_name} {last_name}".strip() or None

            if message_text.startswith("/"):
                if bot_token is None:
                    try:
                        bot_token = await self.channel_binding_service.get_access_token(binding_id)
                    except Exception:
                        bot_token = None
                if bot_token:
                    from app.services.bot_commands_service import dispatch_command

                    handled = await dispatch_command(
                        command=message_text,
                        chat_id=chat_id,
                        binding=binding,
                        bot_token=bot_token,
                        db=self.db,
                    )
                    if handled:
                        return

            conversation = await find_or_create_conversation(
                self.db,
                agent_id=binding.agent_id,
                channel=MessageChannel.TELEGRAM,
                external_user_id=chat_id,
                name=user_name,
                username=username,
            )

            await persist_user_message_and_maybe_reply(
                self.db,
                conversation=conversation,
                agent_id=binding.agent_id,
                channel=MessageChannel.TELEGRAM,
                external_user_id=chat_id,
                text=message_text,
                external_message_id=str(message_id) if message_id else None,
                binding_id=binding_id,
                media_url=media_url,
                media_type=media_type,
                vision_user_media_url=vision_user_media_url,
                timestamp=message_timestamp,
                is_voice=is_voice,
            )
        except Exception as e:
            logger.error("Error handling Telegram webhook event: %s", e, exc_info=True)
            raise

    async def send_message(
        self,
        binding_id: str,
        chat_id: str,
        message_text: str,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
        reply_markup: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Send text and/or media via Telegram Bot API."""
        bot_token = await self.channel_binding_service.get_access_token(binding_id)
        text = _truncate_for_telegram_text(message_text or "")

        async with httpx.AsyncClient(timeout=30.0) as client:
            if media_url and media_type:
                if media_type == "image":
                    endpoint = f"{self.TELEGRAM_API_BASE_URL}{bot_token}/sendPhoto"
                    payload: dict[str, Any] = {"chat_id": chat_id, "photo": media_url}
                    if text:
                        payload["caption"] = text
                elif media_type == "video":
                    endpoint = f"{self.TELEGRAM_API_BASE_URL}{bot_token}/sendVideo"
                    payload = {"chat_id": chat_id, "video": media_url}
                    if text:
                        payload["caption"] = text
                elif media_type == "audio":
                    endpoint = f"{self.TELEGRAM_API_BASE_URL}{bot_token}/sendAudio"
                    payload = {"chat_id": chat_id, "audio": media_url}
                    if text:
                        payload["caption"] = text
                else:
                    endpoint = f"{self.TELEGRAM_API_BASE_URL}{bot_token}/sendDocument"
                    payload = {"chat_id": chat_id, "document": media_url}
                    if text:
                        payload["caption"] = text

                if reply_markup:
                    payload["reply_markup"] = reply_markup

                resp = await client.post(endpoint, json=payload)
                if resp.status_code != 200 or not resp.json().get("ok"):
                    logger.error("Telegram media send failed: %s", resp.text)
                    if text:
                        text_payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
                        if reply_markup:
                            text_payload["reply_markup"] = reply_markup
                        text_resp = await client.post(
                            f"{self.TELEGRAM_API_BASE_URL}{bot_token}/sendMessage",
                            json=text_payload,
                        )
                        return text_resp.json()
                    return {}
                logger.info("Sent Telegram %s to chat %s", media_type, chat_id)
                return resp.json()

            if text:
                text_only_payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
                if reply_markup:
                    text_only_payload["reply_markup"] = reply_markup
                resp = await client.post(
                    f"{self.TELEGRAM_API_BASE_URL}{bot_token}/sendMessage",
                    json=text_only_payload,
                )
                if resp.status_code != 200 or not resp.json().get("ok"):
                    logger.error("Telegram send failed: %s", resp.text)
                    resp.raise_for_status()
                logger.info("Sent Telegram message to chat %s", chat_id)
                return resp.json()

        return {}

    async def verify_bot_token(self, bot_token: str) -> bool:
        """Verify bot token by calling getMe. Does not log the token."""
        url = f"{self.TELEGRAM_API_BASE_URL}{bot_token}/getMe"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                result = response.json()
                if result.get("ok") and result.get("result"):
                    bot_info = result["result"]
                    logger.info(
                        "Telegram bot verified: @%s (id: %s)",
                        bot_info.get("username"),
                        bot_info.get("id"),
                    )
                    return True
                return False
        except Exception as e:
            logger.error("Error verifying Telegram bot token: %s", e, exc_info=True)
            return False

    async def set_webhook(
        self, binding_id: str, webhook_url: str, secret_token: Optional[str] = None
    ) -> bool:
        """Set webhook URL for Telegram bot and store it on the binding."""
        bot_token = await self.channel_binding_service.get_access_token(binding_id)
        url = f"{self.TELEGRAM_API_BASE_URL}{bot_token}/setWebhook"
        payload: dict[str, Any] = {"url": webhook_url}
        if secret_token:
            payload["secret_token"] = secret_token
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                result = response.json()
                if result.get("ok"):
                    logger.info("Telegram webhook set: %s", webhook_url)
                    try:
                        binding = await self.channel_binding_service.get_binding(binding_id)
                        metadata = dict(binding.metadata or {}) if binding else {}
                        metadata["webhook_url"] = webhook_url
                        await self.channel_binding_service.update_binding(
                            binding_id, metadata=metadata
                        )
                    except Exception as meta_exc:
                        logger.warning(
                            "Telegram webhook set but metadata update failed: %s", meta_exc
                        )
                    return True
                logger.error("Telegram setWebhook error: %s", result.get("description"))
                return False
        except Exception as e:
            logger.error("Error setting Telegram webhook: %s", e, exc_info=True)
            return False

    async def delete_webhook(self, bot_token: str, binding_id: str) -> bool:
        """Best-effort Telegram deleteWebhook. Never logs the bot token."""
        url = f"{self.TELEGRAM_API_BASE_URL}{bot_token}/deleteWebhook"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url)
                result = response.json()
                if result.get("ok"):
                    logger.info("Telegram webhook deleted for binding %s", binding_id)
                    return True
                logger.warning("Telegram deleteWebhook failed for binding %s", binding_id)
                return False
        except Exception as e:
            logger.warning(
                "Error deleting Telegram webhook for binding %s: %s",
                binding_id,
                type(e).__name__,
            )
            return False
