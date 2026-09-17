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
