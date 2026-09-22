"""Unit tests for ConversationStatusService."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.conversation import Conversation, ConversationStatus, MarketingStatus
from app.models.message import MessageChannel
from app.services.conversation_status_service import ConversationStatusService


def _conversation(
    *,
    conversation_id: str = "conv-1",
    status: ConversationStatus = ConversationStatus.AI_ACTIVE,
) -> Conversation:
    now = datetime.now(timezone.utc)
    return Conversation(
        conversation_id=conversation_id,
        agent_id="agent-1",
        channel=MessageChannel.WEB_CHAT,
        external_user_id="user-1",
        status=status,
        marketing_status=MarketingStatus.NEW,
        created_at=now,
        updated_at=now,
        metadata={},
    )


class FakeDB:
    def __init__(self, conversation: Conversation):
        self.conversation = conversation
        self.update_calls: list[dict[str, Any]] = []

    async def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        if self.conversation.conversation_id != conversation_id:
            return None
        return self.conversation

    async def update_conversation(
        self,
        conversation_id: str,
        status: Optional[ConversationStatus] = None,
        handoff_reason: Optional[str] = None,
        request_type: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional[Conversation]:
        self.update_calls.append(
            {
                "conversation_id": conversation_id,
                "status": status,
                "handoff_reason": handoff_reason,
                "request_type": request_type,
                **kwargs,
            }
        )
        if status is not None:
            self.conversation.status = status
        if handoff_reason is not None:
            self.conversation.handoff_reason = handoff_reason
        if "metadata" in kwargs:
            self.conversation.metadata = kwargs["metadata"]
        return self.conversation

    async def get_agent(self, agent_id: str) -> dict[str, Any]:
        return {
            "config": {
                "agent_id": agent_id,
                "profile": {"agent_display_name": "Test Agent"},
            }
        }


class FakeBroadcastManager:
    def __init__(self) -> None:
        self.conversation_updates: list[Conversation] = []
        self.escalations: list[tuple[Conversation, Optional[str]]] = []

    async def broadcast_conversation_update(self, conversation: Conversation) -> None:
        self.conversation_updates.append(conversation)

    async def broadcast_new_escalation(
        self, conversation: Conversation, escalation_reason: Optional[str] = None
    ) -> None:
        self.escalations.append((conversation, escalation_reason))


@pytest.mark.asyncio
async def test_storage_update_has_no_broadcast_side_effects():
    db = FakeDB(_conversation())
    broadcast = FakeBroadcastManager()
    service = ConversationStatusService(db, broadcast_manager=broadcast)

    await db.update_conversation("conv-1", metadata={"k": "v"})

    assert len(db.update_calls) == 1
    assert broadcast.conversation_updates == []
    assert broadcast.escalations == []


@pytest.mark.asyncio
async def test_service_broadcasts_on_non_escalation_update():
    db = FakeDB(_conversation())
    broadcast = FakeBroadcastManager()
    service = ConversationStatusService(db, broadcast_manager=broadcast)

    updated = await service.update_conversation(
        "conv-1",
        status=ConversationStatus.HUMAN_ACTIVE,
        handoff_reason="Manual handoff",
    )

    assert updated is not None
    assert len(db.update_calls) == 1
    assert broadcast.escalations == []
    assert len(broadcast.conversation_updates) == 1
    assert broadcast.conversation_updates[0].conversation_id == "conv-1"


@pytest.mark.asyncio
async def test_service_broadcasts_escalation_and_schedules_notification():
    db = FakeDB(_conversation(status=ConversationStatus.AI_ACTIVE))
    broadcast = FakeBroadcastManager()
    notification_service = MagicMock()
    notification_service.send_escalation_notification = AsyncMock()
    service = ConversationStatusService(
        db,
        broadcast_manager=broadcast,
        notification_service_factory=lambda: notification_service,
    )

    updated = await service.update_conversation(
        "conv-1",
        status=ConversationStatus.NEEDS_HUMAN,
        handoff_reason="Content moderation violation",
    )

    assert updated is not None
    assert len(broadcast.escalations) == 1
    assert broadcast.escalations[0][1] == "Content moderation violation"
    assert broadcast.conversation_updates == []
    assert notification_service.send_escalation_notification.await_count == 0


@pytest.mark.asyncio
async def test_service_does_not_re_escalate_when_already_needs_human():
    db = FakeDB(_conversation(status=ConversationStatus.NEEDS_HUMAN))
    broadcast = FakeBroadcastManager()
    service = ConversationStatusService(db, broadcast_manager=broadcast)

    await service.update_conversation(
        "conv-1",
        status=ConversationStatus.NEEDS_HUMAN,
        handoff_reason="Updated reason",
    )

    assert broadcast.escalations == []
    assert len(broadcast.conversation_updates) == 1


@pytest.mark.asyncio
async def test_notification_failure_does_not_break_update():
    db = FakeDB(_conversation(status=ConversationStatus.AI_ACTIVE))
    broadcast = FakeBroadcastManager()

    def broken_factory() -> Any:
        svc = MagicMock()
        svc.send_escalation_notification = AsyncMock(side_effect=RuntimeError("notify failed"))
        return svc

    service = ConversationStatusService(
        db,
        broadcast_manager=broadcast,
        notification_service_factory=broken_factory,
    )

    updated = await service.update_conversation(
        "conv-1",
        status=ConversationStatus.NEEDS_HUMAN,
        handoff_reason="Escalation required",
    )

    assert updated is not None
    assert len(db.update_calls) == 1
    assert len(broadcast.escalations) == 1
