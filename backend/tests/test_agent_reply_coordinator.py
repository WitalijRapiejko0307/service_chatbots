"""Tests for agent_reply_coordinator (debounce, timers, auto-steps)."""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.chains.agent_chain import workflow_config_hash
from app.models.agent_config import AgentConfig
from app.models.conversation import Conversation, ConversationStatus
from app.models.message import Message, MessageChannel, MessageRole
from app.services.agent_reply_coordinator import (
    KEY_AUTO_DUE,
    KEY_AUTO_IDX,
    KEY_AUTO_PAY,
    KEY_DUE,
    KEY_LAST_INPUT_PREFIX,
    KEY_LAST_PLAIN_PREFIX,
    KEY_TIMER_DUE,
    KEY_VER_PREFIX,
    execute_agent_reply,
    execute_auto_step_trigger,
    execute_timer_trigger,
    notify_user_message_saved,
    schedule_auto_step,
    schedule_timer_trigger,
)
from app.utils.datetime_utils import utc_now
from app.utils.enum_helpers import get_enum_value
from tests.conftest import DummySettings, FakeDB


# ---------------------------------------------------------------------------
# Local fakes
# ---------------------------------------------------------------------------


class FakeRedis:
    """In-memory Redis stand-in for coordinator tests."""

    def __init__(self) -> None:
        self.strings: dict[str, str] = {}
        self.zsets: dict[str, dict[str, float]] = {}
        self.sets: dict[str, set[str]] = {}
        self.ttls: dict[str, int] = {}
        self._nx_keys: set[str] = set()

    async def ping(self) -> bool:
        return True

    async def incr(self, key: str) -> int:
        cur = int(self.strings.get(key, "0"))
        cur += 1
        self.strings[key] = str(cur)
        return cur

    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        self.strings[key] = value
        if ttl is not None:
            self.ttls[key] = ttl

    async def get(self, key: str) -> Optional[str]:
        return self.strings.get(key)

    async def delete(self, key: str) -> None:
        self.strings.pop(key, None)
        self.zsets.pop(key, None)
        self.sets.pop(key, None)
        self.ttls.pop(key, None)
        self._nx_keys.discard(key)

    async def zadd(self, key: str, mapping: dict[str, float]) -> None:
        z = self.zsets.setdefault(key, {})
        z.update(mapping)

    async def zrem(self, key: str, *members: str) -> None:
        z = self.zsets.get(key, {})
        for m in members:
            z.pop(m, None)

    async def zrangebyscore(
        self, key: str, _min: str, max_score: float, num: int = 50
    ) -> list[str]:
        z = self.zsets.get(key, {})
        items = [(m, s) for m, s in z.items() if s <= max_score]
        items.sort(key=lambda x: x[1])
        return [m for m, _ in items[:num]]

    async def zscore(self, key: str, member: str) -> Optional[float]:
        return self.zsets.get(key, {}).get(member)

    async def set_nx_ex(self, key: str, value: str, _ttl: int) -> bool:
        if key in self._nx_keys:
            return False
        self._nx_keys.add(key)
        self.strings[key] = value
        return True

    async def sadd(self, key: str, *members: str) -> None:
        s = self.sets.setdefault(key, set())
        s.update(members)

    async def srem(self, key: str, *members: str) -> None:
        s = self.sets.get(key, set())
        for m in members:
            s.discard(m)

    async def smembers(self, key: str) -> set[str]:
        return set(self.sets.get(key, set()))

    async def sismember(self, key: str, member: str) -> bool:
        return member in self.sets.get(key, set())

    async def expire(self, key: str, ttl: int) -> None:
        self.ttls[key] = ttl


class CoordinatorFakeDB(FakeDB):
    """FakeDB with create_message for coordinator outbound paths."""

    async def create_message(self, message: Message) -> Message:
        await self.try_create_message(message)
        return message


class DebounceSettings(DummySettings):
    agent_reply_debounce_seconds = 5


def _minimal_agent_config(agent_id: str = "agent-1") -> dict[str, Any]:
    return {
        "agent_id": agent_id,
        "project": "test",
        "profile": {
            "agent_display_name": "Test Agent",
            "company_display_name": "Test Co",
        },
    }


