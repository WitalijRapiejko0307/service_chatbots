"""Channel sender abstraction — web chat plus live messenger adapters."""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from datetime import timedelta, timezone
from typing import Any, Optional

from app.models.message import MessageChannel
from app.utils.datetime_utils import parse_utc_datetime, to_utc_iso_string, utc_now
from app.utils.enum_helpers import get_enum_value

logger = logging.getLogger(__name__)

INSTAGRAM_MESSAGING_WINDOW = timedelta(hours=24)


def _build_reply_markup(quick_replies: list[str]) -> dict:
    """Build a Telegram ReplyKeyboardMarkup or remove-keyboard dict.

    Buttons are grouped into rows of two. An empty list produces
    ``remove_keyboard: true`` to dismiss any previously shown keyboard.
    """
    if quick_replies:
        rows = [quick_replies[i : i + 2] for i in range(0, len(quick_replies), 2)]
        return {
            "keyboard": [[{"text": btn} for btn in row] for row in rows],
            "one_time_keyboard": True,
            "resize_keyboard": True,
        }
    return {"remove_keyboard": True}


def _build_viber_keyboard(quick_replies: list[str]) -> dict:
    """Map quick replies to a Viber keyboard (ActionType=reply)."""
    buttons = []
    columns = 3 if len(quick_replies) > 1 else 6
    for text in quick_replies:
        buttons.append(
            {
                "Columns": columns,
                "Rows": 1,
                "ActionType": "reply",
                "ActionBody": text,
                "Text": text,
                "Silent": True,
            }
        )
    return {"Type": "keyboard", "DefaultHeight": False, "Buttons": buttons}


async def _resolve_binding_and_user(
    db: Any,
    conversation_id: str,
    expected_channel: str,
    binding_id: Optional[str],
    external_user_id: Optional[str],
) -> tuple[str, str]:
    """Resolve (binding_id, external_user_id) from the conversation when omitted."""
    if binding_id and external_user_id:
        return binding_id, external_user_id

    conversation = await db.get_conversation(conversation_id)
    if not conversation:
        raise ValueError(f"Conversation {conversation_id} not found")

    conversation_channel = get_enum_value(conversation.channel)
    if conversation_channel != expected_channel:
        raise ValueError(
            f"Conversation {conversation_id} is not a {expected_channel} conversation"
        )

    resolved_user = external_user_id or conversation.external_user_id
    if not resolved_user:
        raise ValueError(
            f"external_user_id is required for {expected_channel} messages"
        )

    if not binding_id:
        from app.services.channel_binding_service import ChannelBindingService
        from app.storage.resolver import get_secrets_manager

        binding_service = ChannelBindingService(db, get_secrets_manager())
        bindings = await binding_service.get_bindings_by_agent(
            agent_id=conversation.agent_id,
            channel_type=expected_channel,
            active_only=True,
        )
        if not bindings:
            raise ValueError(
                f"No active {expected_channel} binding found for agent {conversation.agent_id}"
            )
        binding_id = bindings[0].binding_id

    return binding_id, resolved_user


class ChannelSender(ABC):
    """Abstract base class for channel senders."""

    @abstractmethod
    async def send_message(
        self,
        conversation_id: str,
        message_text: str,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
        **kwargs,
    ) -> None:
        pass


class WebChatSender(ChannelSender):
    """Sender for web chat channel (WebSocket)."""

    def __init__(self, db: Any):
        self.db = db

    async def send_message(
        self,
        conversation_id: str,
        message_text: str,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
        message_id: Optional[str] = None,
        **kwargs,
    ) -> None:
        from app.api.websocket import connection_manager

        payload: dict = {
            "type": "message",
            "message_id": message_id or str(uuid.uuid4()),
            "role": "agent",
            "content": message_text,
            "timestamp": to_utc_iso_string(utc_now()),
        }
        if media_url:
            payload["media_url"] = media_url
            payload["media_type"] = media_type

        delivered = await connection_manager.send_message(conversation_id, payload)
        if delivered:
            logger.info(
                "WebChatSender: WS push delivered for conversation %s", conversation_id
            )
        else:
            logger.info(
                "WebChatSender: no active WS for conversation %s "
                "(message persisted in DB; client will receive on reconnect)",
                conversation_id,
            )


class TelegramSender(ChannelSender):
    """Sender for Telegram channel."""

    def __init__(self, telegram_service: Any, db: Any):
        self.telegram_service = telegram_service
        self.db = db

    async def send_message(
        self,
        conversation_id: str,
        message_text: str,
        binding_id: Optional[str] = None,
        external_user_id: Optional[str] = None,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
        quick_replies: Optional[list[str]] = None,
        **kwargs,
    ) -> None:
        binding_id, external_user_id = await _resolve_binding_and_user(
            self.db,
            conversation_id,
            MessageChannel.TELEGRAM.value,
            binding_id,
            external_user_id,
        )
        reply_markup = (
            _build_reply_markup(quick_replies) if quick_replies is not None else None
        )
        await self.telegram_service.send_message(
            binding_id=binding_id,
            chat_id=external_user_id,
            message_text=message_text,
            media_url=media_url,
            media_type=media_type,
            reply_markup=reply_markup,
        )


class ViberSender(ChannelSender):
    """Sender for Viber Public Account channel."""

    def __init__(self, viber_service: Any, db: Any):
        self.viber_service = viber_service
        self.db = db

    async def send_message(
        self,
        conversation_id: str,
        message_text: str,
        binding_id: Optional[str] = None,
        external_user_id: Optional[str] = None,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
        quick_replies: Optional[list[str]] = None,
        **kwargs,
    ) -> None:
        binding_id, external_user_id = await _resolve_binding_and_user(
            self.db,
            conversation_id,
            MessageChannel.VIBER.value,
            binding_id,
            external_user_id,
        )
        keyboard = (
            _build_viber_keyboard(quick_replies) if quick_replies else None
        )
        await self.viber_service.send_message(
            binding_id=binding_id,
            receiver_id=external_user_id,
            message_text=message_text,
            media_url=media_url,
            media_type=media_type,
            keyboard=keyboard,
        )


