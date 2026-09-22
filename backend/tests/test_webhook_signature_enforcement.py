"""Webhook signature enforcement: fail-closed in production, warn elsewhere."""

from __future__ import annotations

import hashlib
import hmac
import logging
from contextlib import ExitStack, contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.channel_binding import ChannelType
from app.services.instagram_service import InstagramService
from tests.conftest import DummySettings, FakeBindingService, FakeDB, make_binding

BINDING_ID = "11111111-1111-1111-1111-111111111111"
IG_BODY = b'{"object":"instagram","entry":[]}'
VIBER_BODY = b'{"event":"message"}'
TIKTOK_BODY = b'{"event":"im_receive_msg"}'
IG_SECRET = "ig-app-secret"
VIBER_TOKEN = "viber-auth-token"
TIKTOK_SECRET = "tiktok-app-secret"


def _settings(environment: str = "development", **overrides) -> DummySettings:
    settings = DummySettings()
    settings.environment = environment
    for key, value in overrides.items():
        setattr(settings, key, value)
    return settings


def _ig_signature(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _viber_signature(body: bytes, token: str) -> str:
    return hmac.new(token.encode(), body, hashlib.sha256).hexdigest()


def _tiktok_signature(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@contextmanager
def _patch_settings(settings: DummySettings, module: str | None = None):
    targets = [
        "app.api.webhook_guards.get_settings",
        "app.api.v1.instagram.get_settings",
        "app.config.get_settings",
    ]
    if module in ("instagram", "tiktok"):
        targets.append(f"app.api.v1.{module}.get_settings")
    with ExitStack() as stack:
        for target in targets:
            stack.enter_context(patch(target, return_value=settings))
        yield


@contextmanager
def _instagram_client(
    settings: DummySettings,
    *,
    app_secret: str = "",
):
    from app.api.v1.instagram import get_instagram_service, router
    from app.dependencies import CommonDependencies

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    binding = make_binding(channel=ChannelType.INSTAGRAM)
    real_svc = InstagramService(FakeBindingService(binding), FakeDB(), settings)
    fake_svc = MagicMock()
    fake_svc.verify_webhook_signature = real_svc.verify_webhook_signature
    fake_svc.handle_webhook_event = AsyncMock()

    class _Deps:
        def __init__(self) -> None:
            self.db = FakeDB()

    app.dependency_overrides[get_instagram_service] = lambda: fake_svc
    app.dependency_overrides[CommonDependencies] = lambda: _Deps()

    with (
        _patch_settings(settings, "instagram"),
        patch(
            "app.api.v1.instagram._get_instagram_app_secret",
            AsyncMock(return_value=app_secret),
        ),
        patch("app.services.webhook_event_store.add_webhook_event"),
    ):
        yield TestClient(app), fake_svc


@pytest.fixture
def instagram_client_factory():
    @contextmanager
    def _factory(settings: DummySettings, *, app_secret: str = ""):
        with _instagram_client(settings, app_secret=app_secret) as (client, svc):
            yield client, svc

    return _factory


@contextmanager
def _viber_client(
    settings: DummySettings,
    *,
    token: str | None = None,
):
    from app.api.v1.viber import get_viber_service, router
    from app.dependencies import CommonDependencies

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    fake_svc = MagicMock()
    fake_svc.handle_webhook_event = AsyncMock()

    binding_svc = AsyncMock()
    if token is None:
        binding_svc.get_access_token = AsyncMock(side_effect=Exception("no token"))
    else:
        binding_svc.get_access_token = AsyncMock(return_value=token)

    class _Deps:
        def __init__(self) -> None:
            self.db = FakeDB()

    app.dependency_overrides[get_viber_service] = lambda: fake_svc
    app.dependency_overrides[CommonDependencies] = lambda: _Deps()

    with (
        _patch_settings(settings, "viber"),
        patch("app.api.v1.viber.get_secrets_manager", return_value=MagicMock()),
        patch("app.api.v1.viber.ChannelBindingService", return_value=binding_svc),
        patch("app.services.webhook_event_store.add_webhook_event"),
    ):
        yield TestClient(app), fake_svc


@pytest.fixture
def viber_client_factory():
    @contextmanager
    def _factory(settings: DummySettings, *, token: str | None = None):
        with _viber_client(settings, token=token) as (client, svc):
            yield client, svc

    return _factory


@contextmanager
def _tiktok_client(
    settings: DummySettings,
):
    from app.api.v1.tiktok import get_tiktok_service, router
    from app.dependencies import CommonDependencies

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    fake_svc = MagicMock()
    fake_svc.handle_webhook_event = AsyncMock()

    class _Deps:
        def __init__(self) -> None:
            self.db = FakeDB()

    app.dependency_overrides[get_tiktok_service] = lambda: fake_svc
    app.dependency_overrides[CommonDependencies] = lambda: _Deps()

    with _patch_settings(settings, "tiktok"):
        yield TestClient(app), fake_svc


@pytest.fixture
def tiktok_client_factory():
    @contextmanager
    def _factory(settings: DummySettings):
        with _tiktok_client(settings) as (client, svc):
            yield client, svc

    return _factory


# --- Instagram ---


def test_instagram_production_missing_secret_returns_401(instagram_client_factory):
    settings = _settings("production")
    with instagram_client_factory(settings, app_secret="") as (client, svc):
        resp = client.post(
            "/api/v1/instagram/webhook",
            content=IG_BODY,
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code == 401
    svc.handle_webhook_event.assert_not_called()


def test_instagram_development_missing_secret_warns_and_processes(
    instagram_client_factory, caplog
):
    settings = _settings("development")
    with instagram_client_factory(settings, app_secret="") as (client, svc):
        with caplog.at_level(logging.WARNING):
            resp = client.post(
                "/api/v1/instagram/webhook",
                content=IG_BODY,
                headers={"Content-Type": "application/json"},
            )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    svc.handle_webhook_event.assert_awaited_once()
    assert any(
        "webhook accepted without signature verification — instagram" in r.message
        for r in caplog.records
    )


def test_instagram_valid_signature_processed(instagram_client_factory):
    settings = _settings("development")
    with instagram_client_factory(settings, app_secret=IG_SECRET) as (client, svc):
        resp = client.post(
            "/api/v1/instagram/webhook",
            content=IG_BODY,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": _ig_signature(IG_BODY, IG_SECRET),
            },
        )
    assert resp.status_code == 200
    svc.handle_webhook_event.assert_awaited_once()


def test_instagram_invalid_signature_rejected(instagram_client_factory):
    settings = _settings("development")
    with instagram_client_factory(settings, app_secret=IG_SECRET) as (client, svc):
        resp = client.post(
            "/api/v1/instagram/webhook",
            content=IG_BODY,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": "sha256=deadbeef",
            },
        )
    assert resp.status_code == 403
    svc.handle_webhook_event.assert_not_called()


# --- Viber ---


def test_viber_production_missing_token_returns_401(viber_client_factory):
    settings = _settings("production")
    with viber_client_factory(settings, token=None) as (client, svc):
        resp = client.post(
            f"/api/v1/viber/webhook/{BINDING_ID}",
            content=VIBER_BODY,
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code == 401
    svc.handle_webhook_event.assert_not_called()


def test_viber_development_missing_token_warns_and_processes(viber_client_factory, caplog):
    settings = _settings("development")
    with viber_client_factory(settings, token=None) as (client, svc):
        with caplog.at_level(logging.WARNING):
            resp = client.post(
                f"/api/v1/viber/webhook/{BINDING_ID}",
                content=VIBER_BODY,
                headers={"Content-Type": "application/json"},
            )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    svc.handle_webhook_event.assert_awaited_once()
    assert any(
        f"webhook accepted without signature verification — viber, binding {BINDING_ID}"
        in r.message
        for r in caplog.records
    )


def test_viber_valid_signature_processed(viber_client_factory):
    settings = _settings("development")
    with viber_client_factory(settings, token=VIBER_TOKEN) as (client, svc):
        resp = client.post(
            f"/api/v1/viber/webhook/{BINDING_ID}",
            content=VIBER_BODY,
            headers={
                "Content-Type": "application/json",
                "X-Viber-Content-Signature": _viber_signature(VIBER_BODY, VIBER_TOKEN),
            },
        )
    assert resp.status_code == 200
    svc.handle_webhook_event.assert_awaited_once()


def test_viber_invalid_signature_rejected(viber_client_factory):
    settings = _settings("development")
    with viber_client_factory(settings, token=VIBER_TOKEN) as (client, svc):
        resp = client.post(
            f"/api/v1/viber/webhook/{BINDING_ID}",
            content=VIBER_BODY,
            headers={
                "Content-Type": "application/json",
                "X-Viber-Content-Signature": "deadbeef",
            },
        )
    assert resp.status_code == 403
    svc.handle_webhook_event.assert_not_called()


# --- TikTok ---


def test_tiktok_production_missing_secret_returns_401(tiktok_client_factory):
    settings = _settings("production", tiktok_app_secret=None, tiktok_messaging_enabled=True)
    with tiktok_client_factory(settings) as (client, svc):
        resp = client.post(
            f"/api/v1/tiktok/webhook/{BINDING_ID}",
            content=TIKTOK_BODY,
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code == 401
    svc.handle_webhook_event.assert_not_called()


def test_tiktok_development_missing_secret_warns_and_processes(tiktok_client_factory, caplog):
    settings = _settings("development", tiktok_app_secret=None, tiktok_messaging_enabled=True)
    with tiktok_client_factory(settings) as (client, svc):
        with caplog.at_level(logging.WARNING):
            resp = client.post(
                f"/api/v1/tiktok/webhook/{BINDING_ID}",
                content=TIKTOK_BODY,
                headers={"Content-Type": "application/json"},
            )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    svc.handle_webhook_event.assert_awaited_once()
    assert any(
        f"webhook accepted without signature verification — tiktok, binding {BINDING_ID}"
        in r.message
        for r in caplog.records
    )


def test_tiktok_valid_signature_processed(tiktok_client_factory):
    settings = _settings(
        "development",
        tiktok_app_secret=TIKTOK_SECRET,
        tiktok_messaging_enabled=True,
    )
    with tiktok_client_factory(settings) as (client, svc):
        resp = client.post(
            f"/api/v1/tiktok/webhook/{BINDING_ID}",
            content=TIKTOK_BODY,
            headers={
                "Content-Type": "application/json",
                "X-TikTok-Signature": _tiktok_signature(TIKTOK_BODY, TIKTOK_SECRET),
            },
        )
    assert resp.status_code == 200
    svc.handle_webhook_event.assert_awaited_once()


def test_tiktok_invalid_signature_rejected(tiktok_client_factory):
    settings = _settings(
        "development",
        tiktok_app_secret=TIKTOK_SECRET,
        tiktok_messaging_enabled=True,
    )
    with tiktok_client_factory(settings) as (client, svc):
        resp = client.post(
            f"/api/v1/tiktok/webhook/{BINDING_ID}",
            content=TIKTOK_BODY,
            headers={
                "Content-Type": "application/json",
                "X-TikTok-Signature": "deadbeef",
            },
        )
    assert resp.status_code == 403
    svc.handle_webhook_event.assert_not_called()
