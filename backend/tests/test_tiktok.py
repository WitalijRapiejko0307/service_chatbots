"""TikTok disabled-mode tests."""

from unittest.mock import AsyncMock, patch

import pytest

from app.models.channel_binding import ChannelType
from app.services.channel_binding_service import ChannelBindingService
from app.services.tiktok_service import TikTokService
from tests.conftest import DummySettings, FakeBindingService, FakeDB, make_binding


class FakeSecrets:
    async def create_channel_token_secret(self, **kwargs):
        return "secret-name"

    async def get_channel_token(self, name):
        return "tok"

    async def update_channel_token(self, **kwargs):
        return None

    async def delete_channel_token_secret(self, name):
        return None


@pytest.mark.asyncio
async def test_tiktok_disabled_send_is_noop():
    db = FakeDB()
    binding = make_binding(channel=ChannelType.TIKTOK, account_id="tt-1")
    settings = DummySettings()
    settings.tiktok_messaging_enabled = False
    svc = TikTokService(FakeBindingService(binding), db, settings)

    with patch("httpx.AsyncClient") as client_cls:
        result = await svc.send_message(binding.binding_id, "user-1", "hi")
        client_cls.assert_not_called()
    assert result is False


@pytest.mark.asyncio
async def test_tiktok_create_binding_pending_access():
    db = FakeDB()
    db.create_channel_binding = AsyncMock(side_effect=lambda b: b)
    settings = DummySettings()
    settings.tiktok_messaging_enabled = False

    with patch("app.config.get_settings", return_value=settings):
        svc = ChannelBindingService(db, FakeSecrets())
        binding = await svc.create_binding(
            agent_id="agent-1",
            channel_type="tiktok",
            channel_account_id="biz-1",
            access_token="tok",
            metadata={},
        )

    assert binding.metadata.get("pending_access") is True
    assert binding.is_verified is False


def _tt_payload(text: str = "hello", message_id: str = "msg-1", user_id: str = "user-1") -> dict:
    return {
        "event": "im_receive_msg",
        "data": {
            "from_user_id": user_id,
            "text": text,
            "message_id": message_id,
        },
    }


@pytest.mark.asyncio
async def test_tiktok_duplicate_message_id_does_not_double_insert():
    db = FakeDB()
    binding = make_binding(channel=ChannelType.TIKTOK, account_id="tt-1")
    settings = DummySettings()
    settings.tiktok_messaging_enabled = True
    svc = TikTokService(FakeBindingService(binding), db, settings)
    payload = _tt_payload()

    await svc.handle_webhook_event(payload, binding.binding_id)
    await svc.handle_webhook_event(payload, binding.binding_id)

    assert len(db.messages) == 1
    assert len(db.conversations) == 1


@pytest.mark.asyncio
async def test_tiktok_duplicate_inbound_does_not_call_agent():
    db = FakeDB()
    binding = make_binding(channel=ChannelType.TIKTOK, account_id="tt-1")
    settings = DummySettings()
    settings.tiktok_messaging_enabled = True
    svc = TikTokService(FakeBindingService(binding), db, settings)
    payload = _tt_payload(message_id="msg-dup")

    await svc.handle_webhook_event(payload, binding.binding_id)
    assert len(db.messages) == 1

    async def boom(*_a, **_k):
        raise AssertionError("agent must not run on duplicate inbound")

    db.get_agent = boom  # type: ignore[method-assign]
    await svc.handle_webhook_event(payload, binding.binding_id)
    assert len(db.messages) == 1


@pytest.mark.asyncio
async def test_tiktok_media_send_falls_back_to_text():
    db = FakeDB()
    binding = make_binding(channel=ChannelType.TIKTOK, account_id="tt-1")
    settings = DummySettings()
    settings.tiktok_messaging_enabled = True
    svc = TikTokService(FakeBindingService(binding, token="tok"), db, settings)

    calls: list[dict] = []

    class _Resp:
        def __init__(self, status_code: int, payload: dict, text: str = "ok"):
            self.status_code = status_code
            self._payload = payload
            self.text = text

        def json(self):
            return self._payload

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None, headers=None):
            calls.append(json or {})
            if json and json.get("media_url"):
                return _Resp(400, {"code": 1, "message": "media not supported"}, "media fail token=act.secret")
            return _Resp(200, {"code": 0})

    with patch("httpx.AsyncClient", return_value=_Client()):
        result = await svc.send_message(
            binding.binding_id,
            "user-1",
            "caption",
            media_url="https://cdn.example/img.jpg",
            media_type="image",
        )

    assert result is True
    assert len(calls) == 2
    assert calls[0]["message_type"] in ("image", "file")
    assert calls[0].get("media_url")
    assert calls[1]["message_type"] == "text"
    assert calls[1]["text"] == "caption"
    assert "media_url" not in calls[1]
