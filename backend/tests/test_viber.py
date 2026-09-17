"""Viber HMAC and conversation_started tests (no live network)."""

import hashlib
import hmac
from unittest.mock import AsyncMock, patch

import pytest

from app.models.channel_binding import ChannelType
from app.services.viber_service import ViberService, verify_viber_signature
from tests.conftest import DummySettings, FakeBindingService, FakeDB, make_binding


def test_viber_hmac_accept():
    token = "pa-auth-token"
    body = b'{"event":"message"}'
    sig = hmac.new(token.encode(), body, hashlib.sha256).hexdigest()
    assert verify_viber_signature(body, sig, token) is True


def test_viber_hmac_reject():
    body = b'{"event":"message"}'
    sig = hmac.new(b"wrong", body, hashlib.sha256).hexdigest()
    assert verify_viber_signature(body, sig, "pa-auth-token") is False
    assert verify_viber_signature(body, "", "pa-auth-token") is False


@pytest.mark.asyncio
async def test_viber_conversation_started_does_not_500():
    db = FakeDB()
    binding = make_binding(channel=ChannelType.VIBER, account_id="pa-1")
    svc = ViberService(FakeBindingService(binding), db, DummySettings())
    payload = {
        "event": "conversation_started",
        "user": {"id": "viber-user-1", "name": "Pat"},
    }
    with patch.object(svc, "send_message", new_callable=AsyncMock) as send:
        await svc.handle_webhook_event(payload, binding.binding_id)
        send.assert_awaited()

    assert len(db.conversations) == 1
    conv = next(iter(db.conversations.values()))
    assert conv.external_user_id == "viber-user-1"
    assert conv.external_user_name == "Pat"


def _viber_message_payload(text: str = "hello", token: int = 555, user_id: str = "viber-user-1") -> dict:
    return {
        "event": "message",
        "message_token": token,
        "sender": {"id": user_id, "name": "Pat"},
        "message": {"type": "text", "text": text},
    }


@pytest.mark.asyncio
async def test_viber_duplicate_message_token_does_not_double_insert():
    db = FakeDB()
    binding = make_binding(channel=ChannelType.VIBER, account_id="pa-1")
    svc = ViberService(FakeBindingService(binding), db, DummySettings())
    payload = _viber_message_payload()

    await svc.handle_webhook_event(payload, binding.binding_id)
    await svc.handle_webhook_event(payload, binding.binding_id)

    assert len(db.messages) == 1
    assert len(db.conversations) == 1


@pytest.mark.asyncio
async def test_viber_duplicate_inbound_does_not_call_agent():
    db = FakeDB()
    binding = make_binding(channel=ChannelType.VIBER, account_id="pa-1")
    svc = ViberService(FakeBindingService(binding), db, DummySettings())
    payload = _viber_message_payload(token=777)

    await svc.handle_webhook_event(payload, binding.binding_id)
    assert len(db.messages) == 1

    async def boom(*_a, **_k):
        raise AssertionError("agent must not run on duplicate inbound")

    db.get_agent = boom  # type: ignore[method-assign]
    await svc.handle_webhook_event(payload, binding.binding_id)
    assert len(db.messages) == 1
