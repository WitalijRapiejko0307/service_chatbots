"""Shared inbound path for messenger adapters (Telegram, Viber, Instagram, TikTok).

Webhook adapters parse platform payloads, then call:
  1. find_or_create_conversation
  2. persist_user_message_and_maybe_reply

Owner UI never talks to messengers. One conversation identity per
(agent_id, channel, external_user_id).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from app.config import get_settings
from app.models.conversation import Conversation, ConversationStatus, MarketingStatus
from app.models.message import Message, MessageChannel, MessageRole
from app.utils.datetime_utils import to_utc_iso_string, utc_now
from app.utils.enum_helpers import get_enum_value

logger = logging.getLogger(__name__)

# Stable namespace: same (channel, binding, user, external id) → same message_id.
_MSG_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

HANDOFF_STATUSES = frozenset(
    {
        ConversationStatus.NEEDS_HUMAN.value,
        ConversationStatus.HUMAN_ACTIVE.value,
    }
)


def deterministic_message_id(
    channel: str,
    binding_id: Optional[str],
    external_user_id: str,
    external_message_id: str,
) -> str:
    """UUID5 so duplicate webhook deliveries collide on the messages PK."""
    seed = f"{channel}:{binding_id or ''}:{external_user_id}:{external_message_id}"
    return str(uuid.uuid5(_MSG_NS, seed))


async def find_or_create_conversation(
    db: Any,
    agent_id: str,
    channel: MessageChannel | str,
    external_user_id: str,
    name: Optional[str] = None,
    username: Optional[str] = None,
    external_conversation_id: Optional[str] = None,
) -> Conversation:
    """Return the latest non-CLOSED conversation for this identity, or create one."""
    channel_value = get_enum_value(channel)

    existing: Optional[Conversation] = None
    try:
        existing = await db.get_conversation_by_external_user(
            agent_id=agent_id,
            channel=channel_value,
            external_user_id=external_user_id,
            include_closed=False,
        )
    except Exception as exc:
        logger.warning(
            "SQL lookup for conversation failed (agent=%s channel=%s user=%s): %s",
            agent_id,
            channel_value,
            external_user_id,
            exc,
        )

    if existing:
        updates: dict[str, Any] = {}
        if name and not existing.external_user_name:
            updates["external_user_name"] = name
        if username and not existing.external_user_username:
            updates["external_user_username"] = username
        if updates:
            try:
                await db.update_conversation(existing.conversation_id, **updates)
                if "external_user_name" in updates:
                    existing.external_user_name = name
                if "external_user_username" in updates:
                    existing.external_user_username = username
            except Exception as exc:
                logger.warning(
                    "Could not update conversation %s user fields: %s",
                    existing.conversation_id,
                    exc,
                )
        return existing

    conversation = Conversation(
        conversation_id=str(uuid.uuid4()),
        agent_id=agent_id,
        channel=channel_value,
        external_user_id=external_user_id,
        external_conversation_id=external_conversation_id,
        external_user_name=name,
        external_user_username=username,
        status=ConversationStatus.AI_ACTIVE,
        marketing_status=MarketingStatus.NEW,
        created_at=utc_now(),
        updated_at=utc_now(),
        metadata={},
    )
    await db.create_conversation(conversation)
    logger.info(
        "Created conversation %s for agent=%s channel=%s user=%s",
        conversation.conversation_id,
        agent_id,
        channel_value,
        external_user_id,
    )
    return conversation


def _merge_inbound_metadata(
    conversation: Conversation,
    channel_value: str,
    *,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    meta = dict(conversation.metadata or {})
    if extra:
        meta.update(extra)
    now_iso = to_utc_iso_string(utc_now())
    meta["last_user_message_at"] = now_iso
    if channel_value == MessageChannel.TIKTOK.value:
        meta["tiktok_window_started_at"] = now_iso
        meta["tiktok_outbound_count"] = 0
    return meta


async def persist_user_message_and_maybe_reply(
    db: Any,
    *,
    conversation: Conversation,
    agent_id: str,
    channel: MessageChannel | str,
    external_user_id: str,
    text: str,
    external_message_id: Optional[str] = None,
    binding_id: Optional[str] = None,
    media_url: Optional[str] = None,
    media_type: Optional[str] = None,
    vision_user_media_url: Optional[str] = None,
    timestamp: Optional[datetime] = None,
    extra_metadata: Optional[dict[str, Any]] = None,
    is_voice: bool = False,
) -> bool:
    """Persist inbound user message; run the agent unless handoff / duplicate / empty.

    Returns True if a new message row was inserted.
    Never logs access tokens.
    """
    channel_value = get_enum_value(channel)
    channel_enum = (
        channel if isinstance(channel, MessageChannel) else MessageChannel(channel_value)
    )

    message_text = text or ""
    resolved_media_url = media_url
    resolved_media_type = media_type
    vision_url = vision_user_media_url

    if is_voice and resolved_media_url and not message_text.strip():
        try:
            from app.services.stt_service import transcribe_from_url

            transcript = await transcribe_from_url(resolved_media_url, language="ru")
            if transcript:
                message_text = transcript
                logger.info(
                    "STT transcribed voice for channel=%s user=%s: %d chars",
                    channel_value,
                    external_user_id,
                    len(transcript),
                )
        except Exception as exc:
            logger.warning(
                "STT failed for channel=%s user=%s: %s",
                channel_value,
                external_user_id,
                exc,
            )

    if not vision_url and resolved_media_type == "image" and resolved_media_url:
        vision_url = resolved_media_url

    msg_metadata: dict[str, Any] = dict(extra_metadata or {})
    if resolved_media_url:
        msg_metadata["media_url"] = resolved_media_url
    if resolved_media_type:
        msg_metadata["media_type"] = resolved_media_type

    if external_message_id:
        message_id = deterministic_message_id(
            channel_value, binding_id, external_user_id, str(external_message_id)
        )
    else:
        message_id = str(uuid.uuid4())

    user_message = Message(
        message_id=message_id,
        conversation_id=conversation.conversation_id,
        agent_id=agent_id,
        role=MessageRole.USER,
        content=message_text,
        channel=channel_enum,
        external_message_id=str(external_message_id) if external_message_id else None,
        external_user_id=external_user_id,
        timestamp=timestamp or utc_now(),
        metadata=msg_metadata,
        media_url=resolved_media_url,
        media_type=resolved_media_type,
    )

    inserted = await db.try_create_message(user_message)
    if not inserted:
        logger.info(
            "Duplicate inbound message channel=%s external_message_id=%s user=%s — skipping",
            channel_value,
            external_message_id,
            external_user_id,
        )
        return False

    conv_meta = _merge_inbound_metadata(
        conversation, channel_value, extra=None
    )
    try:
        await db.update_conversation(conversation.conversation_id, metadata=conv_meta)
        conversation.metadata = conv_meta
    except Exception as exc:
        logger.warning(
            "Could not update conversation %s inbound metadata: %s",
            conversation.conversation_id,
            exc,
        )

    status_value = get_enum_value(conversation.status)
    if status_value in HANDOFF_STATUSES:
        logger.info(
            "Conversation %s is %s — persisting only, skipping AI",
            conversation.conversation_id,
            status_value,
        )
        return True

    if not message_text.strip() and not vision_url:
        logger.debug(
            "Inbound message saved for %s (no text and no image for vision), skipping agent",
            conversation.conversation_id,
        )
        return True

    try:
        from app.services.agent_reply_coordinator import cancel_timer_trigger

        await cancel_timer_trigger(conversation.conversation_id)
    except Exception as exc:
        logger.debug("cancel_timer_trigger failed for %s: %s", conversation.conversation_id, exc)

    try:
        agent_data = await db.get_agent(agent_id)
        if not agent_data or "config" not in agent_data:
            logger.error("Agent %s not found or invalid configuration", agent_id)
            return True

        from app.models.agent_config import AgentConfig
        from app.services.agent_service import create_agent_service
        from app.services.channel_sender import get_channel_sender
        from app.services.conversation_service import build_conversation_history_for_agent

        agent_config = AgentConfig.from_dict(agent_data["config"])
        conversation_history = await build_conversation_history_for_agent(
            db,
            conversation.conversation_id,
            message_text,
            agent_context_reset_at=conversation.agent_context_reset_at,
        )

        channel_sender = get_channel_sender(channel_enum, db)
        agent_service = create_agent_service(agent_config, db, channel_sender)

        settings = get_settings()
        if settings.agent_reply_debounce_seconds > 0 and not vision_url:
            from app.services.agent_reply_coordinator import notify_user_message_saved
            from app.storage.redis import get_redis_client

            redis_client = get_redis_client()
            if await redis_client.ping():
                mod_early = await agent_service.run_pre_moderation_guard(
                    message_text, conversation.conversation_id
                )
                if mod_early and mod_early.get("escalate"):
                    return True
                notify_result = await notify_user_message_saved(
                    conversation.conversation_id,
                    agent_user_message=message_text,
                    last_user_plain_content=message_text.strip(),
                )
                if notify_result == "scheduled":
                    return True

        result = await agent_service.process_message(
            user_message=message_text,
            conversation_id=conversation.conversation_id,
            conversation_history=conversation_history,
            user_media_url=vision_url,
        )
        if result.get("escalate"):
            logger.info(
                "Message escalated for conversation %s", conversation.conversation_id
            )
    except Exception as exc:
        logger.error(
            "Error processing inbound message through agent (conversation=%s): %s",
            conversation.conversation_id,
            exc,
            exc_info=True,
        )

    return True
