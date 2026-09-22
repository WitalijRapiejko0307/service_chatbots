"""Shared agent-reply pipeline for inbound user messages across all channels."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from app.config import get_settings
from app.models.conversation import Conversation, ConversationStatus
from app.models.message import Message, MessageRole
from app.services.agent_reply_coordinator import cancel_timer_trigger, notify_user_message_saved
from app.services.agent_service import AgentService
from app.services.conversation_service import build_conversation_history_for_agent
from app.services.conversation_status_service import update_conversation_with_notifications
from app.storage.redis import get_redis_client
from app.utils.datetime_utils import utc_now
from app.utils.enum_helpers import get_enum_value

logger = logging.getLogger(__name__)

_FALLBACK_AGENT_RESPONSE = "I apologize, but I couldn't generate a response."


class PipelineOutcome(str, Enum):
    """How the shared pipeline finished."""

    PROCESSED = "processed"
    ESCALATED = "escalated"
    PRE_MODERATION_ESCALATED = "pre_moderation_escalated"
    DEBOUNCE_SCHEDULED = "debounce_scheduled"


@dataclass
class InboundPipelineOptions:
    """Channel-specific behavior flags for the shared pipeline."""

    cancel_inactivity_timer: bool = True
    cancel_timer_swallow_errors: bool = False
    skip_debounce_for_media: bool = True
    create_fallback_agent_message: bool = False
    update_conversation_ai_active: bool = False


@dataclass
class InboundPipelineResult:
    """Result of run_agent_reply_pipeline for callers to map to HTTP/WS/channel responses."""

    outcome: PipelineOutcome
    agent_result: Optional[dict] = None
    pre_moderation_result: Optional[dict] = None
    agent_response: Optional[str] = None
    agent_message_id: Optional[str] = None
    agent_message_timestamp: Optional[datetime] = None
    escalation_reason: Optional[str] = None


async def _maybe_cancel_inactivity_timer(
    conversation_id: str,
    *,
    swallow_errors: bool,
) -> None:
    if not swallow_errors:
        await cancel_timer_trigger(conversation_id)
        return
    try:
        await cancel_timer_trigger(conversation_id)
    except Exception as exc:
        logger.debug("cancel_timer_trigger failed for %s: %s", conversation_id, exc)


async def _maybe_schedule_debounced_reply(
    agent_service: AgentService,
    *,
    conversation_id: str,
    agent_user_message: str,
    last_user_plain_content: str,
) -> Optional[InboundPipelineResult]:
    """Run pre-moderation and debounce scheduling. Returns a result when the pipeline should stop."""
    settings = get_settings()
    if settings.agent_reply_debounce_seconds <= 0:
        return None

    redis_client = get_redis_client()
    if not await redis_client.ping():
        return None

    mod_early = await agent_service.run_pre_moderation_guard(
        agent_user_message, conversation_id
    )
    if mod_early and mod_early.get("escalate"):
        return InboundPipelineResult(
            outcome=PipelineOutcome.PRE_MODERATION_ESCALATED,
            pre_moderation_result=mod_early,
            escalation_reason=mod_early.get("escalation_reason"),
        )

    notify_result = await notify_user_message_saved(
        conversation_id,
        agent_user_message=agent_user_message,
        last_user_plain_content=last_user_plain_content,
    )
    if notify_result == "scheduled":
        return InboundPipelineResult(outcome=PipelineOutcome.DEBOUNCE_SCHEDULED)
    return None


async def run_agent_reply_pipeline(
    db: Any,
    conversation: Conversation,
    *,
    agent_user_message: str,
    last_user_plain_content: str,
    agent_service: AgentService,
    user_media_url: Optional[str] = None,
    options: Optional[InboundPipelineOptions] = None,
) -> InboundPipelineResult:
    """Run debounce, agent processing, escalation, and optional fallback for one user turn."""
    opts = options or InboundPipelineOptions()
    conversation_id = conversation.conversation_id

    if opts.cancel_inactivity_timer:
        await _maybe_cancel_inactivity_timer(
            conversation_id,
            swallow_errors=opts.cancel_timer_swallow_errors,
        )

    conversation_history = await build_conversation_history_for_agent(
        db,
        conversation_id,
        last_user_plain_content,
        agent_context_reset_at=conversation.agent_context_reset_at,
    )

    skip_debounce = opts.skip_debounce_for_media and bool(user_media_url)
    if not skip_debounce:
        debounce_result = await _maybe_schedule_debounced_reply(
            agent_service,
            conversation_id=conversation_id,
            agent_user_message=agent_user_message,
            last_user_plain_content=last_user_plain_content,
        )
        if debounce_result is not None:
            return debounce_result

    result = await agent_service.process_message(
        user_message=agent_user_message,
        conversation_id=conversation_id,
        conversation_history=conversation_history,
        user_media_url=user_media_url,
    )

    if result.get("escalate"):
        return InboundPipelineResult(
            outcome=PipelineOutcome.ESCALATED,
            agent_result=result,
            escalation_reason=result.get("escalation_reason"),
        )

    agent_response = result.get("response", _FALLBACK_AGENT_RESPONSE)
    agent_message_id = result.get("agent_message_id")
    agent_message_timestamp: Optional[datetime] = None

    if opts.create_fallback_agent_message and not agent_message_id:
        agent_message_id = str(uuid.uuid4())
        fallback_meta: dict = {"rag_context_used": result.get("rag_context_used", False)}
        if result.get("rag_media_url"):
            fallback_meta["media_url"] = result["rag_media_url"]
            fallback_meta["media_type"] = result.get("rag_media_type")
        agent_message = Message(
            message_id=agent_message_id,
            conversation_id=conversation_id,
            agent_id=conversation.agent_id,
            role=MessageRole.AGENT,
            content=agent_response,
            channel=conversation.channel,
            external_user_id=conversation.external_user_id,
            timestamp=utc_now(),
            metadata=fallback_meta,
        )
        await db.create_message(agent_message)
        agent_message_timestamp = agent_message.timestamp
    elif opts.create_fallback_agent_message:
        agent_message_timestamp = utc_now()

    if opts.update_conversation_ai_active:
        status_value = get_enum_value(conversation.status)
        if status_value != ConversationStatus.AI_ACTIVE.value:
            await update_conversation_with_notifications(
                db,
                conversation_id=conversation_id,
                status=ConversationStatus.AI_ACTIVE,
            )

    return InboundPipelineResult(
        outcome=PipelineOutcome.PROCESSED,
        agent_result=result,
        agent_response=agent_response,
        agent_message_id=agent_message_id,
        agent_message_timestamp=agent_message_timestamp,
    )
