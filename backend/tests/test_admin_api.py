"""HTTP tests for admin API router (app.api.v1.admin)."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.exceptions import AgentException, NotFoundError
from app.api.v1 import admin as admin_router
from app.dependencies import CommonDependencies
from app.models.conversation import Conversation, ConversationStatus, MarketingStatus
from app.models.message import MessageChannel
from app.utils.datetime_utils import to_utc_iso_string, utc_now
from app.utils.enum_helpers import get_enum_value
from tests.conftest import DummySettings, FakeDB

FIXED_NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
JWT_SECRET = "jwt-secret-for-tests-min-32-chars"


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _make_jwt(sub: str = "admin@test.com") -> str:
    payload = {
        "sub": sub,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


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


class AdminApiFakeDB(FakeDB):
    """FakeDB with admin-router persistence helpers."""

    def __init__(self) -> None:
        super().__init__()
        self.audit_logs: list[dict] = []

    async def create_message(self, message):
        await self.try_create_message(message)
        return message

    async def create_audit_log(
        self,
        admin_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        metadata=None,
    ) -> dict:
        entry = {
            "admin_id": admin_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "metadata": metadata or {},
            "timestamp": to_utc_iso_string(utc_now()),
        }
        self.audit_logs.append(entry)
        return entry

    async def list_audit_logs(
        self,
        admin_id: str | None = None,
        resource_type: str | None = None,
        action: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        sort_desc: bool = True,
        limit: int = 100,
    ) -> list[dict]:
        items = list(self.audit_logs)
        if admin_id:
            items = [i for i in items if i["admin_id"] == admin_id]
        if resource_type:
            items = [i for i in items if i["resource_type"] == resource_type]
        if action:
            items = [i for i in items if i["action"] == action]
        if start_date or end_date:
            filtered = []
            for item in items:
                ts = _aware(datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00")))
                if start_date and ts < _aware(start_date):
                    continue
                if end_date and ts > _aware(end_date):
                    continue
                filtered.append(item)
            items = filtered
        items.sort(key=lambda i: i["timestamp"], reverse=sort_desc)
        return items[:limit]

    async def list_conversations(
        self,
        agent_id: str | None = None,
        status=None,
        marketing_status: str | None = None,
        crm_stage_id: str | None = None,
        limit: int = 100,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> list[Conversation]:
        rows = list(self.conversations.values())
        if agent_id:
            rows = [c for c in rows if c.agent_id == agent_id]
        if status is not None:
            status_val = get_enum_value(status)
            rows = [c for c in rows if get_enum_value(c.status) == status_val]
        if marketing_status:
            rows = [
                c
                for c in rows
                if get_enum_value(c.marketing_status) == marketing_status
            ]
        if crm_stage_id:
            rows = [c for c in rows if c.crm_stage_id == crm_stage_id]
        if created_from is not None:
            rows = [
                c
                for c in rows
                if c.created_at and _aware(c.created_at) >= _aware(created_from)
            ]
        if created_to is not None:
            rows = [
                c
                for c in rows
                if c.created_at and _aware(c.created_at) <= _aware(created_to)
            ]
        key = (lambda c: c.updated_at) if sort_by == "updated_at" else (lambda c: c.created_at)
        rows.sort(key=key, reverse=sort_order != "asc")
        return rows[:limit]

    async def count_distinct_end_users(self) -> int:
        seen: set[tuple[str, str, str]] = set()
        for conv in self.conversations.values():
            if conv.external_user_id:
                seen.add(
                    (
                        conv.agent_id,
                        get_enum_value(conv.channel),
                        conv.external_user_id,
                    )
                )
        return len(seen)

    async def list_distinct_end_users(self, limit: int = 50, offset: int = 0) -> list[dict]:
        grouped: dict[tuple[str, str, str], dict] = {}
        for conv in self.conversations.values():
            if not conv.external_user_id:
                continue
            key = (
                conv.agent_id,
                get_enum_value(conv.channel),
                conv.external_user_id,
            )
            row = grouped.setdefault(
                key,
                {
                    "agent_id": conv.agent_id,
                    "agent_display_name": None,
                    "channel": get_enum_value(conv.channel),
                    "external_user_id": conv.external_user_id,
                    "display_name": None,
                    "username": None,
                    "last_seen_at": to_utc_iso_string(conv.updated_at),
                    "conversation_count": 0,
                },
            )
            row["conversation_count"] += 1
        items = list(grouped.values())
        return items[offset : offset + limit]


def _conversation(
    *,
    conversation_id: str,
    agent_id: str = "agent-1",
    status: ConversationStatus = ConversationStatus.AI_ACTIVE,
    marketing_status: MarketingStatus = MarketingStatus.NEW,
    created_at: datetime | None = None,
    external_user_id: str | None = "user-1",
    channel: MessageChannel = MessageChannel.WEB_CHAT,
) -> Conversation:
    ts = created_at or FIXED_NOW
    return Conversation(
        conversation_id=conversation_id,
        agent_id=agent_id,
        channel=channel,
        external_user_id=external_user_id,
        status=status,
        marketing_status=marketing_status,
        created_at=ts,
        updated_at=ts,
    )


@contextmanager
def admin_client(
    db: AdminApiFakeDB,
    *,
    settings: DummySettings | None = None,
    auth_header: dict[str, str] | None = None,
):
    settings = settings or DummySettings()
    app = FastAPI()
    _register_exception_handlers(app)
    app.include_router(admin_router.router, prefix="/api/v1/admin")

    deps = SimpleNamespace(config=settings, db=db, cache=None)
    app.dependency_overrides[CommonDependencies] = lambda: deps

    patch_targets = [
        "app.config.get_settings",
        "app.api.auth.get_settings",
        "app.api.v1.admin.get_settings",
    ]
    with patch(patch_targets[0], return_value=settings), patch(
        patch_targets[1], return_value=settings
    ), patch(patch_targets[2], return_value=settings):
        client = TestClient(app)
        yield client, auth_header or {}


def _prod_settings() -> DummySettings:
    settings = DummySettings()
    settings.environment = "production"
    settings.debug = True
    settings.jwt_secret_key = JWT_SECRET
    settings.admin_token = "static-admin-token"
    return settings


# ── Conversations list / get ──────────────────────────────────────────────────


def test_list_conversations_returns_all():
    db = AdminApiFakeDB()
    db.conversations["c1"] = _conversation(conversation_id="c1")
    db.conversations["c2"] = _conversation(
        conversation_id="c2", status=ConversationStatus.HUMAN_ACTIVE
    )
    with admin_client(db, auth_header={"Authorization": f"Bearer {_make_jwt()}"}) as (client, headers):
        resp = client.get("/api/v1/admin/conversations", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_list_conversations_filters_by_status():
    db = AdminApiFakeDB()
    db.conversations["c1"] = _conversation(conversation_id="c1")
    db.conversations["c2"] = _conversation(
        conversation_id="c2", status=ConversationStatus.CLOSED
    )
    with admin_client(db, auth_header={"Authorization": f"Bearer {_make_jwt()}"}) as (client, headers):
        resp = client.get(
            "/api/v1/admin/conversations",
            params={"status": "CLOSED"},
            headers=headers,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["conversation_id"] == "c2"


def test_list_conversations_invalid_sort_by_returns_400():
    db = AdminApiFakeDB()
    with admin_client(db, auth_header={"Authorization": f"Bearer {_make_jwt()}"}) as (client, headers):
        resp = client.get(
            "/api/v1/admin/conversations",
            params={"sort_by": "invalid"},
            headers=headers,
        )
    assert resp.status_code == 400


def test_get_conversation_success():
    db = AdminApiFakeDB()
    db.conversations["conv-1"] = _conversation(conversation_id="conv-1")
    with admin_client(db, auth_header={"Authorization": f"Bearer {_make_jwt()}"}) as (client, headers):
        resp = client.get("/api/v1/admin/conversations/conv-1", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["conversation_id"] == "conv-1"


def test_get_conversation_not_found_returns_404():
    db = AdminApiFakeDB()
    with admin_client(db, auth_header={"Authorization": f"Bearer {_make_jwt()}"}) as (client, headers):
        resp = client.get("/api/v1/admin/conversations/missing", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"


# ── Handoff / return / reset context ────────────────────────────────────────


def test_handoff_changes_status_and_writes_audit_log():
    db = AdminApiFakeDB()
    db.conversations["conv-h"] = _conversation(conversation_id="conv-h")
    with admin_client(db, auth_header={"Authorization": f"Bearer {_make_jwt()}"}) as (client, headers):
        resp = client.post(
            "/api/v1/admin/conversations/conv-h/handoff",
            json={"admin_id": "admin-1", "reason": "Customer requested human"},
            headers=headers,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == ConversationStatus.HUMAN_ACTIVE.value
    assert body["message"] == "Conversation handed off to human"
    updated = db.conversations["conv-h"]
    assert get_enum_value(updated.status) == ConversationStatus.HUMAN_ACTIVE.value
    assert updated.handoff_reason == "Customer requested human"
    assert any(log["action"] == "handoff" for log in db.audit_logs)


def test_return_to_ai_changes_status_and_writes_audit_log():
    db = AdminApiFakeDB()
    db.conversations["conv-r"] = _conversation(
        conversation_id="conv-r", status=ConversationStatus.HUMAN_ACTIVE
    )
    with admin_client(db, auth_header={"Authorization": f"Bearer {_make_jwt()}"}) as (client, headers):
        resp = client.post(
            "/api/v1/admin/conversations/conv-r/return",
            json={"admin_id": "admin-1"},
            headers=headers,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == ConversationStatus.AI_ACTIVE.value
    assert get_enum_value(db.conversations["conv-r"].status) == ConversationStatus.AI_ACTIVE.value
    assert any(log["action"] == "return_to_ai" for log in db.audit_logs)


def test_reset_agent_context_sets_watermark():
    db = AdminApiFakeDB()
    db.conversations["conv-reset"] = _conversation(conversation_id="conv-reset")
    with (
        patch("app.api.v1.admin.utc_now", return_value=FIXED_NOW),
        admin_client(db, auth_header={"Authorization": f"Bearer {_make_jwt()}"}) as (client, headers),
    ):
        resp = client.post(
            "/api/v1/admin/conversations/conv-reset/reset-agent-context",
            json={"admin_id": "admin-1"},
            headers=headers,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["message"] == "Agent context reset"
    assert body["agent_context_reset_at"] == to_utc_iso_string(FIXED_NOW)
    assert db.conversations["conv-reset"].agent_context_reset_at == FIXED_NOW
    assert any(log["action"] == "reset_agent_context" for log in db.audit_logs)


# ── Audit log ───────────────────────────────────────────────────────────────


def test_audit_logs_list_and_filter():
    db = AdminApiFakeDB()
    db.audit_logs = [
        {
            "admin_id": "admin-a",
            "action": "handoff",
            "resource_type": "conversation",
            "resource_id": "c1",
            "metadata": {},
            "timestamp": "2025-06-15T10:00:00Z",
        },
        {
            "admin_id": "admin-b",
            "action": "return_to_ai",
            "resource_type": "conversation",
            "resource_id": "c2",
            "metadata": {},
            "timestamp": "2025-06-15T11:00:00Z",
        },
    ]
    with admin_client(db, auth_header={"Authorization": f"Bearer {_make_jwt()}"}) as (client, headers):
        all_resp = client.get("/api/v1/admin/audit", headers=headers)
        filtered = client.get(
            "/api/v1/admin/audit",
            params={"admin_id": "admin-a", "action": "handoff"},
            headers=headers,
        )
    assert all_resp.status_code == 200
    assert len(all_resp.json()) == 2
    assert filtered.status_code == 200
    assert len(filtered.json()) == 1
    assert filtered.json()[0]["admin_id"] == "admin-a"


def test_audit_logs_invalid_sort_returns_400():
    db = AdminApiFakeDB()
    with admin_client(db, auth_header={"Authorization": f"Bearer {_make_jwt()}"}) as (client, headers):
        resp = client.get("/api/v1/admin/audit", params={"sort": "sideways"}, headers=headers)
    assert resp.status_code == 400


# ── Statistics ────────────────────────────────────────────────────────────────


def test_get_stats_today_counts_by_status():
    db = AdminApiFakeDB()
    db.conversations["today-ai"] = _conversation(
        conversation_id="today-ai",
        status=ConversationStatus.AI_ACTIVE,
        created_at=FIXED_NOW - timedelta(hours=2),
    )
    db.conversations["today-human"] = _conversation(
        conversation_id="today-human",
        status=ConversationStatus.HUMAN_ACTIVE,
        marketing_status=MarketingStatus.BOOKED,
        created_at=FIXED_NOW - timedelta(hours=1),
    )
    db.conversations["yesterday"] = _conversation(
        conversation_id="yesterday",
        status=ConversationStatus.CLOSED,
        created_at=FIXED_NOW - timedelta(days=1),
    )
    mock_crm = AsyncMock(return_value=[{"id": "stage-1", "name": "New", "count": 2}])
    with (
        patch("app.api.v1.admin.utc_now", return_value=FIXED_NOW),
        patch("app.storage.postgres_crm.PostgresCRMStorage.get_stage_counts", mock_crm),
        admin_client(db, auth_header={"Authorization": f"Bearer {_make_jwt()}"}) as (client, headers),
    ):
        resp = client.get("/api/v1/admin/stats", params={"period": "today"}, headers=headers)
    assert resp.status_code == 200
    stats = resp.json()
    assert stats["period"] == "today"
    assert stats["total_conversations"] == 2
    assert stats["ai_active"] == 1
    assert stats["human_active"] == 1
    assert stats["closed"] == 0
    assert stats["marketing_booked"] == 1
    assert stats["crm_stage_stats"] == [{"id": "stage-1", "name": "New", "count": 2}]


def test_get_stats_with_comparison():
    db = AdminApiFakeDB()
    db.conversations["today-1"] = _conversation(
        conversation_id="today-1",
        created_at=FIXED_NOW - timedelta(hours=3),
    )
    db.conversations["yesterday-1"] = _conversation(
        conversation_id="yesterday-1",
        created_at=FIXED_NOW - timedelta(days=1, hours=2),
    )
    with (
        patch("app.api.v1.admin.utc_now", return_value=FIXED_NOW),
        patch(
            "app.storage.postgres_crm.PostgresCRMStorage.get_stage_counts",
            AsyncMock(return_value=[]),
        ),
        admin_client(db, auth_header={"Authorization": f"Bearer {_make_jwt()}"}) as (client, headers),
    ):
        resp = client.get(
            "/api/v1/admin/stats",
            params={"period": "today", "include_comparison": True},
            headers=headers,
        )
    assert resp.status_code == 200
    stats = resp.json()
    assert stats["total_conversations"] == 1
    assert stats["comparison"]["total_conversations"] == 0


def test_get_stats_invalid_period_returns_400():
    db = AdminApiFakeDB()
    with admin_client(db, auth_header={"Authorization": f"Bearer {_make_jwt()}"}) as (client, headers):
        resp = client.get("/api/v1/admin/stats", params={"period": "all_time"}, headers=headers)
    assert resp.status_code == 400


# ── Channel configuration ─────────────────────────────────────────────────────


def test_channel_config_returns_webhook_urls():
    settings = DummySettings()
    settings.app_url = "https://example.test"
    db = AdminApiFakeDB()
    with admin_client(
        db, settings=settings, auth_header={"Authorization": f"Bearer {_make_jwt()}"}
    ) as (client, headers):
        resp = client.get("/api/v1/admin/channel-config", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["app_url"] == "https://example.test"
    assert body["instagram_webhook_url"] == "https://example.test/api/v1/instagram/webhook"
    assert body["telegram_webhook_base"] == "https://example.test/api/v1/telegram/webhook"
    assert body["instagram_app_secret_configured"] is True


def test_channel_support_matrix_returns_payload():
    db = AdminApiFakeDB()
    with admin_client(db, auth_header={"Authorization": f"Bearer {_make_jwt()}"}) as (client, headers):
        resp = client.get("/api/v1/admin/channel-support-matrix", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "matrix" in body
    assert "channels" in body


def test_update_instagram_settings_persists_via_secrets_manager():
    db = AdminApiFakeDB()
    mgr = AsyncMock()
    mgr.set_global_setting = AsyncMock()
    with (
        patch("app.storage.postgres_secrets.get_postgres_secrets_manager", return_value=mgr),
        admin_client(db, auth_header={"Authorization": f"Bearer {_make_jwt()}"}) as (client, headers),
    ):
        resp = client.put(
            "/api/v1/admin/instagram-settings",
            json={"verify_token": "verify-token-1234"},
            headers=headers,
        )
    assert resp.status_code == 200
    assert resp.json()["message"] == "Instagram settings updated successfully"
    mgr.set_global_setting.assert_awaited_once_with(
        "instagram_verify_token", "verify-token-1234"
    )


# ── Authorization ─────────────────────────────────────────────────────────────


def test_auth_production_without_credentials_returns_401():
    db = AdminApiFakeDB()
    settings = _prod_settings()
    with admin_client(db, settings=settings) as (client, headers):
        resp = client.get("/api/v1/admin/conversations", headers=headers)
    assert resp.status_code == 401


def test_auth_production_invalid_token_returns_403():
    db = AdminApiFakeDB()
    settings = _prod_settings()
    with admin_client(
        db,
        settings=settings,
        auth_header={"Authorization": "Bearer not-a-valid-token"},
    ) as (client, headers):
        resp = client.get("/api/v1/admin/conversations", headers=headers)
    assert resp.status_code == 403


def test_auth_production_valid_jwt_allows_access():
    db = AdminApiFakeDB()
    settings = _prod_settings()
    with admin_client(
        db,
        settings=settings,
        auth_header={"Authorization": f"Bearer {_make_jwt()}"},
    ) as (client, headers):
        resp = client.get("/api/v1/admin/conversations", headers=headers)
    assert resp.status_code == 200


def test_auth_dev_bypass_without_token_allowed():
    db = AdminApiFakeDB()
    settings = DummySettings()
    settings.environment = "development"
    settings.debug = True
    settings.jwt_secret_key = None
    settings.admin_token = None
    with admin_client(db, settings=settings) as (client, headers):
        resp = client.get("/api/v1/admin/conversations", headers=headers)
    assert resp.status_code == 200
