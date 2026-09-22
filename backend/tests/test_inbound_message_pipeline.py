"""Unit tests for shared inbound message agent-reply pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.conversation import Conversation, ConversationStatus, MarketingStatus
from app.models.message import Message, MessageChannel, MessageRole
from app.services.inbound_message_pipeline import (
    InboundPipelineOptions,
    PipelineOutcome,
    run_agent_reply_pipeline,
)
from app.utils.enum_helpers import get_enum_value
from tests.conftest import DummySettings, FakeDB

FIXED_NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
AGENT_ID = "agent-1"


def _settings(*, debounce_seconds: int = 0) -> DummySettings:
    settings = DummySettings()
    settings.agent_reply_debounce_seconds = debounce_seconds
    return settings


class PipelineFakeDB(FakeDB):
    async def create_message(self, message: Message) -> Message:
        await self.try_create_message(message)
        return message


def _conversation(
    *,
    conversation_id: str = "conv-1",
    status: ConversationStatus = ConversationStatus.AI_ACTIVE,
) -> Conversation:
    return Conversation(
        conversation_id=conversation_id,
        agent_id=AGENT_ID,
        channel=MessageChannel.WEB_CHAT,
        status=status,
        marketing_status=MarketingStatus.NEW,
        created_at=FIXED_NOW,
        updated_at=FIXED_NOW,
    )


def _agent_service(**process_message_return) -> MagicMock:
    service = MagicMock()
    service.run_pre_moderation_guard = AsyncMock(return_value=None)
    service.process_message = AsyncMock(return_value=process_message_return)
    return service


@pytest.mark.asyncio
async def test_pipeline_successful_agent_reply():
    db = PipelineFakeDB()
    conv = _conversation()
    db.conversations[conv.conversation_id] = conv
    service = _agent_service(
        response="Hello from AI",
        agent_message_id="agent-msg-1",
        escalate=False,
    )

    with patch(
        "app.services.inbound_message_pipeline.get_settings",
        return_value=_settings(),
    ):
        result = await run_agent_reply_pipeline(
            db,
            conv,
            agent_user_message="Hi",
            last_user_plain_content="Hi",
            agent_service=service,
        )

    assert result.outcome == PipelineOutcome.PROCESSED
    assert result.agent_response == "Hello from AI"
    assert result.agent_message_id == "agent-msg-1"
    service.process_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_pipeline_handoff_skipped_by_caller():
    """Callers skip the pipeline when conversation is in handoff; this test documents that contract."""
    db = PipelineFakeDB()
    conv = _conversation(status=ConversationStatus.HUMAN_ACTIVE)
    db.conversations[conv.conversation_id] = conv
    service = _agent_service(response="nope", agent_message_id="x", escalate=False)

    with patch(
        "app.services.inbound_message_pipeline.get_settings",
        return_value=_settings(),
    ):
        result = await run_agent_reply_pipeline(
            db,
            conv,
            agent_user_message="Hi",
            last_user_plain_content="Hi",
            agent_service=service,
        )

    assert result.outcome == PipelineOutcome.PROCESSED
    service.process_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_pipeline_escalation_from_agent():
    db = PipelineFakeDB()
    conv = _conversation()
    db.conversations[conv.conversation_id] = conv
    service = _agent_service(
        response=None,
        escalate=True,
        escalation_reason="User requested human",
    )

    with patch(
        "app.services.inbound_message_pipeline.get_settings",
        return_value=_settings(),
    ):
        result = await run_agent_reply_pipeline(
            db,
            conv,
            agent_user_message="Talk to a human",
            last_user_plain_content="Talk to a human",
            agent_service=service,
        )

    assert result.outcome == PipelineOutcome.ESCALATED
    assert result.escalation_reason == "User requested human"


@pytest.mark.asyncio
async def test_pipeline_fallback_when_no_agent_message_id():
    db = PipelineFakeDB()
    conv = _conversation()
    db.conversations[conv.conversation_id] = conv
    service = _agent_service(agent_message_id=None, escalate=False)

    with patch(
        "app.services.inbound_message_pipeline.get_settings",
        return_value=_settings(),
    ):
        result = await run_agent_reply_pipeline(
            db,
            conv,
            agent_user_message="Trigger fallback",
            last_user_plain_content="Trigger fallback",
            agent_service=service,
            options=InboundPipelineOptions(create_fallback_agent_message=True),
        )

    assert result.outcome == PipelineOutcome.PROCESSED
    assert result.agent_response == "I apologize, but I couldn't generate a response."
    assert result.agent_message_id is not None
    assert len(db.messages) == 1
    msg = next(iter(db.messages.values()))
    assert get_enum_value(msg.role) == MessageRole.AGENT.value


@pytest.mark.asyncio
async def test_pipeline_pre_moderation_escalation():
    db = PipelineFakeDB()
    conv = _conversation()
    db.conversations[conv.conversation_id] = conv
    service = _agent_service()
    service.run_pre_moderation_guard = AsyncMock(
        return_value={
            "escalate": True,
            "escalation_reason": "Content moderation violation",
        }
    )
    redis = AsyncMock()
    redis.ping = AsyncMock(return_value=True)

    with (
        patch(
            "app.services.inbound_message_pipeline.get_settings",
            return_value=_settings(debounce_seconds=2),
        ),
        patch(
            "app.services.inbound_message_pipeline.get_redis_client",
            return_value=redis,
        ),
    ):
        result = await run_agent_reply_pipeline(
            db,
            conv,
            agent_user_message="bad words",
            last_user_plain_content="bad words",
            agent_service=service,
        )

    assert result.outcome == PipelineOutcome.PRE_MODERATION_ESCALATED
    assert result.escalation_reason == "Content moderation violation"
    service.process_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_pipeline_debounce_scheduled():
    db = PipelineFakeDB()
    conv = _conversation()
    db.conversations[conv.conversation_id] = conv
    service = _agent_service()
    redis = AsyncMock()
    redis.ping = AsyncMock(return_value=True)

    with (
        patch(
            "app.services.inbound_message_pipeline.get_settings",
            return_value=_settings(debounce_seconds=2),
        ),
        patch(
            "app.services.inbound_message_pipeline.get_redis_client",
            return_value=redis,
        ),
        patch(
            "app.services.inbound_message_pipeline.notify_user_message_saved",
            AsyncMock(return_value="scheduled"),
        ),
    ):
        result = await run_agent_reply_pipeline(
            db,
            conv,
            agent_user_message="Hi",
            last_user_plain_content="Hi",
            agent_service=service,
        )

    assert result.outcome == PipelineOutcome.DEBOUNCE_SCHEDULED
    service.process_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_pipeline_updates_ai_active_status():
    db = PipelineFakeDB()
    conv = _conversation(status=ConversationStatus.NEEDS_HUMAN)
    db.conversations[conv.conversation_id] = conv
    service = _agent_service(
        response="Back to AI",
        agent_message_id="agent-msg-2",
        escalate=False,
    )

    with patch(
        "app.services.inbound_message_pipeline.get_settings",
        return_value=_settings(),
    ):
        await run_agent_reply_pipeline(
            db,
            conv,
            agent_user_message="Continue",
            last_user_plain_content="Continue",
            agent_service=service,
            options=InboundPipelineOptions(update_conversation_ai_active=True),
        )

    assert get_enum_value(db.conversations[conv.conversation_id].status) == (
        ConversationStatus.AI_ACTIVE.value
    )
