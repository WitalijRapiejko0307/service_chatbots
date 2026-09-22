"""Telegram webhook secret_token authentication tests (no live network)."""

import json
from typing import Any, Optional
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.telegram import handle_webhook
from app.models.channel_binding import ChannelType
from app.services.channel_binding_service import (
    ChannelBindingService,
    generate_telegram_webhook_secret,
)
from app.services.telegram_service import (
    TELEGRAM_WEBHOOK_SECRET_HEADER,
    TelegramService,
    verify_telegram_webhook_secret,
)
from tests.conftest import DummySettings, FakeBindingService, FakeDB, make_binding

BINDING_ID = "11111111-1111-1111-1111-111111111111"


def _tg_payload(text: str = "hello") -> dict:
    return {
        "update_id": 1,
        "message": {
            "message_id": 42,
            "date": 1_700_000_000,
            "chat": {"id": 999},
            "from": {"id": 999, "first_name": "Ann", "username": "ann", "is_bot": False},
            "text": text,
        },
    }


class FakeSecretsWithData:
    def __init__(self) -> None:
        self.store: dict[str, dict[str, Any]] = {}
        self.updated_metadata: Optional[dict[str, Any]] = None

    async def get_channel_token(self, secret_name: str) -> str:
        return self.store.get(secret_name, {}).get("access_token", "test-token")

    async def update_channel_token(
        self, secret_name: str, access_token: str, metadata: dict[str, Any]
    ) -> None:
        current = dict(self.store.get(secret_name, {}))
        current.update({"access_token": access_token, **metadata})
        self.store[secret_name] = current
        self.updated_metadata = metadata

    async def get_channel_secret_data(self, secret_name: str) -> dict[str, Any]:
        return dict(self.store.get(secret_name, {}))


class BindingServiceWithSecret(ChannelBindingService):
    def __init__(self, binding, secrets: FakeSecretsWithData, webhook_secret: Optional[str] = None):
        super().__init__(FakeDB(), secrets)
        self._binding = binding
        binding.secret_name = f"channel:telegram:{binding.binding_id}:access_token"
        if webhook_secret:
            secrets.store[binding.secret_name] = {
                "access_token": "test-token",
                "telegram_webhook_secret": webhook_secret,
            }

    async def get_binding(self, binding_id: str):
        if binding_id == self._binding.binding_id:
            return self._binding
        return None

    async def get_access_token(self, binding_id: str) -> str:
        return "test-token"


class TelegramServiceStub(TelegramService):
    def __init__(self, binding_service: Any, webhook_secret: Optional[str] = None):
        binding = make_binding(binding_id=BINDING_ID)
        secrets = FakeSecretsWithData()
        if isinstance(binding_service, BindingServiceWithSecret):
            svc = binding_service
        else:
            svc = BindingServiceWithSecret(binding, secrets, webhook_secret)
        super().__init__(svc, FakeDB(), DummySettings())
        self.handle_webhook_event = AsyncMock()


def _webhook_test_app(telegram_service: TelegramService) -> FastAPI:
    from app.api.v1 import telegram as telegram_api

    app = FastAPI()
    app.add_api_route(
        "/api/v1/telegram/webhook/{binding_id}",
        handle_webhook,
        methods=["POST"],
    )
    app.dependency_overrides[telegram_api.get_telegram_service] = lambda: telegram_service
    return app


def test_generate_telegram_webhook_secret_format():
    secret = generate_telegram_webhook_secret()
    assert 1 <= len(secret) <= 256
    assert all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-" for c in secret)


def test_verify_telegram_webhook_secret_constant_time():
    secret = "abc123XYZ_-"
    assert verify_telegram_webhook_secret(secret, secret) is True
    assert verify_telegram_webhook_secret("wrong", secret) is False
    assert verify_telegram_webhook_secret(None, secret) is False
    assert verify_telegram_webhook_secret("", secret) is False