def _conversation(
    *,
    conversation_id: str = "conv-1",
    agent_id: str = "agent-1",
    channel: MessageChannel = MessageChannel.TELEGRAM,
    status: ConversationStatus = ConversationStatus.AI_ACTIVE,
    external_user_name: str | None = None,
) -> Conversation:
    now = utc_now()
    return Conversation(
        conversation_id=conversation_id,
        agent_id=agent_id,
        channel=channel,
        external_user_id="user-1",
        external_user_name=external_user_name,
        status=status,
        created_at=now,
        updated_at=now,
        metadata={},
    )


def _seed_agent(db: CoordinatorFakeDB, agent_id: str = "agent-1") -> AgentConfig:
    config_dict = _minimal_agent_config(agent_id)
    db.agents[agent_id] = {"config": config_dict}
    return AgentConfig.from_dict(config_dict)


@contextmanager
def _coordinator_patches(
    *,
    db: CoordinatorFakeDB,
    redis: FakeRedis,
    settings: DummySettings | None = None,
):
    settings = settings or DummySettings()
    with (
        patch("app.dependencies.get_db", return_value=db),
        patch("app.services.agent_reply_coordinator.get_settings", return_value=settings),
        patch("app.services.agent_reply_coordinator.get_redis_client", return_value=redis),
    ):
        yield


# ---------------------------------------------------------------------------
# execute_agent_reply
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_agent_reply_success_path():
    db = CoordinatorFakeDB()
    redis = FakeRedis()
    conv = _conversation()
    db.conversations[conv.conversation_id] = conv
    _seed_agent(db)

    ver_key = f"{KEY_VER_PREFIX}{conv.conversation_id}"
    redis.strings[ver_key] = "3"
    await redis.set(f"{KEY_LAST_INPUT_PREFIX}{conv.conversation_id}", "Привет")
    await redis.set(f"{KEY_LAST_PLAIN_PREFIX}{conv.conversation_id}", "Привет")

    sender = AsyncMock()
    agent_service = MagicMock()
    agent_service.process_message = AsyncMock(
        return_value={
            "response": "Здравствуйте!",
            "agent_message_id": "msg-agent-1",
            "agent_message_timestamp": "2026-01-01T00:00:00Z",
        }
    )

    history = [{"role": "user", "content": "Привет"}]

    with _coordinator_patches(db=db, redis=redis):
        with (
            patch(
                "app.services.agent_reply_coordinator.build_conversation_history_for_agent",
                new=AsyncMock(return_value=history),
            ),
            patch(
                "app.services.agent_reply_coordinator.create_agent_service",
                return_value=agent_service,
            ),
            patch("app.services.channel_sender.get_channel_sender", return_value=sender),
        ):
            await execute_agent_reply(conv.conversation_id, expected_version=3)

    agent_service.process_message.assert_awaited_once()
    call_kw = agent_service.process_message.await_args.kwargs
    assert call_kw["user_message"] == "Привет"
    assert call_kw["conversation_id"] == conv.conversation_id
    sender.send_message.assert_not_awaited()  # telegram path persists via agent_service, not direct send here


