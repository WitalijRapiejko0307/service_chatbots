"""Regression tests for provider message id deduplication SQL."""

from __future__ import annotations

import json

import asyncpg
import pytest

from app.models.conversation import Conversation
from app.models.message import Message, MessageRole
from app.storage.postgres import PostgreSQLClient, get_pool

pytestmark = pytest.mark.integration


async def _insert_message_row(
    conn: asyncpg.Connection,
    *,
    conversation_id: str,
    message_id: str,
    agent_id: str = "agent-int",
    external_message_id: str | None = None,
    metadata: str | dict | None = "{}",
) -> None:
    if metadata is None:
        meta_sql = "NULL"
        meta_param = None
    elif isinstance(metadata, dict):
        meta_sql = "$5::jsonb"
        meta_param = json.dumps(metadata)
    else:
        meta_sql = "$5::jsonb"
        meta_param = metadata

    if meta_param is None:
        await conn.execute(
            f"""
            INSERT INTO messages (
                conversation_id, message_id, agent_id, role, content, channel,
                external_message_id, timestamp, metadata
            ) VALUES ($1, $2, $3, 'agent', 'test', 'telegram', $4, NOW(), {meta_sql})
            """,
            conversation_id,
            message_id,
            agent_id,
            external_message_id,
        )
    else:
        await conn.execute(
            f"""
            INSERT INTO messages (
                conversation_id, message_id, agent_id, role, content, channel,
                external_message_id, timestamp, metadata
            ) VALUES ($1, $2, $3, 'agent', 'test', 'telegram', $4, NOW(), {meta_sql})
            """,
            conversation_id,
            message_id,
            agent_id,
            external_message_id,
            meta_param,
        )


@pytest.mark.asyncio
async def test_provider_message_id_exists_after_stamp(pg_client: PostgreSQLClient) -> None:
    """Stamped secondary provider ids must be found (media + caption scenario)."""
    conv = Conversation(conversation_id="conv-dedup-1", agent_id="agent-int")
    await pg_client.create_conversation(conv)

    msg = Message(
        message_id="msg-dedup-1",
        conversation_id=conv.conversation_id,
        agent_id=conv.agent_id,
        role=MessageRole.AGENT,
        content="photo + caption",
    )
    assert await pg_client.try_create_message(msg) is True

    await pg_client.stamp_provider_message_ids(
        conv.conversation_id, msg.message_id, ["mid-1", "mid-2"]
    )

    assert await pg_client.provider_message_id_exists(conv.conversation_id, "mid-1") is True
    assert await pg_client.provider_message_id_exists(conv.conversation_id, "mid-2") is True
    assert await pg_client.provider_message_id_exists(conv.conversation_id, "mid-unknown") is False


@pytest.mark.asyncio
async def test_provider_message_id_exists_by_external_message_id(
    pg_client: PostgreSQLClient,
) -> None:
    conv = Conversation(conversation_id="conv-dedup-2", agent_id="agent-int")
    await pg_client.create_conversation(conv)

    msg = Message(
        message_id="msg-dedup-2",
        conversation_id=conv.conversation_id,
        agent_id=conv.agent_id,
        role=MessageRole.AGENT,
        content="hello",
        external_message_id="ext-primary",
    )
    assert await pg_client.try_create_message(msg) is True

    assert await pg_client.provider_message_id_exists(conv.conversation_id, "ext-primary") is True
    assert await pg_client.provider_message_id_exists(conv.conversation_id, "ext-other") is False


@pytest.mark.asyncio
async def test_provider_message_id_exists_metadata_edge_cases(
    pg_client: PostgreSQLClient,
) -> None:
    conv = Conversation(conversation_id="conv-dedup-3", agent_id="agent-int")
    await pg_client.create_conversation(conv)

    pool = await get_pool()
    async with pool.acquire() as conn:
        await _insert_message_row(
            conn,
            conversation_id=conv.conversation_id,
            message_id="msg-null-meta",
            metadata=None,
        )
        await _insert_message_row(
            conn,
            conversation_id=conv.conversation_id,
            message_id="msg-no-key",
            metadata={},
        )
        await _insert_message_row(
            conn,
            conversation_id=conv.conversation_id,
            message_id="msg-empty-list",
            metadata={"provider_message_ids": []},
        )

    for message_id in ("msg-null-meta", "msg-no-key", "msg-empty-list"):
        assert await pg_client.provider_message_id_exists(conv.conversation_id, "orphan-id") is False
