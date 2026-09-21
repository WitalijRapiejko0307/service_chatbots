"""Instagram webhook verify + signature tests (no live network / no DB)."""

import hashlib
import hmac

import pytest
from fastapi import FastAPI, Header, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from app.models.channel_binding import ChannelType
from app.services.instagram_service import InstagramService
from tests.conftest import DummySettings, FakeBindingService, FakeDB, make_binding

VERIFY_TOKEN = "verify-me"
APP_SECRET = "ig-app-secret"


def _mini_webhook_app() -> FastAPI:
    """Mirrors production GET challenge + POST HMAC 403 without importing the full API stack."""
    app = FastAPI()
    db = FakeDB()
    binding = make_binding(channel=ChannelType.INSTAGRAM)
    svc = InstagramService(FakeBindingService(binding), db, DummySettings())

    @app.get("/api/v1/instagram/webhook")
    async def verify_webhook(
        mode: str = Query(..., alias="hub.mode"),
        token: str = Query(..., alias="hub.verify_token"),
        challenge: str = Query(..., alias="hub.challenge"),
    ):
        if mode == "subscribe" and token == VERIFY_TOKEN:
            return PlainTextResponse(content=challenge, status_code=200)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Webhook verification failed")

    @app.post("/api/v1/instagram/webhook")
    async def handle_webhook(
        request: Request,
        x_hub_signature_256: str | None = Header(None, alias="X-Hub-Signature-256"),
    ):
        body = await request.body()
        if not x_hub_signature_256 or not svc.verify_webhook_signature(
            body, x_hub_signature_256, app_secret=APP_SECRET
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid webhook signature",
            )
        return {"status": "ok"}

    return app


def test_instagram_get_verify_challenge():
    client = TestClient(_mini_webhook_app())
    resp = client.get(
        "/api/v1/instagram/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": VERIFY_TOKEN, "hub.challenge": "abc123"},
    )
    assert resp.status_code == 200
    assert resp.text == "abc123"


def test_instagram_get_verify_wrong_token_403():
    client = TestClient(_mini_webhook_app())
    resp = client.get(
        "/api/v1/instagram/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "abc123"},
    )
    assert resp.status_code == 403


def test_instagram_post_signature_fail_403():
    client = TestClient(_mini_webhook_app())
    body = b'{"object":"instagram","entry":[]}'
    resp = client.post(
        "/api/v1/instagram/webhook",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": "sha256=deadbeef"},
    )
    assert resp.status_code == 403


def test_instagram_signature_accepts_valid_hmac():
    db = FakeDB()
    binding = make_binding(channel=ChannelType.INSTAGRAM)
    svc = InstagramService(FakeBindingService(binding), db, DummySettings())
    body = b'{"object":"instagram"}'
    digest = hmac.new(b"ig-app-secret", body, hashlib.sha256).hexdigest()
    assert svc.verify_webhook_signature(body, f"sha256={digest}", app_secret="ig-app-secret") is True
    assert svc.verify_webhook_signature(body, "sha256=nope", app_secret="ig-app-secret") is False


def _ig_payload(mid: str = "mid-1", text: str = "hello", sender: str = "user-1", recipient: str = "bot-1") -> dict:
    return {
        "object": "instagram",
        "entry": [
            {
                "messaging": [
                    {
                        "sender": {"id": sender},
                        "recipient": {"id": recipient},
                        "message": {"mid": mid, "text": text},
                    }
                ]
            }
        ],
    }


@pytest.mark.asyncio
async def test_instagram_duplicate_mid_does_not_double_insert():
    db = FakeDB()
    binding = make_binding(channel=ChannelType.INSTAGRAM, account_id="bot-1")
    svc = InstagramService(FakeBindingService(binding), db, DummySettings())
    payload = _ig_payload()

    await svc.handle_webhook_event(payload)
    await svc.handle_webhook_event(payload)

    assert len(db.messages) == 1
    assert len(db.conversations) == 1


@pytest.mark.asyncio
async def test_instagram_duplicate_inbound_does_not_call_agent():
    db = FakeDB()
    binding = make_binding(channel=ChannelType.INSTAGRAM, account_id="bot-1")
    svc = InstagramService(FakeBindingService(binding), db, DummySettings())
    payload = _ig_payload(mid="mid-dup")

    await svc.handle_webhook_event(payload)
    assert len(db.messages) == 1

    async def boom(*_a, **_k):
        raise AssertionError("agent must not run on duplicate inbound")

    db.get_agent = boom  # type: ignore[method-assign]
    await svc.handle_webhook_event(payload)
    assert len(db.messages) == 1


