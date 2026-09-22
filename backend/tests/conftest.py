"""Shared fakes for messenger adapter tests."""

from __future__ import annotations

from typing import Any, Optional
from unittest.mock import AsyncMock

import pytest

from app.models.channel_binding import ChannelBinding, ChannelType
from app.models.conversation import Conversation, ConversationStatus
from app.models.message import Message, MessageChannel
from app.utils.datetime_utils import utc_now
from app.utils.enum_helpers import get_enum_value


class FakeDB:
    """In-memory stand-in for PostgreSQLClient."""

    def __init__(self) -> None:
        self.conversations: dict[str, Conversation] = {}
        self.messages: dict[tuple[str, str], Message] = {}
        self.agents: dict[str, dict[str, Any]] = {}
        self.instagram_profiles: dict[str, Any] = {}

    async def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        return self.conversations.get(conversation_id)

    async def create_conversation(self, conversation: Conversation) -> Conversation:
        self.conversations[conversation.conversation_id] = conversation
        return conversation

    async def update_conversation(self, conversation_id: str, **kwargs: Any) -> Optional[Conversation]:
        conv = self.conversations.get(conversation_id)
        if not conv:
            return None
        data = conv.model_dump()
        for k, v in kwargs.items():
            if k == "status" and hasattr(v, "value"):
                data[k] = v.value
            else:
                data[k] = v
        updated = Conversation(**data)
        self.conversations[conversation_id] = updated
        return updated

    async def delete_channel_binding(self, binding_id: str) -> None:
        return None

    async def get_conversation_by_external_user(
        self,
        agent_id: str,
        channel: str,
        external_user_id: str,
        *,
        include_closed: bool = False,
    ) -> Optional[Conversation]:
        matches = []
        for conv in self.conversations.values():
            if conv.agent_id != agent_id:
                continue
            if get_enum_value(conv.channel) != channel:
                continue
            if conv.external_user_id != external_user_id:
                continue
            if not include_closed and get_enum_value(conv.status) == ConversationStatus.CLOSED.value:
                continue
            matches.append(conv)
        matches.sort(key=lambda c: c.updated_at, reverse=True)
        return matches[0] if matches else None

    async def list_open_conversations_by_external_user(
        self, agent_id: str, channel: str, external_user_id: str
    ) -> list[Conversation]:
        out = []
        for conv in self.conversations.values():
            if (
                conv.agent_id == agent_id
                and get_enum_value(conv.channel) == channel
                and conv.external_user_id == external_user_id
                and get_enum_value(conv.status) != ConversationStatus.CLOSED.value
            ):
                out.append(conv)
        return out

    async def list_conversations(self, agent_id: Optional[str] = None, **kwargs: Any) -> list[Conversation]:
        rows = list(self.conversations.values())
        if agent_id:
            rows = [c for c in rows if c.agent_id == agent_id]
        return rows

    async def try_create_message(self, message: Message) -> bool:
        key = (message.conversation_id, message.message_id)
        if key in self.messages:
            return False
        self.messages[key] = message
        return True

    async def list_messages(
        self,
        conversation_id: str,
        limit: int = 100,
        reverse: bool = True,
    ) -> list[Message]:
        items = [m for (cid, _), m in self.messages.items() if cid == conversation_id]
        items.sort(key=lambda m: m.timestamp or utc_now())
        if reverse:
            items.reverse()
        return items[:limit]

    async def provider_message_id_exists(self, conversation_id: str, platform_id: str) -> bool:
        if not platform_id or not str(platform_id).strip():
            return False
        pid = str(platform_id).strip()
        for (cid, _), msg in self.messages.items():
            if cid != conversation_id:
                continue
            if msg.external_message_id == pid:
                return True
            meta = msg.metadata or {}
            stored = meta.get("provider_message_ids") or []
            if isinstance(stored, list) and pid in [str(x) for x in stored]:
                return True
        return False

    async def stamp_provider_message_ids(
        self, conversation_id: str, message_id: str, ids: list[str]
    ) -> None:
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in ids or []:
            if raw is None:
                continue
            value = str(raw).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            cleaned.append(value)
        if not cleaned:
            return
        key = (conversation_id, message_id)
        msg = self.messages.get(key)
        if not msg:
            return
        if not (msg.external_message_id and str(msg.external_message_id).strip()):
            msg.external_message_id = cleaned[0]
        meta = dict(msg.metadata or {})
        existing = meta.get("provider_message_ids") or []
        if not isinstance(existing, list):
            existing = []
        merged: list[str] = []
        merged_seen: set[str] = set()
        for raw in [*existing, *cleaned]:
            if raw is None:
                continue
            value = str(raw).strip()
            if not value or value in merged_seen:
                continue
            merged_seen.add(value)
            merged.append(value)
        meta["provider_message_ids"] = merged
        msg.metadata = meta

    async def get_agent(self, agent_id: str) -> Optional[dict[str, Any]]:
        return self.agents.get(agent_id)

    async def create_or_update_instagram_profile(self, profile: Any) -> Any:
        self.instagram_profiles[profile.external_user_id] = profile
        return profile

    async def get_instagram_profile(self, external_user_id: str) -> Optional[Any]:
        return self.instagram_profiles.get(external_user_id)

    async def list_channel_bindings_by_channel(
        self, channel_type: str, active_only: bool = True
    ) -> list[Any]:
        return []


