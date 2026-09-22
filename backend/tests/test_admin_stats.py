"""Unit tests for admin stats aggregation helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.conversation import Conversation, ConversationStatus, MarketingStatus
from app.storage.postgres import (
    _period_stats_from_conversations,
    diff_period_stats,
    fetch_conversation_period_stats,
)
from tests.conftest import FakeDB

UTC = timezone.utc
FIXED_NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)


def _conv(
    conversation_id: str,
    *,
    created_at: datetime,
    status: ConversationStatus = ConversationStatus.AI_ACTIVE,
    marketing_status: MarketingStatus = MarketingStatus.NEW,
) -> Conversation:
    return Conversation(
        conversation_id=conversation_id,
        agent_id="agent-1",
        status=status,
        marketing_status=marketing_status,
        created_at=created_at,
        updated_at=created_at,
    )


def test_period_stats_from_conversations_matches_status_counts():
    rows = [
        _conv("a", created_at=FIXED_NOW - timedelta(hours=1)),
        _conv(
            "b",
            created_at=FIXED_NOW - timedelta(hours=2),
            status=ConversationStatus.HUMAN_ACTIVE,
            marketing_status=MarketingStatus.BOOKED,
        ),
        _conv(
            "c",
            created_at=FIXED_NOW - timedelta(days=1),
            status=ConversationStatus.CLOSED,
        ),
    ]
    start = datetime(FIXED_NOW.year, FIXED_NOW.month, FIXED_NOW.day, tzinfo=UTC)
    stats = _period_stats_from_conversations(rows, start, FIXED_NOW, end_exclusive=False)

    assert stats["total_conversations"] == 2
    assert stats["ai_active"] == 1
    assert stats["human_active"] == 1
    assert stats["marketing_booked"] == 1


def test_diff_period_stats_subtracts_counts():
    current = {"total_conversations": 2, "ai_active": 1, "needs_human": 0, "human_active": 1,
               "closed": 0, "marketing_new": 1, "marketing_booked": 1,
               "marketing_no_response": 0, "marketing_rejected": 0}
    previous = {"total_conversations": 1, "ai_active": 1, "needs_human": 0, "human_active": 0,
                "closed": 0, "marketing_new": 1, "marketing_booked": 0,
                "marketing_no_response": 0, "marketing_rejected": 0}
    assert diff_period_stats(current, previous)["total_conversations"] == 1


@pytest.mark.asyncio
async def test_fetch_conversation_period_stats_uses_fake_db_fallback():
    db = FakeDB()
    db.conversations["today"] = _conv("today", created_at=FIXED_NOW - timedelta(hours=1))
    db.conversations["yesterday"] = _conv(
        "yesterday", created_at=FIXED_NOW - timedelta(days=1)
    )
    start = datetime(FIXED_NOW.year, FIXED_NOW.month, FIXED_NOW.day, tzinfo=UTC)
    stats = await fetch_conversation_period_stats(db, start, FIXED_NOW)

    assert stats["total_conversations"] == 1
