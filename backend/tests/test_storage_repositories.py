"""Unit tests for extracted PostgreSQL storage repositories."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.models.instagram_user_profile import InstagramUserProfile
from app.storage.postgres import PostgreSQLClient
from app.storage.postgres_audit import PostgresAuditStorage
from app.storage.postgres_instagram_profiles import PostgresInstagramProfileStorage

UTC = timezone.utc
FIXED_NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def pg_client() -> PostgreSQLClient:
    return PostgreSQLClient(Settings())


@pytest.mark.asyncio
async def test_facade_create_audit_log_delegates(pg_client: PostgreSQLClient) -> None:
    expected = {"log_id": "log-1", "admin_id": "admin-1", "action": "view"}
    pg_client._audit.create_audit_log = AsyncMock(return_value=expected)

    result = await pg_client.create_audit_log(
        admin_id="admin-1",
        action="view",
        resource_type="conversation",
        resource_id="conv-1",
        metadata={"key": "value"},
    )

    pg_client._audit.create_audit_log.assert_awaited_once_with(
        "admin-1", "view", "conversation", "conv-1", {"key": "value"}
    )
    assert result == expected


@pytest.mark.asyncio
async def test_facade_list_audit_logs_delegates(pg_client: PostgreSQLClient) -> None:
    expected = [{"log_id": "log-1"}]
    pg_client._audit.list_audit_logs = AsyncMock(return_value=expected)

    result = await pg_client.list_audit_logs(
        admin_id="admin-1",
        action="handoff",
        sort_desc=False,
        limit=5,
    )

    pg_client._audit.list_audit_logs.assert_awaited_once_with(
        admin_id="admin-1",
        resource_type=None,
        action="handoff",
        start_date=None,
        end_date=None,
        sort_desc=False,
        limit=5,
    )
    assert result == expected


@pytest.mark.asyncio
async def test_facade_instagram_profile_delegates(pg_client: PostgreSQLClient) -> None:
    profile = InstagramUserProfile(
        external_user_id="ig-1",
        name="Test User",
        username="testuser",
        profile_pic="https://example.com/pic.jpg",
        updated_at=FIXED_NOW,
        ttl=0,
    )
    pg_client._instagram.create_or_update_instagram_profile = AsyncMock(return_value=profile)
    pg_client._instagram.get_instagram_profile = AsyncMock(return_value=profile)

    created = await pg_client.create_or_update_instagram_profile(profile)
    fetched = await pg_client.get_instagram_profile("ig-1")

    pg_client._instagram.create_or_update_instagram_profile.assert_awaited_once_with(profile)
    pg_client._instagram.get_instagram_profile.assert_awaited_once_with("ig-1")
    assert created == profile
    assert fetched == profile


@pytest.mark.asyncio
async def test_audit_storage_create_executes_insert() -> None:
    storage = PostgresAuditStorage()
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("app.storage.postgres_audit.get_pool", AsyncMock(return_value=mock_pool)), patch(
        "app.storage.postgres_audit.utc_now", return_value=FIXED_NOW
    ), patch("app.storage.postgres_audit.to_utc_iso_string", return_value="2025-06-15T12:00:00Z"):
        result = await storage.create_audit_log(
            admin_id="admin-a",
            action="delete",
            resource_type="agent",
            resource_id="agent-1",
            metadata={"reason": "cleanup"},
        )

    mock_conn.execute.assert_awaited_once()
    sql, *args = mock_conn.execute.await_args.args
    assert "INSERT INTO audit_logs" in sql
    assert args[0].startswith("agent_agent-1_")
    assert args[1] == "admin-a"
    assert args[2] == "delete"
    assert args[3] == "agent"
    assert args[4] == "agent-1"
    assert args[5] == FIXED_NOW
    assert '"reason"' in args[6]
    assert result["admin_id"] == "admin-a"
    assert result["metadata"] == {"reason": "cleanup"}


@pytest.mark.asyncio
async def test_audit_storage_list_builds_filter_query() -> None:
    storage = PostgresAuditStorage()
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[])
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    start = FIXED_NOW.replace(hour=0)
    end = FIXED_NOW.replace(hour=23)

    with patch("app.storage.postgres_audit.get_pool", AsyncMock(return_value=mock_pool)):
        await storage.list_audit_logs(
            admin_id="admin-a",
            action="view",
            start_date=start,
            end_date=end,
            sort_desc=True,
            limit=10,
        )

    mock_conn.fetch.assert_awaited_once()
    sql, *params = mock_conn.fetch.await_args.args
    assert "admin_id = $1" in sql
    assert "action = $2" in sql
    assert "timestamp >= $3" in sql
    assert "timestamp <= $4" in sql
    assert "ORDER BY timestamp DESC" in sql
    assert "LIMIT $5" in sql
    assert params == ["admin-a", "view", start, end, 10]


@pytest.mark.asyncio
async def test_instagram_storage_upsert_executes_sql() -> None:
    storage = PostgresInstagramProfileStorage()
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    profile = InstagramUserProfile(
        external_user_id="ig-42",
        name="Alice",
        username="alice",
        profile_pic=None,
        updated_at=FIXED_NOW,
        ttl=0,
    )

    with patch(
        "app.storage.postgres_instagram_profiles.get_pool", AsyncMock(return_value=mock_pool)
    ):
        result = await storage.create_or_update_instagram_profile(profile)

    mock_conn.execute.assert_awaited_once()
    sql, *args = mock_conn.execute.await_args.args
    assert "INSERT INTO instagram_profiles" in sql
    assert "ON CONFLICT (external_user_id)" in sql
    assert args[0] == "ig-42"
    assert args[1] == "Alice"
    assert result == profile