class FakeBindingService:
    def __init__(self, binding: ChannelBinding, token: str = "test-token") -> None:
        self.binding = binding
        self.token = token
        self.updated: list[dict[str, Any]] = []

    async def get_binding(self, binding_id: str) -> Optional[ChannelBinding]:
        if binding_id == self.binding.binding_id:
            return self.binding
        return None

    async def get_access_token(self, binding_id: str) -> str:
        if binding_id != self.binding.binding_id:
            raise ValueError("unknown binding")
        return self.token

    async def get_binding_by_account_id(self, channel_type: str, account_id: str) -> Optional[ChannelBinding]:
        if (
            get_enum_value(self.binding.channel_type) == channel_type
            and self.binding.channel_account_id == account_id
        ):
            return self.binding
        return None

    async def get_bindings_by_agent(self, agent_id: str, channel_type=None, active_only=True):
        if self.binding.agent_id == agent_id:
            return [self.binding]
        return []

    async def list_bindings_by_channel(self, channel_type: str, active_only: bool = True):
        if get_enum_value(self.binding.channel_type) != channel_type:
            return []
        if active_only and not self.binding.is_active:
            return []
        return [self.binding]

    async def update_binding(self, binding_id: str, **kwargs: Any) -> ChannelBinding:
        self.updated.append(kwargs)
        if "metadata" in kwargs:
            self.binding.metadata = kwargs["metadata"]
        if "is_verified" in kwargs:
            self.binding.is_verified = kwargs["is_verified"]
        if "channel_account_id" in kwargs:
            self.binding.channel_account_id = kwargs["channel_account_id"]
        if "channel_username" in kwargs:
            self.binding.channel_username = kwargs["channel_username"]
        return self.binding


def make_binding(
    *,
    channel: ChannelType = ChannelType.TELEGRAM,
    binding_id: str = "11111111-1111-1111-1111-111111111111",
    agent_id: str = "agent-1",
    account_id: str = "bot-1",
    metadata: Optional[dict[str, Any]] = None,
) -> ChannelBinding:
    now = utc_now()
    return ChannelBinding(
        binding_id=binding_id,
        agent_id=agent_id,
        channel_type=channel,
        channel_account_id=account_id,
        is_active=True,
        is_verified=True,
        metadata=metadata or {},
        created_at=now,
        updated_at=now,
    )


class DummySettings:
    app_url = "https://example.test"
    frontend_url = None
    environment = "development"
    agent_reply_debounce_seconds = 0
    jwt_secret_key = "jwt-secret-for-tests-min-32-chars"
    secret_encryption_key = None
    instagram_app_id = None
    instagram_app_secret = "ig-app-secret"
    instagram_webhook_verify_token = "ig-verify"
    tiktok_app_id = None
    tiktok_app_secret = None
    tiktok_messaging_enabled = False
    debug = True


@pytest.fixture
def dummy_settings() -> DummySettings:
    return DummySettings()