def test_is_instagram_app_review_error_detects_advanced_access():
    from app.services.instagram_service import is_instagram_app_review_error

    assert is_instagram_app_review_error(400, "(#10) Application does not have permission", 10)
    assert is_instagram_app_review_error(403, "This app needs Advanced Access for instagram_manage_messages")
    assert is_instagram_app_review_error(400, "The app is not in Live mode")
    assert is_instagram_app_review_error(400, "invalid token") is False


class _JsonResp:
    def __init__(self, status_code: int, payload: dict, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or ""

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_get_user_profile_returns_graph_error_not_none_only():
    from unittest.mock import patch

    binding = make_binding(channel=ChannelType.INSTAGRAM)
    svc = InstagramService(FakeBindingService(binding), FakeDB(), DummySettings())

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None):
            return _JsonResp(
                400,
                {"error": {"message": "(#10) Application does not have permission", "code": 10}},
                "(#10) Application does not have permission",
            )

    with patch("httpx.AsyncClient", return_value=_Client()):
        profile, error = await svc.get_user_profile("user-1", "tok")

    assert profile is None
    assert error is not None
    assert "does not have permission" in error


@pytest.mark.asyncio
async def test_refresh_profile_for_conversation_success_and_wrong_channel():
    from unittest.mock import patch

    from app.models.conversation import Conversation, ConversationStatus
    from app.models.message import MessageChannel
    from app.utils.datetime_utils import utc_now

    db = FakeDB()
    binding = make_binding(channel=ChannelType.INSTAGRAM, agent_id="agent-1")
    svc = InstagramService(FakeBindingService(binding), db, DummySettings())
    now = utc_now()
    ig_conv = Conversation(
        conversation_id="c-ig",
        agent_id="agent-1",
        channel=MessageChannel.INSTAGRAM,
        external_user_id="ig-user-1",
        status=ConversationStatus.AI_ACTIVE,
        created_at=now,
        updated_at=now,
    )
    web_conv = Conversation(
        conversation_id="c-web",
        agent_id="agent-1",
        channel=MessageChannel.WEB_CHAT,
        status=ConversationStatus.AI_ACTIVE,
        created_at=now,
        updated_at=now,
    )

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None):
            return _JsonResp(
                200,
                {"name": "Ada", "username": "ada", "profile_pic": "https://cdn.example/p.jpg"},
            )

    with patch("httpx.AsyncClient", return_value=_Client()):
        profile, error = await svc.refresh_profile_for_conversation(ig_conv)

    assert error is None
    assert profile is not None
    assert profile.name == "Ada"
    assert profile.username == "ada"
    assert "ig-user-1" in db.instagram_profiles

    with pytest.raises(ValueError, match="Instagram"):
        await svc.refresh_profile_for_conversation(web_conv)


@pytest.mark.asyncio
async def test_verify_access_token_detailed_marks_app_review_pending():
    from unittest.mock import patch

    binding = make_binding(channel=ChannelType.INSTAGRAM)
    svc = InstagramService(FakeBindingService(binding), FakeDB(), DummySettings())

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None):
            return _JsonResp(
                400,
                {"error": {"message": "Advanced Access is required", "code": 10}},
                "Advanced Access is required",
            )

    with patch("httpx.AsyncClient", return_value=_Client()):
        check = await svc.verify_access_token_detailed("tok", "acct-1")

    assert check.ok is False
    assert check.app_review_pending is True


@pytest.mark.asyncio
async def test_refresh_long_lived_token_posts_ig_refresh_grant():
    from unittest.mock import patch

    binding = make_binding(channel=ChannelType.INSTAGRAM)
    svc = InstagramService(FakeBindingService(binding), FakeDB(), DummySettings())
    captured: dict = {}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None):
            captured["url"] = url
            captured["params"] = params
            return _JsonResp(200, {"access_token": "new-tok", "expires_in": 5184000})

    with patch("httpx.AsyncClient", return_value=_Client()):
        result = await svc.refresh_long_lived_token("old-tok")

    assert result is not None
    assert result["access_token"] == "new-tok"
    assert result["expires_in"] == 5184000
    assert result["token_expires_at"]
    assert captured["url"] == "https://graph.instagram.com/refresh_access_token"
    assert captured["params"]["grant_type"] == "ig_refresh_token"