@pytest.mark.asyncio
async def test_execute_agent_reply_skips_human_handoff_statuses():
    db = CoordinatorFakeDB()
    redis = FakeRedis()
    for status in (ConversationStatus.NEEDS_HUMAN, ConversationStatus.HUMAN_ACTIVE):
        conv = _conversation(conversation_id=f"conv-{status.value}", status=status)
        db.conversations[conv.conversation_id] = conv
        redis.strings[f"{KEY_VER_PREFIX}{conv.conversation_id}"] = "1"

        agent_service = MagicMock()
        agent_service.process_message = AsyncMock()

        with _coordinator_patches(db=db, redis=redis):
            with patch(
                "app.services.agent_reply_coordinator.create_agent_service",
                return_value=agent_service,
            ):
                await execute_agent_reply(conv.conversation_id, expected_version=1)

        agent_service.process_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_agent_reply_skips_stale_debounce_version():
    db = CoordinatorFakeDB()
    redis = FakeRedis()
    conv = _conversation()
    db.conversations[conv.conversation_id] = conv
    _seed_agent(db)
    redis.strings[f"{KEY_VER_PREFIX}{conv.conversation_id}"] = "5"

    agent_service = MagicMock()
    agent_service.process_message = AsyncMock()

    with _coordinator_patches(db=db, redis=redis):
        with patch(
            "app.services.agent_reply_coordinator.create_agent_service",
            return_value=agent_service,
        ):
            await execute_agent_reply(conv.conversation_id, expected_version=3)

    agent_service.process_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_agent_reply_missing_agent():
    db = CoordinatorFakeDB()
    redis = FakeRedis()
    conv = _conversation()
    db.conversations[conv.conversation_id] = conv
    redis.strings[f"{KEY_VER_PREFIX}{conv.conversation_id}"] = "1"
    await redis.set(f"{KEY_LAST_INPUT_PREFIX}{conv.conversation_id}", "Hi")

    agent_service = MagicMock()
    agent_service.process_message = AsyncMock()

    with _coordinator_patches(db=db, redis=redis):
        with patch(
            "app.services.agent_reply_coordinator.create_agent_service",
            return_value=agent_service,
        ):
            await execute_agent_reply(conv.conversation_id, expected_version=1)

    agent_service.process_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_agent_reply_inactive_agent_no_config():
    db = CoordinatorFakeDB()
    redis = FakeRedis()
    conv = _conversation()
    db.conversations[conv.conversation_id] = conv
    db.agents["agent-1"] = {"name": "broken"}
    redis.strings[f"{KEY_VER_PREFIX}{conv.conversation_id}"] = "1"
    await redis.set(f"{KEY_LAST_INPUT_PREFIX}{conv.conversation_id}", "Hi")

    agent_service = MagicMock()
    agent_service.process_message = AsyncMock()

    with _coordinator_patches(db=db, redis=redis):
        with patch(
            "app.services.agent_reply_coordinator.create_agent_service",
            return_value=agent_service,
        ):
            await execute_agent_reply(conv.conversation_id, expected_version=1)

    agent_service.process_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_agent_reply_skips_closed_conversation():
    db = CoordinatorFakeDB()
    redis = FakeRedis()
    conv = _conversation(status=ConversationStatus.CLOSED)
    db.conversations[conv.conversation_id] = conv
    redis.strings[f"{KEY_VER_PREFIX}{conv.conversation_id}"] = "1"

    agent_service = MagicMock()
    agent_service.process_message = AsyncMock()

    with _coordinator_patches(db=db, redis=redis):
        with patch(
            "app.services.agent_reply_coordinator.create_agent_service",
            return_value=agent_service,
        ):
            await execute_agent_reply(conv.conversation_id, expected_version=1)

    agent_service.process_message.assert_not_awaited()


# ---------------------------------------------------------------------------
# execute_timer_trigger
# ---------------------------------------------------------------------------


def _timer_payload(
    agent_config: AgentConfig,
    *,
    message_template: str = "Reminder for {pet_name}",
    step_id: str | None = None,
    config_hash: str | None = None,
) -> dict[str, Any]:
    return {
        "delay_seconds": 60,
        "message_template": message_template,
        "action_type": "static",
        "step_id": step_id,
        "config_hash": config_hash or workflow_config_hash(agent_config.workflow),
    }


@pytest.mark.asyncio
async def test_execute_timer_trigger_static_sends_message():
    db = CoordinatorFakeDB()
    redis = FakeRedis()
    conv = _conversation()
    db.conversations[conv.conversation_id] = conv
    agent_config = _seed_agent(db)

    payload = _timer_payload(agent_config, message_template="Time is up!")
    await redis.set(
        f"agent_reply:timer_payload:{conv.conversation_id}",
        json.dumps(payload),
    )

    sender = AsyncMock()
    with _coordinator_patches(db=db, redis=redis):
        with (
            patch("app.services.channel_sender.get_channel_sender", return_value=sender),
            patch(
                "app.services.agent_reply_coordinator._load_conversation_history_from_db",
                new=AsyncMock(return_value=[{"role": "user", "content": "hi"}]),
            ),
        ):
            await execute_timer_trigger(conv.conversation_id)

    sender.send_message.assert_awaited_once()
    sent_text = sender.send_message.await_args.kwargs["message_text"]
    assert sent_text == "Time is up!"
    assert len(db.messages) == 1
    assert f"agent_reply:timer_payload:{conv.conversation_id}" not in redis.strings


