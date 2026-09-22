"""Channel adapter tests for operator echo vs customer inbound (no live network)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.models.channel_binding import ChannelType
from app.models.conversation import Conversation, ConversationStatus
from app.models.message import MessageChannel, MessageRole
from app.services.instagram_service import InstagramService
from app.services.telegram_service import TelegramService
from app.services.tiktok_service import TikTokService
from app.services.viber_service import ViberService
from app.utils.datetime_utils import utc_now
from app.utils.enum_helpers import get_enum_value
from tests.conftest import DummySettings, FakeBindingService, FakeDB, make_binding


def _messages(db: FakeDB) -> list:
    return list(db.messages.values())


def _ig_event(
    *,
    mid: str = "mid-1",
    text: str = "hello",
    sender: str = "user-1",
    recipient: str = "bot-1",
    is_echo: bool = False,
    is_self: bool = False,
    attachments: list | None = None,
    timestamp_ms: int | None = 1_700_000_000_000,
) -> dict:
    message: dict = {"mid": mid, "text": text}
    if is_echo:
        message["is_echo"] = True
    if is_self:
        message["is_self"] = True
    if attachments:
        message["attachments"] = attachments
        if not text:
            message.pop("text", None)
    event: dict = {
        "sender": {"id": sender},
        "recipient": {"id": recipient},
        "message": message,
    }
    if timestamp_ms is not None:
        event["timestamp"] = timestamp_ms
    return {
        "object": "instagram",
        "entry": [{"messaging": [event]}],
    }


def _ig_service(db: FakeDB, account_id: str = "bot-1") -> InstagramService:
    binding = make_binding(channel=ChannelType.INSTAGRAM, account_id=account_id)
    svc = InstagramService(FakeBindingService(binding), db, DummySettings())
    svc.refresh_user_profile = AsyncMock(return_value=(None, None))  # type: ignore[method-assign]
    return svc


@pytest.mark.asyncio
async def test_instagram_echo_text_stored_as_admin_on_customer_conversation():
    db = FakeDB()
    existing = Conversation(
        conversation_id="conv-ig",
        agent_id="agent-1",
        channel=MessageChannel.INSTAGRAM,
        external_user_id="customer-1",
        status=ConversationStatus.HUMAN_ACTIVE,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db.conversations[existing.conversation_id] = existing
    svc = _ig_service(db)
    payload = _ig_event(
        mid="echo-text-1",
        text="typed in the app",
        sender="bot-1",
        recipient="customer-1",
        is_echo=True,
    )

    with patch(
        "app.services.instagram_service.persist_user_message_and_maybe_reply",
        new_callable=AsyncMock,
    ) as persist_user:
        await svc.handle_webhook_event(payload)
        persist_user.assert_not_called()

    conv = db.conversations["conv-ig"]
    assert conv.status in (ConversationStatus.HUMAN_ACTIVE, ConversationStatus.HUMAN_ACTIVE.value)
    assert conv.external_user_id == "customer-1"
    msgs = _messages(db)
    assert len(msgs) == 1
    msg = msgs[0]
    assert get_enum_value(msg.role) == MessageRole.ADMIN.value
    assert msg.content == "typed in the app"
    assert msg.external_user_id == "customer-1"
    assert msg.external_message_id == "echo-text-1"
    assert not any(get_enum_value(m.role) == MessageRole.USER.value for m in msgs)


@pytest.mark.asyncio
async def test_instagram_echo_attachment_maps_image_like_inbound():
    db = FakeDB()
    svc = _ig_service(db)
    payload = _ig_event(
        mid="echo-img-1",
        text="",
        sender="bot-1",
        recipient="customer-1",
        is_echo=True,
        attachments=[
            {"type": "image", "payload": {"url": "https://cdn.example/p.jpg"}},
        ],
    )

    await svc.handle_webhook_event(payload)

    msgs = _messages(db)
    assert len(msgs) == 1
    msg = msgs[0]
    assert get_enum_value(msg.role) == MessageRole.ADMIN.value
    assert msg.media_url == "https://cdn.example/p.jpg"
    assert msg.media_type == "image"
    conv = next(iter(db.conversations.values()))
    assert conv.external_user_id == "customer-1"


@pytest.mark.asyncio
async def test_instagram_echo_duplicate_mid_inserts_once():
    db = FakeDB()
    svc = _ig_service(db)
    payload = _ig_event(
        mid="echo-dup-1",
        text="same line",
        sender="bot-1",
        recipient="customer-1",
        is_echo=True,
    )

    await svc.handle_webhook_event(payload)
    await svc.handle_webhook_event(payload)

    assert len(db.messages) == 1
    assert get_enum_value(_messages(db)[0].role) == MessageRole.ADMIN.value


@pytest.mark.asyncio
async def test_instagram_inbound_customer_still_creates_user_row():
    db = FakeDB()
    svc = _ig_service(db)
    payload = _ig_event(
        mid="cust-1",
        text="hi from customer",
        sender="customer-1",
        recipient="bot-1",
    )

    try:
        await svc.handle_webhook_event(payload)
    except Exception:
        pass

    msgs = _messages(db)
    assert len(msgs) == 1
    msg = msgs[0]
    assert get_enum_value(msg.role) == MessageRole.USER.value
    assert msg.content == "hi from customer"
    assert msg.external_user_id == "customer-1"
    conv = next(iter(db.conversations.values()))
    assert conv.external_user_id == "customer-1"


@pytest.mark.asyncio
async def test_instagram_echo_unknown_business_inserts_nothing():
    db = FakeDB()
    svc = _ig_service(db, account_id="bot-1")
    svc.resolve_account_from_token = AsyncMock(return_value=None)  # type: ignore[method-assign]
    payload = _ig_event(
        mid="echo-unknown",
        text="from another account",
        sender="unknown-biz",
        recipient="customer-1",
        is_echo=True,
    )

    await svc.handle_webhook_event(payload)

    assert db.messages == {}
    assert db.conversations == {}


def _tg_payload(*, text: str = "hello", message_id: int = 42, chat_id: int = 999, is_bot: bool = False) -> dict:
    return {
        "update_id": 1,
        "message": {
            "message_id": message_id,
            "date": 1_700_000_000,
            "chat": {"id": chat_id},
            "from": {
                "id": chat_id,
                "first_name": "Ann",
                "username": "ann",
                "is_bot": is_bot,
            },
            "text": text,
        },
    }


@pytest.mark.asyncio
async def test_telegram_normal_user_message_creates_user_row():
    db = FakeDB()
    binding = make_binding()
    svc = TelegramService(FakeBindingService(binding), db, DummySettings())

    await svc.handle_webhook_event(_tg_payload(), binding.binding_id)

    msgs = _messages(db)
    assert len(msgs) == 1
    assert get_enum_value(msgs[0].role) == MessageRole.USER.value
    assert msgs[0].content == "hello"
    assert msgs[0].external_user_id == "999"


@pytest.mark.asyncio
async def test_telegram_is_bot_inserts_nothing():
    db = FakeDB()
    binding = make_binding()
    svc = TelegramService(FakeBindingService(binding), db, DummySettings())

    await svc.handle_webhook_event(_tg_payload(is_bot=True), binding.binding_id)

    assert db.messages == {}
    assert db.conversations == {}


@pytest.mark.asyncio
async def test_viber_normal_message_creates_user_row():
    db = FakeDB()
    binding = make_binding(channel=ChannelType.VIBER, account_id="pa-1")
    svc = ViberService(FakeBindingService(binding), db, DummySettings())
    payload = {
        "event": "message",
        "message_token": 555,
        "sender": {"id": "viber-user-1", "name": "Pat"},
        "message": {"type": "text", "text": "hello"},
    }

    await svc.handle_webhook_event(payload, binding.binding_id)

    msgs = _messages(db)
    assert len(msgs) == 1
    assert get_enum_value(msgs[0].role) == MessageRole.USER.value
    assert msgs[0].content == "hello"
    assert msgs[0].external_user_id == "viber-user-1"
    assert not any(get_enum_value(m.role) == MessageRole.ADMIN.value for m in msgs)


@pytest.mark.asyncio
async def test_tiktok_normal_inbound_creates_user_row_not_admin():
    db = FakeDB()
    binding = make_binding(channel=ChannelType.TIKTOK, account_id="tt-1")
    settings = DummySettings()
    settings.tiktok_messaging_enabled = True
    svc = TikTokService(FakeBindingService(binding), db, settings)
    payload = {
        "event": "im_receive_msg",
        "data": {
            "from_user_id": "user-1",
            "text": "hello",
            "message_id": "msg-1",
        },
    }

    await svc.handle_webhook_event(payload, binding.binding_id)

    msgs = _messages(db)
    assert len(msgs) == 1
    assert get_enum_value(msgs[0].role) == MessageRole.USER.value
    assert msgs[0].external_user_id == "user-1"
    assert not any(get_enum_value(m.role) == MessageRole.ADMIN.value for m in msgs)
