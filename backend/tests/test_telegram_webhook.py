"""Telegram inbound webhook tests (no live network)."""

import pytest

from app.models.conversation import Conversation, ConversationStatus
from app.models.message import MessageChannel
from app.services.telegram_service import TelegramService
from app.utils.datetime_utils import utc_now
from tests.conftest import DummySettings, FakeBindingService, FakeDB, make_binding


def _tg_payload(text: str, message_id: int = 42, chat_id: int = 999) -> dict:
    return {
        "update_id": 1,
        "message": {
            "message_id": message_id,
            "date": 1_700_000_000,
            "chat": {"id": chat_id},
            "from": {"id": chat_id, "first_name": "Ann", "username": "ann", "is_bot": False},
            "text": text,
        },
    }


@pytest.mark.asyncio
async def test_telegram_inbound_creates_conversation_and_message():
    db = FakeDB()
    binding = make_binding()
    svc = TelegramService(FakeBindingService(binding), db, DummySettings())

    await svc.handle_webhook_event(_tg_payload("hello"), binding.binding_id)

    assert len(db.conversations) == 1
    conv = next(iter(db.conversations.values()))
    assert conv.agent_id == "agent-1"
    assert conv.channel in (MessageChannel.TELEGRAM, MessageChannel.TELEGRAM.value)
    assert conv.external_user_id == "999"
    assert len(db.messages) == 1
    msg = next(iter(db.messages.values()))
    assert msg.content == "hello"
    assert msg.external_message_id == "42"


@pytest.mark.asyncio
async def test_telegram_duplicate_message_id_does_not_double_insert():
    db = FakeDB()
    binding = make_binding()
    svc = TelegramService(FakeBindingService(binding), db, DummySettings())
    payload = _tg_payload("hello", message_id=7)

    await svc.handle_webhook_event(payload, binding.binding_id)
    await svc.handle_webhook_event(payload, binding.binding_id)

    assert len(db.messages) == 1
    assert len(db.conversations) == 1


@pytest.mark.asyncio
async def test_telegram_needs_human_skips_ai():
    db = FakeDB()
    binding = make_binding()
    existing = Conversation(
        conversation_id="conv-open",
        agent_id="agent-1",
        channel=MessageChannel.TELEGRAM,
        external_user_id="999",
        status=ConversationStatus.NEEDS_HUMAN,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db.conversations[existing.conversation_id] = existing

    async def boom(*_a, **_k):
        raise AssertionError("agent must not run when conversation is NEEDS_HUMAN")

    db.get_agent = boom  # type: ignore[method-assign]
    svc = TelegramService(FakeBindingService(binding), db, DummySettings())
    await svc.handle_webhook_event(_tg_payload("need a human"), binding.binding_id)

    assert len(db.messages) == 1
    conv = db.conversations["conv-open"]
    assert conv.status in (ConversationStatus.NEEDS_HUMAN, ConversationStatus.NEEDS_HUMAN.value)


@pytest.mark.asyncio
async def test_telegram_duplicate_inbound_does_not_call_agent():
    db = FakeDB()
    binding = make_binding()
    svc = TelegramService(FakeBindingService(binding), db, DummySettings())
    payload = _tg_payload("hello", message_id=11)

    await svc.handle_webhook_event(payload, binding.binding_id)
    assert len(db.messages) == 1

    async def boom(*_a, **_k):
        raise AssertionError("agent must not run on duplicate inbound")

    db.get_agent = boom  # type: ignore[method-assign]
    await svc.handle_webhook_event(payload, binding.binding_id)
    assert len(db.messages) == 1
