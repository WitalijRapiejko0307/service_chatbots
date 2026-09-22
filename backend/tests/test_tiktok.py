"""TikTok disabled-mode tests and Login Kit OAuth harden (no live network)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.channel_binding import ChannelType
from app.services.channel_binding_service import ChannelBindingService
from app.services.tiktok_service import (
    TIKTOK_OAUTH_REVOKE_URL,
    TIKTOK_OAUTH_TOKEN_URL,
    TikTokService,
)
from app.utils.oauth_state import make_oauth_state, parse_oauth_state
from tests.conftest import DummySettings, FakeBindingService, FakeDB, make_binding


class FakeSecrets:
    def __init__(self) -> None:
        self.created_metadata = None
        self.updated_metadata = None

    async def create_channel_token_secret(self, **kwargs):
        self.created_metadata = kwargs.get("metadata")
        return "secret-name"

    async def get_channel_token(self, name):
        return "tok"

    async def update_channel_token(self, **kwargs):
        self.updated_metadata = kwargs.get("metadata")
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
    assert result == (False, [])


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

    assert result[0] is True
    assert result[1] == []
    assert len(calls) == 2
    assert calls[0]["message_type"] in ("image", "file")
    assert calls[0].get("media_url")
    assert calls[1]["message_type"] == "text"
    assert calls[1]["text"] == "caption"
    assert "media_url" not in calls[1]


def _oauth_settings() -> DummySettings:
    settings = DummySettings()
    settings.tiktok_app_id = "tt-app-id"
    settings.tiktok_app_secret = "tt-app-secret"
    settings.app_url = "https://api.example.test"
    settings.frontend_url = "https://front.example.test"
    settings.jwt_secret_key = "jwt-secret-for-tests-min-32-chars"
    settings.tiktok_messaging_enabled = False
    settings.debug = True
    return settings


def _patch_settings(settings: DummySettings):
    return (
        patch("app.api.v1.tiktok.get_settings", return_value=settings),
        patch("app.api.auth.get_settings", return_value=settings),
        patch("app.config.get_settings", return_value=settings),
    )


def _oauth_app(db: FakeDB | None = None):
    from app.api.auth import get_current_admin
    from app.api.v1.tiktok import get_tiktok_service, router
    from app.dependencies import CommonDependencies

    db = db or FakeDB()
    db.agents["agent-1"] = {"agent_id": "agent-1"}

    class _Deps:
        def __init__(self) -> None:
            self.db = db

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    fake_tt = AsyncMock()

    async def _admin() -> str:
        return "admin_user"

    app.dependency_overrides[get_current_admin] = _admin
    app.dependency_overrides[CommonDependencies] = lambda: _Deps()
    app.dependency_overrides[get_tiktok_service] = lambda: fake_tt
    return app, fake_tt, db


class _JsonResp:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = ""

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_exchange_oauth_code_posts_login_kit_v2():
    settings = DummySettings()
    settings.tiktok_app_id = "tt-client-key"
    settings.tiktok_app_secret = "tt-client-secret"
    captured: dict = {}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, data=None, headers=None, json=None):
            captured["url"] = url
            captured["data"] = data
            captured["headers"] = headers
            return _JsonResp(
                200,
                {
                    "access_token": "at-1",
                    "open_id": "openid-1",
                    "refresh_token": "rt-1",
                    "log_id": "log-xyz",
                },
            )

    svc = TikTokService(
        FakeBindingService(make_binding(channel=ChannelType.TIKTOK)),
        FakeDB(),
        settings,
    )
    redirect_uri = "https://api.example.test/api/v1/tiktok/oauth/callback"
    with patch("httpx.AsyncClient", return_value=_Client()):
        result = await svc.exchange_oauth_code("abc%2Fdef", redirect_uri)

    assert captured["url"] == TIKTOK_OAUTH_TOKEN_URL
    assert captured["data"]["grant_type"] == "authorization_code"
    assert captured["data"]["client_key"] == "tt-client-key"
    assert captured["data"]["code"] == "abc/def"
    assert captured["data"]["redirect_uri"] == redirect_uri
    assert result is not None
    assert result["account_id"] == "openid-1"
    assert result["access_token"] == "at-1"
    assert result["refresh_token"] == "rt-1"


def test_oauth_state_roundtrip_and_tampered():
    secret = "jwt-secret-for-tests-min-32-chars"
    agent_id = "agent-1"
    state = make_oauth_state(agent_id, secret)
    assert state != agent_id
    assert ":" in state
    assert parse_oauth_state(state, secret) == agent_id

    agent, digest = state.split(":", 1)
    tampered = f"{agent}:{digest[:-1]}{'0' if digest[-1] != '0' else '1'}"
    assert parse_oauth_state(tampered, secret) is None


def test_oauth_start_signed_state_and_basic_scope():
    settings = _oauth_settings()
    app, _, _ = _oauth_app()
    patches = _patch_settings(settings)
    with patches[0], patches[1], patches[2]:
        client = TestClient(app)
        resp = client.get(
            "/api/v1/tiktok/oauth/start",
            params={"agent_id": "agent-1"},
            headers={"Accept": "application/json"},
        )

    assert resp.status_code == 200
    url = resp.json()["authorization_url"]
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "www.tiktok.com"
    assert parsed.path.rstrip("/") == "/v2/auth/authorize"
    assert qs["response_type"] == ["code"]
    assert qs["scope"] == ["user.info.basic"]
    assert "business.messaging" not in qs["scope"][0]
    redirect_uri = qs["redirect_uri"][0]
    assert redirect_uri == "https://api.example.test/api/v1/tiktok/oauth/callback"
    assert "?" not in redirect_uri
    state = qs["state"][0]
    assert state != "agent-1"
    assert ":" in state
    assert parse_oauth_state(state, settings.jwt_secret_key) == "agent-1"


def test_oauth_callback_tampered_state_does_not_create_binding():
    settings = _oauth_settings()
    app, fake_tt, _ = _oauth_app()
    fake_tt.exchange_oauth_code = AsyncMock(return_value={"access_token": "at", "account_id": "oid"})
    good = make_oauth_state("agent-1", settings.jwt_secret_key)
    agent, digest = good.split(":", 1)
    tampered = f"{agent}:{digest[:-1]}{'0' if digest[-1] != '0' else '1'}"

    patches = _patch_settings(settings)
    with patches[0], patches[1], patches[2]:
        with patch("app.api.v1.tiktok.ChannelBindingService") as cbs_cls:
            with patch("app.api.v1.tiktok.get_secrets_manager", return_value=FakeSecrets()):
                client = TestClient(app)
                resp = client.get(
                    "/api/v1/tiktok/oauth/callback",
                    params={"code": "ok-code", "state": tampered},
                    follow_redirects=False,
                )

    assert resp.status_code == 400
    cbs_cls.assert_not_called()
    fake_tt.exchange_oauth_code.assert_not_called()


def test_oauth_callback_success_redirects_to_frontend():
    settings = _oauth_settings()
    app, fake_tt, _ = _oauth_app()
    fake_tt.exchange_oauth_code = AsyncMock(
        return_value={
            "access_token": "at-1",
            "account_id": "openid-1",
            "refresh_token": "rt-1",
        }
    )
    created = SimpleNamespace(binding_id="bind-123")
    instance = AsyncMock()
    instance.get_binding_by_account_id = AsyncMock(return_value=None)
    instance.create_binding = AsyncMock(return_value=created)
    instance.verify_binding = AsyncMock(return_value=False)

    patches = _patch_settings(settings)
    with patches[0], patches[1], patches[2]:
        with patch("app.api.v1.tiktok.ChannelBindingService", return_value=instance):
            with patch("app.api.v1.tiktok.get_secrets_manager", return_value=FakeSecrets()):
                client = TestClient(app)
                state = make_oauth_state("agent-1", settings.jwt_secret_key)
                resp = client.get(
                    "/api/v1/tiktok/oauth/callback",
                    params={"code": "ok-code", "state": state},
                    follow_redirects=False,
                )

    assert resp.status_code == 302
    location = resp.headers["location"]
    assert location.startswith("https://front.example.test/admin/agents/agent-1/channels")
    assert "tiktok_binding=bind-123" in location
    instance.create_binding.assert_awaited()
    kwargs = instance.create_binding.await_args.kwargs
    assert kwargs["channel_account_id"] == "openid-1"
    assert kwargs["metadata"]["connected_via"] == "oauth"
    assert kwargs["metadata"]["pending_access"] is True
    assert kwargs["metadata"]["refresh_token"] == "rt-1"
    fake_tt.exchange_oauth_code.assert_awaited()


@pytest.mark.asyncio
async def test_revoke_access_token_posts_and_failure_does_not_raise():
    settings = DummySettings()
    settings.tiktok_app_id = "tt-client-key"
    settings.tiktok_app_secret = "tt-client-secret"
    captured: dict = {}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, data=None, headers=None, json=None):
            captured["url"] = url
            captured["data"] = data
            return _JsonResp(500, {"error": "nope"})

    svc = TikTokService(
        FakeBindingService(make_binding(channel=ChannelType.TIKTOK)),
        FakeDB(),
        settings,
    )
    with patch("httpx.AsyncClient", return_value=_Client()):
        result = await svc.revoke_access_token("tok-1")

    assert result is False
    assert captured["url"] == TIKTOK_OAUTH_REVOKE_URL
    assert captured["data"]["client_key"] == "tt-client-key"
    assert captured["data"]["token"] == "tok-1"


@pytest.mark.asyncio
async def test_create_binding_strips_refresh_token_from_db_metadata():
    db = FakeDB()
    db.create_channel_binding = AsyncMock(side_effect=lambda b: b)
    settings = DummySettings()
    settings.tiktok_messaging_enabled = False
    secrets = FakeSecrets()

    with patch("app.config.get_settings", return_value=settings):
        svc = ChannelBindingService(db, secrets)
        binding = await svc.create_binding(
            agent_id="agent-1",
            channel_type="tiktok",
            channel_account_id="openid-1",
            access_token="tok",
            metadata={"connected_via": "oauth", "refresh_token": "rt-secret"},
        )

    assert binding.metadata.get("pending_access") is True
    assert binding.metadata.get("connected_via") == "oauth"
    assert "refresh_token" not in binding.metadata
    assert secrets.created_metadata["refresh_token"] == "rt-secret"