class InstagramSender(ChannelSender):
    """Sender for Instagram Direct."""

    def __init__(self, instagram_service: Any, db: Any):
        self.instagram_service = instagram_service
        self.db = db

    async def send_message(
        self,
        conversation_id: str,
        message_text: str,
        binding_id: Optional[str] = None,
        external_user_id: Optional[str] = None,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
        is_human_reply: bool = False,
        **kwargs,
    ) -> None:
        binding_id, external_user_id = await _resolve_binding_and_user(
            self.db,
            conversation_id,
            MessageChannel.INSTAGRAM.value,
            binding_id,
            external_user_id,
        )
        if not is_human_reply and await _instagram_window_expired(self.db, conversation_id):
            logger.info(
                "Instagram 24h messaging window expired for conversation %s — skipping AI send",
                conversation_id,
            )
            return
        await self.instagram_service.send_message(
            binding_id=binding_id,
            recipient_id=external_user_id,
            message_text=message_text,
            media_url=media_url,
            media_type=media_type,
        )


class TikTokSender(ChannelSender):
    """Sender for TikTok Business Messaging."""

    def __init__(self, tiktok_service: Any, db: Any):
        self.tiktok_service = tiktok_service
        self.db = db

    async def send_message(
        self,
        conversation_id: str,
        message_text: str,
        binding_id: Optional[str] = None,
        external_user_id: Optional[str] = None,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
        is_human_reply: bool = False,
        **kwargs,
    ) -> None:
        if not getattr(self.tiktok_service, "messaging_enabled", False):
            logger.info(
                "TikTok messaging disabled — outbound no-op for conversation %s",
                conversation_id,
            )
            return

        binding_id, external_user_id = await _resolve_binding_and_user(
            self.db,
            conversation_id,
            MessageChannel.TIKTOK.value,
            binding_id,
            external_user_id,
        )
        if not is_human_reply and not await self.tiktok_service.can_send_ai_message(
            self.db, conversation_id
        ):
            logger.info(
                "TikTok 48h/10-message policy blocks AI send for conversation %s",
                conversation_id,
            )
            return

        sent = await self.tiktok_service.send_message(
            binding_id=binding_id,
            recipient_id=external_user_id,
            message_text=message_text,
            media_url=media_url,
            media_type=media_type,
        )
        if sent and not is_human_reply:
            await self.tiktok_service.record_outbound(self.db, conversation_id)


async def _instagram_window_expired(db: Any, conversation_id: str) -> bool:
    conversation = await db.get_conversation(conversation_id)
    if not conversation:
        return False
    raw = (conversation.metadata or {}).get("last_user_message_at")
    if not raw:
        return False
    try:
        last = parse_utc_datetime(raw) if isinstance(raw, str) else raw
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return utc_now() - last > INSTAGRAM_MESSAGING_WINDOW
    except Exception:
        return False


def _build_telegram_service(db: Any) -> Any:
    from app.config import get_settings
    from app.services.channel_binding_service import ChannelBindingService
    from app.services.telegram_service import TelegramService
    from app.storage.resolver import get_secrets_manager

    return TelegramService(
        ChannelBindingService(db, get_secrets_manager()), db, get_settings()
    )


def _build_viber_service(db: Any) -> Any:
    from app.config import get_settings
    from app.services.channel_binding_service import ChannelBindingService
    from app.services.viber_service import ViberService
    from app.storage.resolver import get_secrets_manager

    return ViberService(
        ChannelBindingService(db, get_secrets_manager()), db, get_settings()
    )


def _build_instagram_service(db: Any) -> Any:
    from app.config import get_settings
    from app.services.channel_binding_service import ChannelBindingService
    from app.services.instagram_service import InstagramService
    from app.storage.resolver import get_secrets_manager

    return InstagramService(
        ChannelBindingService(db, get_secrets_manager()), db, get_settings()
    )


def _build_tiktok_service(db: Any) -> Any:
    from app.config import get_settings
    from app.services.channel_binding_service import ChannelBindingService
    from app.services.tiktok_service import TikTokService
    from app.storage.resolver import get_secrets_manager

    return TikTokService(
        ChannelBindingService(db, get_secrets_manager()), db, get_settings()
    )


def get_channel_sender(
    channel: MessageChannel | str,
    db: Any,
    **kwargs,
) -> ChannelSender:
    """Get the sender for *channel*. Services are constructed from *db* lazily.

    Extra kwargs are ignored so existing callers that pass only (channel, db)
    keep working.
    """
    del kwargs
    channel_value = get_enum_value(channel)
    try:
        channel_enum = (
            channel if isinstance(channel, MessageChannel) else MessageChannel(channel_value)
        )
    except ValueError as exc:
        raise ValueError(f"Unsupported channel: {channel}") from exc

    if channel_enum == MessageChannel.WEB_CHAT:
        return WebChatSender(db)
    if channel_enum == MessageChannel.TELEGRAM:
        return TelegramSender(_build_telegram_service(db), db)
    if channel_enum == MessageChannel.VIBER:
        return ViberSender(_build_viber_service(db), db)
    if channel_enum == MessageChannel.INSTAGRAM:
        return InstagramSender(_build_instagram_service(db), db)
    if channel_enum == MessageChannel.TIKTOK:
        return TikTokSender(_build_tiktok_service(db), db)
    raise ValueError(f"Unsupported channel: {channel}")