@pytest.mark.asyncio
async def test_execute_timer_trigger_skips_blocked_statuses():
    db = CoordinatorFakeDB()
    redis = FakeRedis()
    agent_config = _seed_agent(db)
    payload = _timer_payload(agent_config, message_template="nope")

    sender = AsyncMock()
    for status in (
        ConversationStatus.CLOSED,
        ConversationStatus.NEEDS_HUMAN,
        ConversationStatus.HUMAN_ACTIVE,
    ):
        conv = _conversation(conversation_id=f"conv-t-{status.value}", status=status)
        db.conversations[conv.conversation_id] = conv
        await redis.set(
            f"agent_reply:timer_payload:{conv.conversation_id}",
            json.dumps(payload),
        )

        with _coordinator_patches(db=db, redis=redis):
            with patch("app.services.channel_sender.get_channel_sender", return_value=sender):
                await execute_timer_trigger(conv.conversation_id)

    sender.send_message.assert_not_awaited()
    assert len(db.messages) == 0


@pytest.mark.asyncio
async def test_execute_timer_trigger_discards_stale_workflow_hash():
    db = CoordinatorFakeDB()
    redis = FakeRedis()
    conv = _conversation()
    db.conversations[conv.conversation_id] = conv
    agent_config = _seed_agent(db)

    payload = _timer_payload(agent_config, message_template="stale", config_hash="deadbeef0000")
    await redis.set(
        f"agent_reply:timer_payload:{conv.conversation_id}",
        json.dumps(payload),
    )

    sender = AsyncMock()
    with _coordinator_patches(db=db, redis=redis):
        with patch("app.services.channel_sender.get_channel_sender", return_value=sender):
            await execute_timer_trigger(conv.conversation_id)

    sender.send_message.assert_not_awaited()
    assert f"agent_reply:timer_payload:{conv.conversation_id}" not in redis.strings


@pytest.mark.asyncio
@pytest.mark.xfail(
    reason=(
        "Bug: execute_timer_trigger initializes collected={} and never calls "
        "_load_collected_from_checkpoint (agent_reply_coordinator.py ~608-673); "
        "placeholders in static timer messages are not substituted."
    ),
    strict=False,
)
async def test_execute_timer_trigger_substitutes_checkpoint_placeholders():
    """Timer static messages should substitute {collected} vars like auto-steps do."""
    db = CoordinatorFakeDB()
    redis = FakeRedis()
    conv = _conversation()
    db.conversations[conv.conversation_id] = conv
    agent_config = _seed_agent(db)

    payload = _timer_payload(agent_config, message_template="Привет, {pet_name}!")
    await redis.set(
        f"agent_reply:timer_payload:{conv.conversation_id}",
        json.dumps(payload),
    )

    sender = AsyncMock()
    with _coordinator_patches(db=db, redis=redis):
        with (
            patch("app.services.channel_sender.get_channel_sender", return_value=sender),
            patch(
                "app.services.agent_reply_coordinator._load_conversation_history_from_db",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.services.agent_reply_coordinator._load_collected_from_checkpoint",
                new=AsyncMock(return_value={"pet_name": "Барсик"}),
            ),
        ):
            await execute_timer_trigger(conv.conversation_id)

    sent_text = sender.send_message.await_args.kwargs["message_text"]
    assert sent_text == "Привет, Барсик!"


@pytest.mark.asyncio
async def test_execute_timer_trigger_discards_when_step_changed():
    db = CoordinatorFakeDB()
    redis = FakeRedis()
    conv = _conversation()
    db.conversations[conv.conversation_id] = conv
    agent_config = _seed_agent(db)

    payload = _timer_payload(agent_config, message_template="step msg", step_id="step_a")
    await redis.set(
        f"agent_reply:timer_payload:{conv.conversation_id}",
        json.dumps(payload),
    )

    sender = AsyncMock()
    with _coordinator_patches(db=db, redis=redis):
        with (
            patch("app.services.channel_sender.get_channel_sender", return_value=sender),
            patch(
                "app.services.agent_reply_coordinator._load_current_step_from_graph",
                new=AsyncMock(return_value="step_b"),
            ),
            patch(
                "app.services.agent_reply_coordinator._load_conversation_history_from_db",
                new=AsyncMock(return_value=[]),
            ),
        ):
            await execute_timer_trigger(conv.conversation_id)

    sender.send_message.assert_not_awaited()
    assert f"agent_reply:timer_payload:{conv.conversation_id}" not in redis.strings


