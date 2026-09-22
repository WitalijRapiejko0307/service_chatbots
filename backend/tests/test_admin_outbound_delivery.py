"""Admin outbound delivery: honest HTTP semantics on channel send failure."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1.admin import SendAdminMessageRequest, send_admin_message
from app.models.conversation import Conversation, ConversationStatus
from app.models.message import MessageChannel
from app.utils.datetime_utils import utc_now
from app.utils.enum_helpers import get_enum_value
from tests.conftest import FakeDB


class AdminOutboundFakeDB(FakeDB):
    """FakeDB with create_message and audit log capture for admin send tests."""

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
        }
        self.audit_logs.append(entry)
        return entry


def _conversation(
    *,
    conversation_id: str = "conv-admin-1",
    channel: MessageChannel = MessageChannel.TELEGRAM,
    status: ConversationStatus = ConversationStatus.HUMAN_ACTIVE,
) -> Conversation:
    now = utc_now()
    return Conversation(
        conversation_id=conversation_id,
        agent_id="agent-1",
        channel=channel,
        external_user_id="customer-1",
        status=status,
        created_at=now,
        updated_at=now,
        metadata={},
    )


def _request(**kwargs) -> SendAdminMessageRequest:
    defaults = {"admin_id": "admin-1", "content": "hello from admin"}
    defaults.update(kwargs)
    return SendAdminMessageRequest(**defaults)


@pytest.mark.asyncio
async def test_send_admin_message_success_returns_payload_and_success_audit():
    db = AdminOutboundFakeDB()
    conv = _conversation()
    db.conversations[conv.conversation_id] = conv
    sender = AsyncMock()
    sender.send_message = AsyncMock(return_value=None)

    with patch("app.api.v1.admin.get_channel_sender", return_value=sender):
        response = await send_admin_message(
            conv.conversation_id,
            _request(),
            deps=SimpleNamespace(db=db),
            _admin="admin-1",
        )

    assert response.content == "hello from admin"
    assert len(db.messages) == 1
    sender.send_message.assert_awaited_once()
    assert [log["action"] for log in db.audit_logs] == ["send_message"]


@pytest.mark.asyncio
async def test_send_admin_message_delivery_exception_returns_502_without_leak():
    db = AdminOutboundFakeDB()
    conv = _conversation()
    db.conversations[conv.conversation_id] = conv
    sender = AsyncMock()
    sender.send_message = AsyncMock(side_effect=RuntimeError("network down"))

    with patch("app.api.v1.admin.get_channel_sender", return_value=sender):
        with pytest.raises(HTTPException) as exc_info:
            await send_admin_message(
                conv.conversation_id,
                _request(),
                deps=SimpleNamespace(db=db),
                _admin="admin-1",
            )

    exc = exc_info.value
    assert exc.status_code == 502
    assert exc.detail == f"Failed to deliver message to {MessageChannel.TELEGRAM.value}"
    assert "network down" not in str(exc.detail)
    assert len(db.messages) == 1
    assert "send_message" not in [log["action"] for log in db.audit_logs]
    assert [log["action"] for log in db.audit_logs] == ["send_message_failed"]


@pytest.mark.asyncio
async def test_send_admin_message_value_error_returns_400():
    db = AdminOutboundFakeDB()
    conv = _conversation()
    db.conversations[conv.conversation_id] = conv
    sender = AsyncMock()
    sender.send_message = AsyncMock(side_effect=ValueError("invalid recipient"))

    with patch("app.api.v1.admin.get_channel_sender", return_value=sender):
        with pytest.raises(HTTPException) as exc_info:
            await send_admin_message(
                conv.conversation_id,
                _request(),
                deps=SimpleNamespace(db=db),
                _admin="admin-1",
            )

    exc = exc_info.value
    assert exc.status_code == 400
    assert "invalid recipient" in str(exc.detail)
    assert db.audit_logs == []


@pytest.mark.asyncio
async def test_send_admin_message_delivery_failure_skips_success_audit():
    db = AdminOutboundFakeDB()
    conv = _conversation(channel=MessageChannel.INSTAGRAM)
    db.conversations[conv.conversation_id] = conv
    sender = AsyncMock()
    sender.send_message = AsyncMock(side_effect=OSError("connection reset"))

    with patch("app.api.v1.admin.get_channel_sender", return_value=sender):
        with pytest.raises(HTTPException) as exc_info:
            await send_admin_message(
                conv.conversation_id,
                _request(),
                deps=SimpleNamespace(db=db),
                _admin="admin-1",
            )

    assert exc_info.value.status_code == 502
    success_logs = [log for log in db.audit_logs if log["action"] == "send_message"]
    assert success_logs == []
    failed_logs = [log for log in db.audit_logs if log["action"] == "send_message_failed"]
    assert len(failed_logs) == 1
    assert failed_logs[0]["metadata"]["channel"] == get_enum_value(conv.channel)
