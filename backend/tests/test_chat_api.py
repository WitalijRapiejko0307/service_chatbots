"""HTTP tests for public chat API router (app.api.v1.chat)."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.exceptions import AgentException, NotFoundError
from app.api.v1 import chat as chat_router
from app.dependencies import CommonDependencies
from app.models.conversation import Conversation, ConversationStatus, MarketingStatus
from app.models.message import Message, MessageChannel, MessageRole
from app.utils.datetime_utils import utc_now
from app.utils.enum_helpers import get_enum_value
from tests.conftest import DummySettings, FakeDB

FIXED_NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
AGENT_ID = "agent-1"


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(AgentException)
    async def agent_exception_handler(request: Request, exc: AgentException):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        safe_errors = [
            {k: v for k, v in e.items() if k not in ("input", "ctx", "url")}
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": {"errors": safe_errors},
                }
            },
        )


class ChatApiFakeDB(FakeDB):
    """FakeDB with chat-router persistence helpers."""

    async def create_message(self, message: Message) -> Message:
        await self.try_create_message(message)
        return message


def _minimal_agent(agent_id: str = AGENT_ID, *, is_active: bool = True) -> dict:
    return {
        "agent_id": agent_id,
        "is_active": is_active,
        "config": {
            "agent_id": agent_id,
            "project": "test-project",
            "profile": {
                "agent_display_name": "Test Agent",
                "company_display_name": "Test Company",
            },
        },
    }


def _conversation(
    *,
    conversation_id: str,
    agent_id: str = AGENT_ID,
    status: ConversationStatus = ConversationStatus.AI_ACTIVE,
    channel: MessageChannel = MessageChannel.WEB_CHAT,
) -> Conversation:
    return Conversation(
        conversation_id=conversation_id,
        agent_id=agent_id,
        channel=channel,
        status=status,
        marketing_status=MarketingStatus.NEW,
        created_at=FIXED_NOW,
        updated_at=FIXED_NOW,
    )


@contextmanager
def chat_client(
    db: ChatApiFakeDB,
    *,
    settings: DummySettings | None = None,
    agent_service: MagicMock | None = None,
):
    settings = settings or DummySettings()
    app = FastAPI()
    _register_exception_handlers(app)
    app.include_router(chat_router.router, prefix="/api/v1/chat")

    deps = SimpleNamespace(config=settings, db=db, cache=None)
    app.dependency_overrides[CommonDependencies] = lambda: deps

    mock_service = agent_service or MagicMock()
    if agent_service is not None:
        if not isinstance(getattr(mock_service, "run_pre_moderation_guard", None), AsyncMock):
            mock_service.run_pre_moderation_guard = AsyncMock(return_value=None)
    else:
        mock_service.run_pre_moderation_guard = AsyncMock(return_value=None)
        mock_service.process_message = AsyncMock(
            return_value={
                "response": "AI reply",
                "agent_message_id": "agent-msg-1",
                "escalate": False,
            }
        )

    mock_sender = MagicMock()
    mock_sender.send_message = AsyncMock()

    with (
        patch("app.config.get_settings", return_value=settings),
        patch("app.api.v1.chat.get_settings", return_value=settings),
        patch("app.api.v1.chat.create_agent_service", return_value=mock_service),
        patch("app.api.v1.chat.get_channel_sender", return_value=mock_sender),
        patch("app.api.v1.chat.cancel_timer_trigger", AsyncMock()),
    ):
        client = TestClient(app)
        yield client, mock_service


# ── Create conversation ───────────────────────────────────────────────────────


def test_create_conversation_success():
    db = ChatApiFakeDB()
    db.agents[AGENT_ID] = _minimal_agent()
    with chat_client(db) as (client, _service):
        resp = client.post("/api/v1/chat/conversations", json={"agent_id": AGENT_ID})
    assert resp.status_code == 201
    body = resp.json()
    assert body["agent_id"] == AGENT_ID
    assert body["status"] == ConversationStatus.AI_ACTIVE.value
    assert body["conversation_id"] in db.conversations


def test_create_conversation_agent_not_found_returns_404():
    db = ChatApiFakeDB()
    with chat_client(db) as (client, _service):
        resp = client.post("/api/v1/chat/conversations", json={"agent_id": "missing-agent"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "AGENT_NOT_FOUND"


@pytest.mark.xfail(
    reason="chat.py does not check agent is_active before creating conversation (chat.py:95-97)",
    strict=False,
)
def test_create_conversation_inactive_agent_rejected():
    """Desired behavior: inactive agents should not accept new conversations."""
    db = ChatApiFakeDB()
    db.agents["inactive-agent"] = _minimal_agent("inactive-agent", is_active=False)
    with chat_client(db) as (client, _service):
        resp = client.post(
            "/api/v1/chat/conversations", json={"agent_id": "inactive-agent"}
        )
    assert resp.status_code in (400, 404)


@pytest.mark.xfail(
    reason="AgentIDValidator mixin is not applied to CreateConversationRequest (chat.py:31, schemas.py:42-59)",
    strict=False,
)
def test_create_conversation_invalid_agent_id_format_returns_422():
    """Desired behavior: malformed agent_id should be rejected at validation (422)."""
    db = ChatApiFakeDB()
    with chat_client(db) as (client, _service):
        resp = client.post("/api/v1/chat/conversations", json={"agent_id": "bad id!"})
    assert resp.status_code == 422


def test_create_conversation_unknown_agent_id_returns_404():
    # Current behavior: invalid-format ids pass Pydantic and surface as AGENT_NOT_FOUND.
    db = ChatApiFakeDB()
    with chat_client(db) as (client, _service):
        resp = client.post("/api/v1/chat/conversations", json={"agent_id": "bad id!"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "AGENT_NOT_FOUND"


# ── Send message: AI vs human paths ──────────────────────────────────────────


def test_send_message_ai_responds():
    db = ChatApiFakeDB()
    db.agents[AGENT_ID] = _minimal_agent()
    conv = _conversation(conversation_id="conv-ai")
    db.conversations[conv.conversation_id] = conv
    with chat_client(db) as (client, mock_service):
        resp = client.post(
            f"/api/v1/chat/conversations/{conv.conversation_id}/messages",
            json={"content": "Hello"},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["role"] == MessageRole.AGENT.value
    assert body["content"] == "AI reply"
    assert body["message_id"] == "agent-msg-1"
    mock_service.process_message.assert_awaited_once()


def test_send_message_human_active_skips_ai():
    db = ChatApiFakeDB()
    conv = _conversation(
        conversation_id="conv-human",
        status=ConversationStatus.HUMAN_ACTIVE,
    )
    db.conversations[conv.conversation_id] = conv
    with chat_client(db) as (client, mock_service):
        resp = client.post(
            f"/api/v1/chat/conversations/{conv.conversation_id}/messages",
            json={"content": "Need help"},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["role"] == MessageRole.USER.value
    assert body["content"] == "Need help"
    mock_service.process_message.assert_not_called()


def test_send_message_needs_human_skips_ai():
    db = ChatApiFakeDB()
    conv = _conversation(
        conversation_id="conv-needs",
        status=ConversationStatus.NEEDS_HUMAN,
    )
    db.conversations[conv.conversation_id] = conv
    with chat_client(db) as (client, mock_service):
        resp = client.post(
            f"/api/v1/chat/conversations/{conv.conversation_id}/messages",
            json={"content": "Escalated case"},
        )
    assert resp.status_code == 201
    assert resp.json()["role"] == MessageRole.USER.value
    mock_service.process_message.assert_not_called()


def test_send_message_agent_fallback_when_no_agent_message_id():
    db = ChatApiFakeDB()
    db.agents[AGENT_ID] = _minimal_agent()
    conv = _conversation(conversation_id="conv-fallback")
    db.conversations[conv.conversation_id] = conv
    mock_service = MagicMock()
    mock_service.run_pre_moderation_guard = AsyncMock(return_value=None)
    mock_service.process_message = AsyncMock(
        return_value={"agent_message_id": None, "escalate": False}
    )
    with chat_client(db, agent_service=mock_service) as (client, _service):
        resp = client.post(
            f"/api/v1/chat/conversations/{conv.conversation_id}/messages",
            json={"content": "Trigger fallback"},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["role"] == MessageRole.AGENT.value
    assert body["content"] == "I apologize, but I couldn't generate a response."


# ── Message history ───────────────────────────────────────────────────────────


def test_get_messages_returns_history():
    db = ChatApiFakeDB()
    conv = _conversation(conversation_id="conv-history")
    db.conversations[conv.conversation_id] = conv
    msg = Message(
        message_id="msg-1",
        conversation_id=conv.conversation_id,
        agent_id=AGENT_ID,
        role=MessageRole.USER,
        content="Hi",
        channel=MessageChannel.WEB_CHAT,
        timestamp=FIXED_NOW,
    )
    db.messages[(conv.conversation_id, "msg-1")] = msg
    with chat_client(db) as (client, _service):
        resp = client.get(f"/api/v1/chat/conversations/{conv.conversation_id}/messages")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["content"] == "Hi"


def test_get_messages_conversation_not_found_returns_404():
    db = ChatApiFakeDB()
    with chat_client(db) as (client, _service):
        resp = client.get("/api/v1/chat/conversations/does-not-exist/messages")
    assert resp.status_code == 404


# ── Close conversation ────────────────────────────────────────────────────────


def test_close_conversation_success():
    db = ChatApiFakeDB()
    conv = _conversation(conversation_id="conv-close")
    db.conversations[conv.conversation_id] = conv
    with (
        patch("app.api.v1.chat.utc_now", return_value=FIXED_NOW),
        chat_client(db) as (client, _service),
    ):
        resp = client.post(f"/api/v1/chat/conversations/{conv.conversation_id}/close")
    assert resp.status_code == 200
    assert resp.json()["status"] == ConversationStatus.CLOSED.value
    assert get_enum_value(db.conversations[conv.conversation_id].status) == (
        ConversationStatus.CLOSED.value
    )


def test_close_conversation_idempotent_when_already_closed():
    db = ChatApiFakeDB()
    conv = _conversation(
        conversation_id="conv-closed", status=ConversationStatus.CLOSED
    )
    db.conversations[conv.conversation_id] = conv
    with chat_client(db) as (client, _service):
        resp = client.post(f"/api/v1/chat/conversations/{conv.conversation_id}/close")
    assert resp.status_code == 200
    assert resp.json()["status"] == ConversationStatus.CLOSED.value


def test_close_non_web_chat_conversation_returns_400():
    db = ChatApiFakeDB()
    conv = _conversation(
        conversation_id="conv-telegram", channel=MessageChannel.TELEGRAM
    )
    db.conversations[conv.conversation_id] = conv
    with chat_client(db) as (client, _service):
        resp = client.post(f"/api/v1/chat/conversations/{conv.conversation_id}/close")
    assert resp.status_code == 400


def test_close_conversation_not_found_returns_404():
    db = ChatApiFakeDB()
    with chat_client(db) as (client, _service):
        resp = client.post("/api/v1/chat/conversations/missing/close")
    assert resp.status_code == 404


# ── Validation ────────────────────────────────────────────────────────────────


def test_send_message_empty_content_returns_422():
    db = ChatApiFakeDB()
    conv = _conversation(conversation_id="conv-empty")
    db.conversations[conv.conversation_id] = conv
    with chat_client(db) as (client, _service):
        resp = client.post(
            f"/api/v1/chat/conversations/{conv.conversation_id}/messages",
            json={"content": "   "},
        )
    assert resp.status_code == 422


def test_send_message_too_long_returns_422():
    db = ChatApiFakeDB()
    conv = _conversation(conversation_id="conv-long")
    db.conversations[conv.conversation_id] = conv
    with chat_client(db) as (client, _service):
        resp = client.post(
            f"/api/v1/chat/conversations/{conv.conversation_id}/messages",
            json={"content": "x" * 10001},
        )
    assert resp.status_code == 422


def test_send_message_media_url_without_type_with_text_returns_422():
    db = ChatApiFakeDB()
    conv = _conversation(conversation_id="conv-media-pair")
    db.conversations[conv.conversation_id] = conv
    with chat_client(db) as (client, _service):
        resp = client.post(
            f"/api/v1/chat/conversations/{conv.conversation_id}/messages",
            json={"content": "see image", "media_url": "https://cdn.example/img.png"},
        )
    assert resp.status_code == 422
    assert "media_url and media_type must be sent together" in str(resp.json())


@pytest.mark.parametrize(
    "payload,expected_fragment",
    [
        (
            {"media_url": "https://cdn.example/img.png"},
            "Message must include text or an image attachment",
        ),
        (
            {
                "media_url": "https://cdn.example/v.mp4",
                "media_type": "video",
            },
            "Web chat supports image attachments only",
        ),
        (
            {
                "media_url": "ftp://cdn.example/img.png",
                "media_type": "image",
            },
            "media_url must be an http(s) URL",
        ),
    ],
)
def test_send_message_media_validation_returns_422(payload, expected_fragment):
    db = ChatApiFakeDB()
    conv = _conversation(conversation_id="conv-media-val")
    db.conversations[conv.conversation_id] = conv
    with chat_client(db) as (client, _service):
        resp = client.post(
            f"/api/v1/chat/conversations/{conv.conversation_id}/messages",
            json=payload,
        )
    assert resp.status_code == 422
    assert expected_fragment in str(resp.json())


def test_send_message_closed_conversation_returns_400():
    db = ChatApiFakeDB()
    conv = _conversation(
        conversation_id="conv-closed-send", status=ConversationStatus.CLOSED
    )
    db.conversations[conv.conversation_id] = conv
    with chat_client(db) as (client, _service):
        resp = client.post(
            f"/api/v1/chat/conversations/{conv.conversation_id}/messages",
            json={"content": "Too late"},
        )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Conversation is closed"


def test_send_message_conversation_not_found_returns_404():
    db = ChatApiFakeDB()
    with chat_client(db) as (client, _service):
        resp = client.post(
            "/api/v1/chat/conversations/unknown-id/messages",
            json={"content": "Hello"},
        )
    assert resp.status_code == 404
