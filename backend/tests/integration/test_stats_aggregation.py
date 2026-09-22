"""Integration tests for SQL-backed admin stats and audit log filtering."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import asyncpg
import pytest

from app.models.conversation import Conversation, ConversationStatus, MarketingStatus
from app.storage.postgres import PostgreSQLClient, get_pool

pytestmark = pytest.mark.integration

UTC = timezone.utc
FIXED_NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)


async def _insert_conversation(
    conn: asyncpg.Connection,
    *,
    conversation_id: str,
    created_at: datetime,
    status: str = ConversationStatus.AI_ACTIVE.value,
    marketing_status: str = MarketingStatus.NEW.value,
) -> None:
    await conn.execute(
        """
        INSERT INTO conversations (
            conversation_id, agent_id, channel, status, marketing_status, created_at, updated_at
        ) VALUES ($1, 'agent-int', 'web_chat', $2, $3, $4, $4)
        """,
        conversation_id,
        status,
        marketing_status,
        created_at,
    )


async def _insert_audit_log(
    conn: asyncpg.Connection,
    *,
    log_id: str,
    admin_id: str,
    action: str,
    timestamp: datetime,
) -> None:
    await conn.execute(
        """
        INSERT INTO audit_logs (
            log_id, admin_id, action, resource_type, resource_id, timestamp, metadata
        ) VALUES ($1, $2, $3, 'conversation', 'conv-1', $4, '{}'::jsonb)
        """,
        log_id,
        admin_id,
        action,
        timestamp,
    )


@pytest.mark.asyncio
async def test_get_conversation_period_stats_aggregates_by_status(
    pg_client: PostgreSQLClient,
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _insert_conversation(
            conn,
            conversation_id="stats-today-ai",
            created_at=FIXED_NOW - timedelta(hours=2),
            status=ConversationStatus.AI_ACTIVE.value,
        )
        await _insert_conversation(
            conn,
            conversation_id="stats-today-human",
            created_at=FIXED_NOW - timedelta(hours=1),
            status=ConversationStatus.HUMAN_ACTIVE.value,
            marketing_status=MarketingStatus.BOOKED.value,
        )
        await _insert_conversation(
            conn,
            conversation_id="stats-yesterday",
            created_at=FIXED_NOW - timedelta(days=1),
            status=ConversationStatus.CLOSED.value,
        )

    start = datetime(FIXED_NOW.year, FIXED_NOW.month, FIXED_NOW.day, tzinfo=UTC)
    stats = await pg_client.get_conversation_period_stats(
        start, FIXED_NOW, end_exclusive=False
    )

    assert stats["total_conversations"] == 2
    assert stats["ai_active"] == 1
    assert stats["human_active"] == 1
    assert stats["closed"] == 0
    assert stats["marketing_booked"] == 1


@pytest.mark.asyncio
async def test_get_conversation_period_stats_no_row_limit(pg_client: PostgreSQLClient) -> None:
    """Stats must count all rows in range, not cap at 1000 like the old Python path."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        for i in range(1001):
            await _insert_conversation(
                conn,
                conversation_id=f"stats-bulk-{i}",
                created_at=FIXED_NOW - timedelta(minutes=i),
            )

    start = FIXED_NOW - timedelta(days=1)
    stats = await pg_client.get_conversation_period_stats(
        start, FIXED_NOW, end_exclusive=False
    )
    assert stats["total_conversations"] == 1001


@pytest.mark.asyncio
async def test_get_conversation_period_stats_exclusive_end(
    pg_client: PostgreSQLClient,
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _insert_conversation(
            conn,
            conversation_id="stats-boundary",
            created_at=FIXED_NOW.replace(hour=0, minute=0, second=0, microsecond=0),
        )

    day_start = FIXED_NOW.replace(hour=0, minute=0, second=0, microsecond=0)
    prev_stats = await pg_client.get_conversation_period_stats(
        day_start - timedelta(days=1),
        day_start,
        end_exclusive=True,
    )
    assert prev_stats["total_conversations"] == 0


@pytest.mark.asyncio
async def test_list_audit_logs_filters_dates_in_sql(pg_client: PostgreSQLClient) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE audit_logs")
        await _insert_audit_log(
            conn,
            log_id="log-old",
            admin_id="admin-a",
            action="view",
            timestamp=FIXED_NOW - timedelta(days=2),
        )
        await _insert_audit_log(
            conn,
            log_id="log-in-range",
            admin_id="admin-a",
            action="handoff",
            timestamp=FIXED_NOW - timedelta(hours=1),
        )
        await _insert_audit_log(
            conn,
            log_id="log-future",
            admin_id="admin-b",
            action="view",
            timestamp=FIXED_NOW + timedelta(days=1),
        )

    start = FIXED_NOW - timedelta(days=1)
    logs = await pg_client.list_audit_logs(
        admin_id="admin-a",
        action="handoff",
        start_date=start,
        end_date=FIXED_NOW,
        sort_desc=True,
        limit=10,
    )

    assert len(logs) == 1
    assert logs[0]["log_id"] == "log-in-range"