# ---------------------------------------------------------------------------
# execute_auto_step_trigger
# ---------------------------------------------------------------------------


def _auto_step_payload(
    agent_config: AgentConfig,
    conversation_id: str,
    *,
    auto_step_id: str = "auto-1",
    message_template: str = "Follow-up for {pet_name}",
    condition: str | None = None,
) -> dict[str, Any]:
    return {
        "id": auto_step_id,
        "conversation_id": conversation_id,
        "action_type": "static",
        "message_template": message_template,
        "delay_seconds": 30,
        "config_hash": workflow_config_hash(agent_config.workflow),
        "condition": condition,
    }


@pytest.mark.asyncio
async def test_execute_auto_step_trigger_static_sends_message():
    db = CoordinatorFakeDB()
    redis = FakeRedis()
    conv = _conversation()
    db.conversations[conv.conversation_id] = conv
    agent_config = _seed_agent(db)
    member = f"{conv.conversation_id}:auto-1"
    payload = _auto_step_payload(agent_config, conv.conversation_id, message_template="Ping!")
    await redis.set(f"{KEY_AUTO_PAY}{member}", json.dumps(payload))

    sender = AsyncMock()
    with _coordinator_patches(db=db, redis=redis):
        with (
            patch("app.services.channel_sender.get_channel_sender", return_value=sender),
            patch(
                "app.services.agent_reply_coordinator._load_collected_from_checkpoint",
                new=AsyncMock(return_value={}),
            ),
            patch(
                "app.services.agent_reply_coordinator._load_conversation_history_from_db",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.services.agent_reply_coordinator._schedule_chained_auto_steps",
                new=AsyncMock(),
            ),
        ):
            await execute_auto_step_trigger(member)

    sender.send_message.assert_awaited_once()
    assert sender.send_message.await_args.kwargs["message_text"] == "Ping!"
    assert f"{KEY_AUTO_PAY}{member}" not in redis.strings


@pytest.mark.asyncio
async def test_execute_auto_step_trigger_substitutes_checkpoint_placeholders():
    db = CoordinatorFakeDB()
    redis = FakeRedis()
    conv = _conversation(external_user_name="Иван Петров")
    db.conversations[conv.conversation_id] = conv
    agent_config = _seed_agent(db)
    member = f"{conv.conversation_id}:auto-1"
    payload = _auto_step_payload(
        agent_config,
        conv.conversation_id,
        message_template="Здравствуйте, {user_name}! Как {pet_name}?",
    )
    await redis.set(f"{KEY_AUTO_PAY}{member}", json.dumps(payload))

    sender = AsyncMock()
    with _coordinator_patches(db=db, redis=redis):
        with (
            patch("app.services.channel_sender.get_channel_sender", return_value=sender),
            patch(
                "app.services.agent_reply_coordinator._load_collected_from_checkpoint",
                new=AsyncMock(return_value={"pet_name": "Мурзик"}),
            ),
            patch(
                "app.services.agent_reply_coordinator._load_conversation_history_from_db",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.services.agent_reply_coordinator._schedule_chained_auto_steps",
                new=AsyncMock(),
            ),
        ):
            await execute_auto_step_trigger(member)

    sent_text = sender.send_message.await_args.kwargs["message_text"]
    assert sent_text == "Здравствуйте, Иван! Как Мурзик?"