def test_oauth_callback_redirects_to_frontend_origin():
    from unittest.mock import AsyncMock, patch
    from urllib.parse import parse_qs, urlparse

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace

    from app.api.auth import get_current_admin
    from app.api.v1.instagram import get_instagram_service, router
    from app.dependencies import CommonDependencies
    from app.utils.oauth_state import make_oauth_state

    settings = DummySettings()
    settings.instagram_app_id = "ig-app"
    settings.instagram_app_secret = "ig-secret"
    settings.app_url = "https://api.example.test"
    settings.frontend_url = "https://front.example.test"

    db = FakeDB()
    db.agents["agent-1"] = {"agent_id": "agent-1"}

    class _Deps:
        def __init__(self) -> None:
            self.db = db

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    fake_ig = AsyncMock()
    fake_ig.exchange_oauth_code = AsyncMock(
        return_value={
            "access_token": "at-1",
            "account_id": "178414000",
            "username": "biz",
            "token_expires_at": "2026-11-20T00:00:00Z",
        }
    )
    created = SimpleNamespace(binding_id="bind-ig")
    instance = AsyncMock()
    instance.get_binding_by_account_id = AsyncMock(return_value=None)
    instance.create_binding = AsyncMock(return_value=created)
    instance.verify_binding = AsyncMock(return_value=True)

    class FakeSecrets:
        pass

    async def _admin() -> str:
        return "admin_user"

    app.dependency_overrides[get_current_admin] = _admin
    app.dependency_overrides[CommonDependencies] = lambda: _Deps()
    app.dependency_overrides[get_instagram_service] = lambda: fake_ig

    patches = (
        patch("app.api.v1.instagram.get_settings", return_value=settings),
        patch("app.api.auth.get_settings", return_value=settings),
        patch("app.config.get_settings", return_value=settings),
        patch("app.api.v1.instagram.ChannelBindingService", return_value=instance),
        patch("app.api.v1.instagram.get_secrets_manager", return_value=FakeSecrets()),
    )
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        client = TestClient(app)
        state = make_oauth_state("agent-1", settings.jwt_secret_key)
        resp = client.get(
            "/api/v1/instagram/oauth/callback",
            params={"code": "ok-code", "state": state},
            follow_redirects=False,
        )

    assert resp.status_code == 302
    location = resp.headers["location"]
    assert location.startswith("https://front.example.test/admin/agents/agent-1/channels")
    qs = parse_qs(urlparse(location).query)
    assert qs["instagram_binding"] == ["bind-ig"]
    instance.create_binding.assert_awaited()
    kwargs = instance.create_binding.await_args.kwargs
    assert kwargs["metadata"]["connected_via"] == "oauth"
    assert kwargs["metadata"]["token_expires_at"] == "2026-11-20T00:00:00Z"
    instance.verify_binding.assert_awaited()


@pytest.mark.asyncio
async def test_verify_binding_sets_app_review_pending_metadata():
    from unittest.mock import AsyncMock, patch

    from app.services.channel_binding_service import ChannelBindingService

    db = FakeDB()
    binding = make_binding(channel=ChannelType.INSTAGRAM, metadata={"connected_via": "paste"})
    db.get_channel_binding = AsyncMock(return_value=binding)  # type: ignore[attr-defined]

    class FakeSecrets:
        async def get_channel_token(self, secret_name: str) -> str:
            return "tok"

        async def update_channel_token(self, secret_name: str, access_token: str, metadata: dict) -> None:
            return None

    svc = ChannelBindingService(db, FakeSecrets())

    async def _get(binding_id: str):
        return binding

    svc.get_binding = _get  # type: ignore[method-assign]
    svc.get_access_token = AsyncMock(return_value="tok")  # type: ignore[method-assign]
    updated: list[dict] = []

    async def _update(binding_id: str, **kwargs):
        updated.append(kwargs)
        if "metadata" in kwargs:
            binding.metadata = kwargs["metadata"]
        if "is_verified" in kwargs:
            binding.is_verified = kwargs["is_verified"]
        return binding

    svc.update_binding = _update  # type: ignore[method-assign]

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None):
            return _JsonResp(
                400,
                {"error": {"message": "Advanced Access is required", "code": 10}},
                "Advanced Access is required",
            )

    with patch("httpx.AsyncClient", return_value=_Client()):
        with patch("app.config.get_settings", return_value=DummySettings()):
            ok = await svc.verify_binding(binding.binding_id)

    assert ok is False
    assert any(item.get("metadata", {}).get("app_review_pending") is True for item in updated)
