"""Shared operator-echo persist + outbound id stamp (no network)."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from app.models.conversation import Conversation, ConversationStatus
from app.models.message import Message, MessageChannel, MessageRole
from app.services.channel_sender import (
    InstagramSender,
    TelegramSender,
    TikTokSender,
    ViberSender,
)
from app.services.inbound_channel import (
    persist_operator_message,
    persist_user_message_and_maybe_reply,
)
from app.utils.datetime_utils import to_utc_iso_string, utc_now
from app.utils.enum_helpers import get_enum_value
from tests.conftest import FakeDB


def _conversation(
    *,
    conversation_id: str = "conv-1",
    agent_id: str = "agent-1",
    channel: MessageChannel = MessageChannel.INSTAGRAM,
    external_user_id: str = "customer-1",
    status: ConversationStatus = ConversationStatus.AI_ACTIVE,
) -> Conversation:
    now = utc_now()
    return Conversation(
        conversation_id=conversation_id,
        agent_id=agent_id,
        channel=channel,
        external_user_id=external_user_id,
        status=status,
        created_at=now,
        updated_at=now,
        metadata={},
    )


def _agent_message(
    conversation: Conversation,
    *,
    message_id: str = "internal-out-1",
    content: str = "outbound text",
    timestamp=None,
) -> Message:
    return Message(
        message_id=message_id,
        conversation_id=conversation.conversation_id,
        agent_id=conversation.agent_id,
        role=MessageRole.AGENT,
        content=content,
        channel=conversation.channel,
        timestamp=timestamp or utc_now(),
        metadata={"source": "inbox"},
        external_user_id=conversation.external_user_id,
    )


@pytest.mark.asyncio
async def test_persist_operator_message_inserts_admin_without_status_change():
    db = FakeDB()
    conv = _conversation()
    db.conversations[conv.conversation_id] = conv
    original_update = db.update_conversation
    update_calls: list[tuple] = []

    async def spy_update(*args, **kwargs):
        update_calls.append((args, kwargs))
        return await original_update(*args, **kwargs)

    db.update_conversation = spy_update  # type: ignore[method-assign]

    async def boom_agent(*_a, **_k):
        raise AssertionError("operator persist must not load the agent")

    db.get_agent = boom_agent  # type: ignore[method-assign]

    inserted = await persist_operator_message(
        db,
        conversation=conv,
        agent_id="agent-1",
        channel=MessageChannel.INSTAGRAM,
        external_user_id="customer-1",
        text="hello from the app",
        external_message_id="mid-1",
        binding_id="bind-1",
        media_url="https://cdn.example/pic.jpg",
        media_type="image",
    )

    assert inserted is True
    assert len(db.messages) == 1
    msg = next(iter(db.messages.values()))
    assert get_enum_value(msg.role) == MessageRole.ADMIN.value
    assert msg.external_user_id == "customer-1"
    assert msg.metadata.get("source") == "external_app"
    assert msg.metadata.get("provider_message_ids") == ["mid-1"]
    assert msg.metadata.get("media_url") == "https://cdn.example/pic.jpg"
    assert msg.metadata.get("media_type") == "image"
    assert update_calls == []
    stored = db.conversations[conv.conversation_id]
    assert get_enum_value(stored.status) == ConversationStatus.AI_ACTIVE.value


@pytest.mark.asyncio
async def test_persist_operator_message_duplicate_external_id_inserts_nothing():
    db = FakeDB()
    conv = _conversation()
    db.conversations[conv.conversation_id] = conv
    kwargs = dict(
        conversation=conv,
        agent_id="agent-1",
        channel=MessageChannel.INSTAGRAM,
        external_user_id="customer-1",
        text="hello from the app",
        external_message_id="mid-dup",
        binding_id="bind-1",
    )

    assert await persist_operator_message(db, **kwargs) is True
    assert await persist_operator_message(db, **kwargs) is False
    assert len(db.messages) == 1


@pytest.mark.asyncio
async def test_stamp_then_persist_operator_message_skips_platform_id():
    db = FakeDB()
    conv = _conversation()
    db.conversations[conv.conversation_id] = conv
    outbound = _agent_message(conv, content="we already sent this")
    await db.try_create_message(outbound)

    await db.stamp_provider_message_ids(
        conv.conversation_id, outbound.message_id, ["plat-99"]
    )
    stamped = db.messages[(conv.conversation_id, outbound.message_id)]
    assert stamped.external_message_id == "plat-99"
    assert stamped.metadata.get("provider_message_ids") == ["plat-99"]
    assert get_enum_value(stamped.role) == MessageRole.AGENT.value
    assert stamped.content == "we already sent this"

    inserted = await persist_operator_message(
        db,
        conversation=conv,
        agent_id="agent-1",
        channel=MessageChannel.INSTAGRAM,
        external_user_id="customer-1",
        text="echo of a different line",
        external_message_id="plat-99",
        binding_id="bind-1",
    )
    assert inserted is False
    assert len(db.messages) == 1


@pytest.mark.asyncio
async def test_persist_operator_message_race_skips_recent_agent_same_text():
    db = FakeDB()
    conv = _conversation()
    other = _conversation(conversation_id="conv-other", external_user_id="other-user")
    db.conversations[conv.conversation_id] = conv
    db.conversations[other.conversation_id] = other
    await db.try_create_message(
        _agent_message(other, message_id="other-agent", content="same text")
    )
    await db.try_create_message(
        _agent_message(conv, message_id="local-agent", content="same text")
    )

    inserted = await persist_operator_message(
        db,
        conversation=conv,
        agent_id="agent-1",
        channel=MessageChannel.INSTAGRAM,
        external_user_id="customer-1",
        text="same text",
        external_message_id="brand-new-mid",
        binding_id="bind-1",
    )
    assert inserted is False
    assert len(db.messages) == 2


@pytest.mark.asyncio
async def test_customer_path_still_inserts_user_role():
    db = FakeDB()
    conv = _conversation(status=ConversationStatus.AI_ACTIVE)
    db.conversations[conv.conversation_id] = conv

    inserted = await persist_user_message_and_maybe_reply(
        db,
        conversation=conv,
        agent_id="agent-1",
        channel=MessageChannel.INSTAGRAM,
        external_user_id="customer-1",
        text="customer says hi",
        external_message_id="user-mid-1",
        binding_id="bind-1",
    )
    assert inserted is True
    assert len(db.messages) == 1
    msg = next(iter(db.messages.values()))
    assert get_enum_value(msg.role) == MessageRole.USER.value
    assert msg.content == "customer says hi"


@pytest.mark.asyncio
async def test_telegram_sender_stamps_message_id_on_success():
    db = FakeDB()
    conv = _conversation(channel=MessageChannel.TELEGRAM)
    db.conversations[conv.conversation_id] = conv
    outbound = _agent_message(conv)
    await db.try_create_message(outbound)
    svc = AsyncMock()
    svc.send_message = AsyncMock(
        return_value={"ok": True, "result": {"message_id": 4242}}
    )
    sender = TelegramSender(svc, db)

    await sender.send_message(
        conv.conversation_id,
        "hi",
        binding_id="bind-1",
        external_user_id="customer-1",
        message_id=outbound.message_id,
    )
    stamped = db.messages[(conv.conversation_id, outbound.message_id)]
    assert stamped.external_message_id == "4242"
    assert "4242" in stamped.metadata.get("provider_message_ids")


@pytest.mark.asyncio
async def test_viber_sender_does_not_stamp_on_error_status():
    db = FakeDB()
    conv = _conversation(channel=MessageChannel.VIBER)
    db.conversations[conv.conversation_id] = conv
    outbound = _agent_message(conv)
    await db.try_create_message(outbound)
    svc = AsyncMock()
    svc.send_message = AsyncMock(
        return_value={"status": 1, "message_token": 999}
    )
    sender = ViberSender(svc, db)

    await sender.send_message(
        conv.conversation_id,
        "hi",
        binding_id="bind-1",
        external_user_id="customer-1",
        message_id=outbound.message_id,
    )
    stamped = db.messages[(conv.conversation_id, outbound.message_id)]
    assert stamped.external_message_id is None
    assert not stamped.metadata.get("provider_message_ids")


@pytest.mark.asyncio
async def test_instagram_sender_skips_stamp_when_window_expired():
    db = FakeDB()
    conv = _conversation()
    conv.metadata = {
        "last_user_message_at": to_utc_iso_string(utc_now() - timedelta(hours=25))
    }
    db.conversations[conv.conversation_id] = conv
    outbound = _agent_message(conv)
    await db.try_create_message(outbound)
    svc = AsyncMock()
    svc.send_message = AsyncMock(return_value={"message_id": "mid.should.not.stamp"})
    sender = InstagramSender(svc, db)

    await sender.send_message(
        conv.conversation_id,
        "hi",
        binding_id="bind-1",
        external_user_id="customer-1",
        message_id=outbound.message_id,
        is_human_reply=False,
    )
    svc.send_message.assert_not_called()
    stamped = db.messages[(conv.conversation_id, outbound.message_id)]
    assert stamped.external_message_id is None


@pytest.mark.asyncio
async def test_tiktok_sender_handles_bool_and_tuple_results():
    db = FakeDB()
    conv = _conversation(channel=MessageChannel.TIKTOK)
    db.conversations[conv.conversation_id] = conv
    first = _agent_message(conv, message_id="tt-1")
    second = _agent_message(conv, message_id="tt-2")
    await db.try_create_message(first)
    await db.try_create_message(second)

    svc = AsyncMock()
    svc.messaging_enabled = True
    svc.can_send_ai_message = AsyncMock(return_value=True)
    svc.record_outbound = AsyncMock()
    svc.send_message = AsyncMock(return_value=True)
    sender = TikTokSender(svc, db)

    await sender.send_message(
        conv.conversation_id,
        "hi",
        binding_id="bind-1",
        external_user_id="customer-1",
        message_id=first.message_id,
    )
    svc.record_outbound.assert_awaited_once()
    assert db.messages[(conv.conversation_id, first.message_id)].external_message_id is None

    svc.send_message = AsyncMock(return_value=(True, ["tt-mid-7"]))
    await sender.send_message(
        conv.conversation_id,
        "hi again",
        binding_id="bind-1",
        external_user_id="customer-1",
        message_id=second.message_id,
    )
    assert db.messages[(conv.conversation_id, second.message_id)].external_message_id == "tt-mid-7"
    assert svc.record_outbound.await_count == 2