@pytest.mark.asyncio
async def test_execute_auto_step_trigger_skips_when_condition_false():
    db = CoordinatorFakeDB()
    redis = FakeRedis()
    conv = _conversation()
    db.conversations[conv.conversation_id] = conv
    agent_config = _seed_agent(db)
    member = f"{conv.conversation_id}:auto-1"
    payload = _auto_step_payload(
        agent_config,
        conv.conversation_id,
        message_template="Should not send",
        condition="user already booked",
    )
    await redis.set(f"{KEY_AUTO_PAY}{member}", json.dumps(payload))

    sender = AsyncMock()
    with _coordinator_patches(db=db, redis=redis):
        with (
            patch("app.services.channel_sender.get_channel_sender", return_value=sender),
            patch(
                "app.services.agent_reply_coordinator._evaluate_auto_step_condition",
                new=AsyncMock(return_value=False),
            ),
            patch(
                "app.services.agent_reply_coordinator._load_collected_from_checkpoint",
                new=AsyncMock(return_value={}),
            ),
            patch(
                "app.services.agent_reply_coordinator._load_conversation_history_from_db",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.services.agent_reply_coordinator._schedule_chained_auto_steps",
                new=AsyncMock(),
            ),
        ):
            await execute_auto_step_trigger(member)

    sender.send_message.assert_not_awaited()
    assert f"{KEY_AUTO_PAY}{member}" not in redis.strings


# ---------------------------------------------------------------------------
# Schedulers (Redis writes)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notify_user_message_saved_writes_redis_keys():
    db = CoordinatorFakeDB()
    redis = FakeRedis()
    conv_id = "conv-schedule"
    fixed_now = 1_700_000_000.0

    with _coordinator_patches(db=db, redis=redis, settings=DebounceSettings()):
        with patch("app.services.agent_reply_coordinator.time.time", return_value=fixed_now):
            result = await notify_user_message_saved(
                conv_id,
                agent_user_message="agent text",
                last_user_plain_content="plain text",
            )

    assert result == "scheduled"
    assert redis.strings[f"{KEY_VER_PREFIX}{conv_id}"] == "1"
    assert redis.strings[f"{KEY_LAST_INPUT_PREFIX}{conv_id}"] == "agent text"
    assert redis.strings[f"{KEY_LAST_PLAIN_PREFIX}{conv_id}"] == "plain text"
    expected_fire = fixed_now * 1000 + 5 * 1000
    assert redis.zsets[KEY_DUE][conv_id] == expected_fire


@pytest.mark.asyncio
async def test_notify_user_message_saved_returns_disabled_when_debounce_zero():
    redis = FakeRedis()
    with _coordinator_patches(db=CoordinatorFakeDB(), redis=redis, settings=DummySettings()):
        result = await notify_user_message_saved(
            "conv-x",
            agent_user_message="a",
            last_user_plain_content="b",
        )
    assert result == "disabled"


@pytest.mark.asyncio
async def test_schedule_timer_trigger_writes_redis():
    redis = FakeRedis()
    conv_id = "conv-timer"
    fire_at = 1_700_000_100_000

    with _coordinator_patches(db=CoordinatorFakeDB(), redis=redis):
        await schedule_timer_trigger(
            conv_id,
            {
                "fire_at_ms": fire_at,
                "delay_seconds": 120,
                "message_template": "wake up",
                "step_id": "s1",
            },
        )

    assert redis.zsets[KEY_TIMER_DUE][conv_id] == float(fire_at)
    raw = redis.strings[f"agent_reply:timer_payload:{conv_id}"]
    assert raw is not None
    data = json.loads(raw)
    assert data["message_template"] == "wake up"
    assert data["step_id"] == "s1"


@pytest.mark.asyncio
async def test_schedule_auto_step_writes_redis():
    redis = FakeRedis()
    conv_id = "conv-auto"
    auto_step_id = "auto-followup"
    member = f"{conv_id}:{auto_step_id}"
    fire_at = 1_700_000_200_000

    with _coordinator_patches(db=CoordinatorFakeDB(), redis=redis):
        await schedule_auto_step(
            conv_id,
            {
                "id": auto_step_id,
                "delay_seconds": 45,
                "action_type": "static",
                "message_template": "auto msg",
            },
            config_hash="abc123",
            fire_at_ms=fire_at,
        )

    assert redis.zsets[KEY_AUTO_DUE][member] == float(fire_at)
    raw = redis.strings[f"{KEY_AUTO_PAY}{member}"]
    assert raw is not None
    data = json.loads(raw)
    assert data["id"] == auto_step_id
    assert data["config_hash"] == "abc123"
    assert member in redis.sets[f"{KEY_AUTO_IDX}{conv_id}"]
