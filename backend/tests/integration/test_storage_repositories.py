"""Integration tests for extracted PostgreSQL storage repositories."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import asyncpg
import pytest

from app.models.instagram_user_profile import InstagramUserProfile
from app.storage.postgres import PostgreSQLClient, get_pool
from app.storage.postgres_audit import PostgresAuditStorage
from app.storage.postgres_instagram_profiles import PostgresInstagramProfileStorage

pytestmark = pytest.mark.integration

UTC = timezone.utc
FIXED_NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)


async def _truncate_audit_and_profiles(conn: asyncpg.Connection) -> None:
    await conn.execute("TRUNCATE TABLE audit_logs, instagram_profiles")


@pytest.mark.asyncio
async def test_audit_storage_create_and_list(pg_client: PostgreSQLClient) -> None:
    storage = PostgresAuditStorage()
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _truncate_audit_and_profiles(conn)

    created = await storage.create_audit_log(
        admin_id="admin-x",
        action="view",
        resource_type="conversation",
        resource_id="conv-99",
        metadata={"source": "integration"},
    )

    assert created["admin_id"] == "admin-x"
    assert created["action"] == "view"
    assert created["metadata"] == {"source": "integration"}

    logs = await storage.list_audit_logs(admin_id="admin-x", limit=10)
    assert len(logs) == 1
    assert logs[0]["log_id"] == created["log_id"]


@pytest.mark.asyncio
async def test_audit_storage_filters_admin_action_dates_sort_limit(
    pg_client: PostgreSQLClient,
) -> None:
    storage = PostgresAuditStorage()
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _truncate_audit_and_profiles(conn)
        for log_id, admin_id, action, ts in [
            ("log-old", "admin-a", "view", FIXED_NOW - timedelta(days=2)),
            ("log-match", "admin-a", "handoff", FIXED_NOW - timedelta(hours=1)),
            ("log-other-admin", "admin-b", "handoff", FIXED_NOW - timedelta(hours=1)),
            ("log-future", "admin-a", "handoff", FIXED_NOW + timedelta(days=1)),
        ]:
            await conn.execute(
                """
                INSERT INTO audit_logs (
                    log_id, admin_id, action, resource_type, resource_id, timestamp, metadata
                ) VALUES ($1, $2, $3, 'conversation', 'conv-1', $4, '{}'::jsonb)
                """,
                log_id,
                admin_id,
                action,
                ts,
            )

    logs = await storage.list_audit_logs(
        admin_id="admin-a",
        action="handoff",
        start_date=FIXED_NOW - timedelta(days=1),
        end_date=FIXED_NOW,
        sort_desc=True,
        limit=1,
    )
    assert len(logs) == 1
    assert logs[0]["log_id"] == "log-match"

    asc_logs = await storage.list_audit_logs(sort_desc=False, limit=2)
    assert len(asc_logs) == 2
    assert asc_logs[0]["log_id"] == "log-old"


@pytest.mark.asyncio
async def test_facade_audit_delegation_on_real_db(pg_client: PostgreSQLClient) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _truncate_audit_and_profiles(conn)

    entry = await pg_client.create_audit_log(
        admin_id="facade-admin",
        action="update",
        resource_type="agent",
        resource_id="agent-1",
    )
    logs = await pg_client.list_audit_logs(admin_id="facade-admin")
    assert any(row["log_id"] == entry["log_id"] for row in logs)


@pytest.mark.asyncio
async def test_instagram_storage_create_and_get(pg_client: PostgreSQLClient) -> None:
    storage = PostgresInstagramProfileStorage()
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _truncate_audit_and_profiles(conn)

    profile = InstagramUserProfile(
        external_user_id="ig-int-1",
        name="Integration User",
        username="int_user",
        profile_pic="https://example.com/avatar.jpg",
        updated_at=FIXED_NOW,
        ttl=0,
    )
    await storage.create_or_update_instagram_profile(profile)

    fetched = await storage.get_instagram_profile("ig-int-1")
    assert fetched is not None
    assert fetched.external_user_id == "ig-int-1"
    assert fetched.username == "int_user"

    profile.name = "Updated Name"
    await storage.create_or_update_instagram_profile(profile)
    updated = await storage.get_instagram_profile("ig-int-1")
    assert updated is not None
    assert updated.name == "Updated Name"