@pytest.mark.asyncio
async def test_webhook_with_secret_and_valid_header_processed():
    svc = TelegramServiceStub(BindingServiceWithSecret(make_binding(binding_id=BINDING_ID), FakeSecretsWithData(), "sec-valid"))
    app = _webhook_test_app(svc)
    client = TestClient(app)
    body = json.dumps(_tg_payload()).encode()

    resp = client.post(
        f"/api/v1/telegram/webhook/{BINDING_ID}",
        content=body,
        headers={
            "Content-Type": "application/json",
            TELEGRAM_WEBHOOK_SECRET_HEADER: "sec-valid",
        },
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    svc.handle_webhook_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_webhook_with_secret_and_invalid_header_403():
    svc = TelegramServiceStub(
        BindingServiceWithSecret(make_binding(binding_id=BINDING_ID), FakeSecretsWithData(), "sec-valid")
    )
    app = _webhook_test_app(svc)
    client = TestClient(app)

    resp = client.post(
        f"/api/v1/telegram/webhook/{BINDING_ID}",
        content=json.dumps(_tg_payload()).encode(),
        headers={
            "Content-Type": "application/json",
            TELEGRAM_WEBHOOK_SECRET_HEADER: "wrong-secret",
        },
    )

    assert resp.status_code == 403
    svc.handle_webhook_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_webhook_with_secret_and_missing_header_403():
    svc = TelegramServiceStub(
        BindingServiceWithSecret(make_binding(binding_id=BINDING_ID), FakeSecretsWithData(), "sec-valid")
    )
    app = _webhook_test_app(svc)
    client = TestClient(app)

    resp = client.post(
        f"/api/v1/telegram/webhook/{BINDING_ID}",
        content=json.dumps(_tg_payload()).encode(),
        headers={"Content-Type": "application/json"},
    )

    assert resp.status_code == 403
    svc.handle_webhook_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_webhook_without_secret_processed():
    svc = TelegramServiceStub(
        BindingServiceWithSecret(make_binding(binding_id=BINDING_ID), FakeSecretsWithData(), None)
    )
    app = _webhook_test_app(svc)
    client = TestClient(app)

    resp = client.post(
        f"/api/v1/telegram/webhook/{BINDING_ID}",
        content=json.dumps(_tg_payload()).encode(),
        headers={"Content-Type": "application/json"},
    )

    assert resp.status_code == 200
    svc.handle_webhook_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_verify_binding_generates_secret_and_passes_to_set_webhook():
    from app.services.channel_binding_service import ChannelBindingService

    db = FakeDB()
    binding = make_binding(channel=ChannelType.TELEGRAM, binding_id=BINDING_ID)
    binding.secret_name = f"channel:telegram:{BINDING_ID}:access_token"
    secrets = FakeSecretsWithData()
    secrets.store[binding.secret_name] = {"access_token": "bot-token"}

    svc = ChannelBindingService(db, secrets)
    svc.get_binding = AsyncMock(return_value=binding)  # type: ignore[method-assign]
    svc.get_access_token = AsyncMock(return_value="bot-token")  # type: ignore[method-assign]
    svc.update_binding = AsyncMock(return_value=binding)  # type: ignore[method-assign]

    captured: dict[str, Any] = {}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, **kwargs):
            return type("Resp", (), {"json": lambda self: {"ok": True, "result": {"id": 1, "username": "bot"}}})()

        async def post(self, url, json=None, **kwargs):
            captured["url"] = url
            captured["json"] = json
            return type("Resp", (), {"json": lambda self: {"ok": True}})()

    with patch("httpx.AsyncClient", return_value=_Client()):
        with patch("app.config.get_settings", return_value=DummySettings()):
            ok = await svc.verify_binding(BINDING_ID)

    assert ok is True
    stored_secret = secrets.store[binding.secret_name].get("telegram_webhook_secret")
    assert stored_secret
    assert len(stored_secret) >= 1
    assert captured["json"]["secret_token"] == stored_secret
