"""PostgreSQL client - Railway-compatible storage layer."""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, Optional

import asyncpg

from app.config import Settings, get_settings
from app.models.channel_binding import ChannelBinding, ChannelType
from app.models.conversation import Conversation, ConversationStatus, MarketingStatus
from app.models.instagram_user_profile import InstagramUserProfile
from app.models.message import Message, MessageRole
from app.utils.datetime_utils import parse_utc_datetime, to_utc_iso_string, utc_now
from app.utils.enum_helpers import get_enum_value

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


def _unique_nonempty_ids(ids: Optional[list[Any]]) -> list[str]:
    """Preserve order; drop empties and duplicates."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in ids or []:
        if raw is None:
            continue
        value = str(raw).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


async def get_pool() -> asyncpg.Pool:
    """Get or create connection pool."""
    global _pool
    if _pool is None:
        settings = get_settings()
        url = settings.get_database_url()
        if not url:
            raise RuntimeError("DATABASE_URL or DATABASE_PUBLIC_URL must be set for PostgreSQL backend")
        _pool = await asyncpg.create_pool(url, min_size=1, max_size=10, command_timeout=60)
    return _pool


async def close_pool() -> None:
    """Close connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def _parse_json(val: Any) -> Any:
    """Parse JSON from DB."""
    if val is None:
        return {}
    if isinstance(val, str):
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            return {}
    return val if isinstance(val, (dict, list)) else {}


def _row_to_conv(row: asyncpg.Record) -> dict:
    """Convert DB row to conversation dict."""
    d = dict(row)
    for k in ("created_at", "updated_at", "closed_at", "agent_context_reset_at"):
        if d.get(k) and isinstance(d[k], datetime):
            d[k] = to_utc_iso_string(d[k])
    if "marketing_status" not in d or d["marketing_status"] is None:
        d["marketing_status"] = MarketingStatus.NEW.value
    # Serialize UUID to string
    if "crm_stage_id" in d and d["crm_stage_id"] is not None:
        d["crm_stage_id"] = str(d["crm_stage_id"])
    if "metadata" in d:
        d["metadata"] = _parse_json(d["metadata"])
    else:
        d["metadata"] = {}
    return d


def _row_to_msg(row: asyncpg.Record) -> dict:
    """Convert DB row to message dict."""
    d = dict(row)
    # Keep datetime as-is for Message model; parse if string from JSON
    if "metadata" in d and isinstance(d["metadata"], str):
        d["metadata"] = _parse_json(d["metadata"])
    return d


def _row_to_binding(row: asyncpg.Record) -> dict:
    """Convert DB row to channel binding dict."""
    d = dict(row)
    for k in ("created_at", "updated_at"):
        if d.get(k) and isinstance(d[k], datetime):
            d[k] = to_utc_iso_string(d[k])
    if "metadata" in d and isinstance(d["metadata"], str):
        d["metadata"] = _parse_json(d["metadata"])
    if d.get("channel_username") == "":
        d["channel_username"] = None
    return d


def _row_to_notification_config(row: asyncpg.Record) -> dict:
    """Convert DB row to notification config dict."""
    d = dict(row)
    for k in ("created_at", "updated_at"):
        if d.get(k) and isinstance(d[k], datetime):
            d[k] = to_utc_iso_string(d[k])
    return d


PERIOD_STATS_KEYS = (
    "total_conversations",
    "ai_active",
    "needs_human",
    "human_active",
    "closed",
    "marketing_new",
    "marketing_booked",
    "marketing_no_response",
    "marketing_rejected",
)


def _empty_period_stats() -> dict[str, int]:
    return {key: 0 for key in PERIOD_STATS_KEYS}


def _period_stats_from_row(row: asyncpg.Record) -> dict[str, int]:
    return {key: int(row[key]) if row and row[key] is not None else 0 for key in PERIOD_STATS_KEYS}


def _conversation_created_in_range(
    conversation: Conversation,
    start_date: datetime,
    end_date: datetime,
    *,
    end_exclusive: bool,
) -> bool:
    """Match admin stats date filtering (inclusive start; end inclusive or exclusive)."""
    if not conversation.created_at:
        return False
    created_dt = conversation.created_at
    if isinstance(created_dt, str):
        try:
            created_dt = parse_utc_datetime(created_dt)
        except (ValueError, AttributeError):
            return False
    if created_dt.tzinfo is None:
        from datetime import timezone

        created_dt = created_dt.replace(tzinfo=timezone.utc)
    start = start_date
    end = end_date
    if start.tzinfo is None:
        from datetime import timezone

        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        from datetime import timezone

        end = end.replace(tzinfo=timezone.utc)
    if end_exclusive:
        return start <= created_dt < end
    return start <= created_dt <= end


def _period_stats_from_conversations(
    conversations: list[Conversation],
    start_date: datetime,
    end_date: datetime,
    *,
    end_exclusive: bool,
) -> dict[str, int]:
    """Python fallback for in-memory test doubles without SQL aggregation."""
    stats = _empty_period_stats()
    for conversation in conversations:
        if not _conversation_created_in_range(
            conversation, start_date, end_date, end_exclusive=end_exclusive
        ):
            continue
        stats["total_conversations"] += 1
        status = get_enum_value(conversation.status)
        if status == ConversationStatus.AI_ACTIVE.value:
            stats["ai_active"] += 1
        elif status == ConversationStatus.NEEDS_HUMAN.value:
            stats["needs_human"] += 1
        elif status == ConversationStatus.HUMAN_ACTIVE.value:
            stats["human_active"] += 1
        elif status == ConversationStatus.CLOSED.value:
            stats["closed"] += 1
        marketing_status = get_enum_value(conversation.marketing_status)
        if marketing_status == MarketingStatus.NEW.value:
            stats["marketing_new"] += 1
        elif marketing_status == MarketingStatus.BOOKED.value:
            stats["marketing_booked"] += 1
        elif marketing_status == MarketingStatus.NO_RESPONSE.value:
            stats["marketing_no_response"] += 1
        elif marketing_status == MarketingStatus.REJECTED.value:
            stats["marketing_rejected"] += 1
    return stats


async def fetch_conversation_period_stats(
    db: Any,
    start_date: datetime,
    end_date: datetime,
    *,
    end_exclusive: bool = False,
) -> dict[str, int]:
    """Aggregate conversation stats for a time window (SQL or in-memory fallback)."""
    method = getattr(db, "get_conversation_period_stats", None)
    if method is not None:
        return await method(start_date, end_date, end_exclusive=end_exclusive)
    conversations = await db.list_conversations(limit=1_000_000)
    return _period_stats_from_conversations(
        conversations,
        start_date,
        end_date,
        end_exclusive=end_exclusive,
    )


def diff_period_stats(current: dict[str, int], previous: dict[str, int]) -> dict[str, int]:
    """Subtract previous-period counts from current-period counts."""
    return {key: current[key] - previous[key] for key in PERIOD_STATS_KEYS}


class PostgreSQLClient:
    """PostgreSQL storage client."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.message_ttl_seconds = settings.message_ttl_hours * 3600

    def _calculate_ttl(self, base_time: datetime) -> int:
        return int((base_time + timedelta(seconds=self.message_ttl_seconds)).timestamp())

    def _calculate_profile_ttl(self, base_time: datetime) -> int:
        return int((base_time + timedelta(days=5)).timestamp())

    # Conversation operations
    async def create_conversation(self, conversation: Conversation) -> Conversation:
        ttl = self._calculate_ttl(conversation.created_at)
        ms = get_enum_value(conversation.marketing_status) or MarketingStatus.NEW.value
        ch = get_enum_value(conversation.channel) or "web_chat"
        st = get_enum_value(conversation.status) or ConversationStatus.AI_ACTIVE.value

        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO conversations (
                        conversation_id, agent_id, channel, external_conversation_id, external_user_id,
                        status, created_at, updated_at, closed_at, handoff_reason, request_type, ttl,
                        external_user_name, external_user_username, external_user_profile_pic,
                        marketing_status, rejection_reason, crm_stage_id, agent_context_reset_at,
                        metadata
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17,
                        COALESCE($18::uuid, (SELECT id FROM crm_stages WHERE is_default = TRUE ORDER BY position ASC LIMIT 1)),
                        $19, $20::jsonb
                    )
                    ON CONFLICT (conversation_id) DO UPDATE SET
                        updated_at = EXCLUDED.updated_at
                    """,
                    conversation.conversation_id,
                    conversation.agent_id,
                    ch,
                    conversation.external_conversation_id,
                    conversation.external_user_id,
                    st,
                    conversation.created_at,
                    conversation.updated_at,
                    conversation.closed_at,
                    conversation.handoff_reason,
                    conversation.request_type,
                    ttl,
                    conversation.external_user_name,
                    conversation.external_user_username,
                    conversation.external_user_profile_pic,
                    ms,
                    conversation.rejection_reason,
                    conversation.crm_stage_id,
                    conversation.agent_context_reset_at,
                    json.dumps(conversation.metadata or {}),
                )
        return conversation

    async def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM conversations WHERE conversation_id = $1",
                conversation_id,
            )
        if not row:
            return None
        return Conversation(**_row_to_conv(row))

    async def update_conversation(
        self,
        conversation_id: str,
        status: Optional[ConversationStatus] = None,
        handoff_reason: Optional[str] = None,
        request_type: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional[Conversation]:
        old = await self.get_conversation(conversation_id)
        old_status = get_enum_value(old.status) if old else None

        updates = []
        params = []
        i = 1
        if status:
            updates.append(f"status = ${i}")
            params.append(status.value)
            i += 1
        if handoff_reason is not None:
            updates.append(f"handoff_reason = ${i}")
            params.append(handoff_reason)
            i += 1
        if request_type is not None:
            updates.append(f"request_type = ${i}")
            params.append(request_type)
            i += 1
        for k, v in kwargs.items():
            if k == "metadata" and isinstance(v, dict):
                v = json.dumps(v)
            updates.append(f'"{k}" = ${i}')
            params.append(v)
            i += 1
        if not updates:
            return await self.get_conversation(conversation_id)

        updates.append(f"updated_at = ${i}")
        params.append(utc_now())
        i += 1
        params.append(conversation_id)

        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"UPDATE conversations SET {', '.join(updates)} WHERE conversation_id = ${i}",
                *params,
            )

        updated = await self.get_conversation(conversation_id)
        if updated:
            try:
                from app.api.admin_websocket import get_admin_broadcast_manager
                from app.models.conversation import ConversationStatus

                broadcast_manager = get_admin_broadcast_manager()
                if (
                    status
                    and status == ConversationStatus.NEEDS_HUMAN
                    and (old_status is None or old_status != ConversationStatus.NEEDS_HUMAN.value)
                ):
                    await broadcast_manager.broadcast_new_escalation(
                        updated, handoff_reason
                    )
                    try:
                        from app.services.notification_service import NotificationService
                        from app.storage.postgres_secrets import get_postgres_secrets_manager
                        from app.config import get_settings

                        secrets_manager = get_postgres_secrets_manager()
                        settings = get_settings()
                        notification_service = NotificationService(
                            db=self,
                            secrets_manager=secrets_manager,
                            telegram_service=None,
                        )
                        agent_data = await self.get_agent(updated.agent_id)
                        agent_display_name = "Unknown Agent"
                        if agent_data and "config" in agent_data:
                            from app.models.agent_config import AgentConfig
                            agent_config = AgentConfig.from_dict(agent_data["config"])
                            agent_display_name = agent_config.profile.agent_display_name
                        asyncio.create_task(
                            notification_service.send_escalation_notification(
                                conversation=updated,
                                escalation_reason=handoff_reason or "Escalation required",
                                agent_display_name=agent_display_name,
                                admin_panel_base_url=settings.app_url or None,
                            )
                        )
                    except Exception as e:
                        logger.warning(f"Failed to send escalation notifications: {e}", exc_info=True)
                else:
                    await broadcast_manager.broadcast_conversation_update(updated)
            except Exception as e:
                logger.warning(f"Failed to broadcast: {e}", exc_info=True)
        return updated

    async def list_conversations(
        self,
        agent_id: Optional[str] = None,
        status: Optional[ConversationStatus] = None,
        marketing_status: Optional[str] = None,
        crm_stage_id: Optional[str] = None,
        limit: int = 100,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        created_from: Optional[datetime] = None,
        created_to: Optional[datetime] = None,
    ) -> list[Conversation]:
        where = []
        params = []
        i = 1
        if agent_id:
            where.append(f"agent_id = ${i}")
            params.append(agent_id)
            i += 1
        if status:
            where.append(f"status = ${i}")
            params.append(status.value)
            i += 1
        if marketing_status:
            where.append(f"marketing_status = ${i}")
            params.append(marketing_status)
            i += 1
        if crm_stage_id:
            where.append(f"crm_stage_id = ${i}")
            params.append(crm_stage_id)
            i += 1
        if created_from is not None:
            where.append(f"created_at >= ${i}")
            params.append(created_from)
            i += 1
        if created_to is not None:
            where.append(f"created_at <= ${i}")
            params.append(created_to)
            i += 1
        order_col = "updated_at" if sort_by == "updated_at" else "created_at"
        order_dir = "ASC" if sort_order == "asc" else "DESC"
        params.append(limit)
        clause = " AND ".join(where) if where else "TRUE"
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT * FROM conversations WHERE {clause} ORDER BY {order_col} {order_dir} LIMIT ${i}",
                *params,
            )
        return [Conversation(**_row_to_conv(r)) for r in rows]

    async def get_conversation_by_external_user(
        self,
        agent_id: str,
        channel: str,
        external_user_id: str,
        *,
        include_closed: bool = False,
    ) -> Optional[Conversation]:
        """Latest conversation for (agent, channel, external user). Prefers non-CLOSED."""
        pool = await get_pool()
        status_clause = "" if include_closed else "AND status <> 'CLOSED'"
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT * FROM conversations
                WHERE agent_id = $1
                  AND channel = $2
                  AND external_user_id = $3
                  {status_clause}
                ORDER BY updated_at DESC NULLS LAST
                LIMIT 1
                """,
                agent_id,
                channel,
                external_user_id,
            )
        if not row:
            return None
        return Conversation(**_row_to_conv(row))

    async def list_open_conversations_by_external_user(
        self,
        agent_id: str,
        channel: str,
        external_user_id: str,
    ) -> list[Conversation]:
        """All non-CLOSED conversations for (agent, channel, external user)."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM conversations
                WHERE agent_id = $1
                  AND channel = $2
                  AND external_user_id = $3
                  AND status <> 'CLOSED'
                ORDER BY updated_at DESC NULLS LAST
                """,
                agent_id,
                channel,
                external_user_id,
            )
        return [Conversation(**_row_to_conv(r)) for r in rows]

    async def count_distinct_end_users(self) -> int:
        """Count unique end users (agent_id + channel + external_user_id) with non-empty external id.

        Uses the same FROM/WHERE as ``list_distinct_end_users`` (including join to ``agents``)
        so the total matches paginated list rows.
        """
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT COUNT(*)::bigint AS n FROM (
                    SELECT 1
                    FROM conversations c
                    INNER JOIN agents a ON a.agent_id = c.agent_id
                    WHERE c.external_user_id IS NOT NULL
                      AND btrim(c.external_user_id::text) <> ''
                    GROUP BY c.agent_id, c.channel, c.external_user_id
                ) t
                """
            )
        return int(row["n"]) if row and row["n"] is not None else 0

    async def list_distinct_end_users(
        self,
        *,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        """Paginated distinct end users with aggregates (newest activity first)."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    c.agent_id,
                    MAX(a.config #>> '{profile,agent_display_name}') AS agent_display_name,
                    c.channel,
                    c.external_user_id,
                    MAX(NULLIF(btrim(c.external_user_name::text), '')) AS display_name,
                    MAX(NULLIF(btrim(c.external_user_username::text), '')) AS username,
                    MAX(c.updated_at) AS last_seen_at,
                    COUNT(*)::bigint AS conversation_count
                FROM conversations c
                INNER JOIN agents a ON a.agent_id = c.agent_id
                WHERE c.external_user_id IS NOT NULL
                  AND btrim(c.external_user_id::text) <> ''
                GROUP BY c.agent_id, c.channel, c.external_user_id
                ORDER BY MAX(c.updated_at) DESC NULLS LAST
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )
        out: list[dict[str, Any]] = []
        for r in rows:
            ls = r["last_seen_at"]
            out.append(
                {
                    "agent_id": r["agent_id"],
                    "agent_display_name": r["agent_display_name"] or None,
                    "channel": r["channel"],
                    "external_user_id": r["external_user_id"],
                    "display_name": r["display_name"],
                    "username": r["username"],
                    "last_seen_at": to_utc_iso_string(ls) if ls else None,
                    "conversation_count": int(r["conversation_count"]),
                }
            )
        return out

    async def get_conversation_period_stats(
        self,
        start_date: datetime,
        end_date: datetime,
        *,
        end_exclusive: bool = False,
    ) -> dict[str, int]:
        """Aggregate conversation counts for admin stats over a created_at window."""
        end_op = "<" if end_exclusive else "<="
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT
                    COUNT(*)::bigint AS total_conversations,
                    COUNT(*) FILTER (WHERE status = 'AI_ACTIVE')::bigint AS ai_active,
                    COUNT(*) FILTER (WHERE status = 'NEEDS_HUMAN')::bigint AS needs_human,
                    COUNT(*) FILTER (WHERE status = 'HUMAN_ACTIVE')::bigint AS human_active,
                    COUNT(*) FILTER (WHERE status = 'CLOSED')::bigint AS closed,
                    COUNT(*) FILTER (
                        WHERE COALESCE(marketing_status, 'NEW') = 'NEW'
                    )::bigint AS marketing_new,
                    COUNT(*) FILTER (WHERE marketing_status = 'BOOKED')::bigint AS marketing_booked,
                    COUNT(*) FILTER (WHERE marketing_status = 'NO_RESPONSE')::bigint AS marketing_no_response,
                    COUNT(*) FILTER (WHERE marketing_status = 'REJECTED')::bigint AS marketing_rejected
                FROM conversations
                WHERE created_at IS NOT NULL
                  AND created_at >= $1
                  AND created_at {end_op} $2
                """,
                start_date,
                end_date,
            )
        return _period_stats_from_row(row) if row else _empty_period_stats()

    # Message operations
    async def create_message(self, message: Message) -> Message:
        ttl = self._calculate_ttl(message.timestamp)
        ch = get_enum_value(message.channel) or "web_chat"
        role = get_enum_value(message.role)
        meta = json.dumps(message.metadata) if message.metadata else "{}"

        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO messages (
                    conversation_id, message_id, agent_id, role, content, channel,
                    external_message_id, external_user_id, timestamp, metadata, ttl
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                message.conversation_id,
                message.message_id,
                message.agent_id,
                role,
                message.content,
                ch,
                message.external_message_id,
                message.external_user_id,
                message.timestamp,
                meta,
                ttl,
            )
        return message

    async def try_create_message(self, message: Message) -> bool:
        """Insert message; return False if (conversation_id, message_id) already exists (idempotent)."""
        ttl = self._calculate_ttl(message.timestamp)
        ch = get_enum_value(message.channel) or "web_chat"
        role = get_enum_value(message.role)
        meta = json.dumps(message.metadata) if message.metadata else "{}"

        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO messages (
                    conversation_id, message_id, agent_id, role, content, channel,
                    external_message_id, external_user_id, timestamp, metadata, ttl
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT (conversation_id, message_id) DO NOTHING
                RETURNING message_id
                """,
                message.conversation_id,
                message.message_id,
                message.agent_id,
                role,
                message.content,
                ch,
                message.external_message_id,
                message.external_user_id,
                message.timestamp,
                meta,
                ttl,
            )
        return row is not None

    async def provider_message_id_exists(self, conversation_id: str, platform_id: str) -> bool:
        """True if this conversation already stores the platform message id."""
        if not platform_id or not str(platform_id).strip():
            return False
        pid = str(platform_id).strip()
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 1
                FROM messages
                WHERE conversation_id = $1
                  AND (
                    external_message_id = $2
                    OR COALESCE(metadata::jsonb -> 'provider_message_ids', '[]'::jsonb)
                       @> jsonb_build_array($2::text)
                  )
                LIMIT 1
                """,
                conversation_id,
                pid,
            )
        return row is not None

    async def stamp_provider_message_ids(
        self, conversation_id: str, message_id: str, ids: list[str]
    ) -> None:
        """Write platform ids onto one existing row. No-op if ids empty or row missing."""
        cleaned = _unique_nonempty_ids(ids)
        if not cleaned:
            return
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT external_message_id, metadata
                    FROM messages
                    WHERE conversation_id = $1 AND message_id = $2
                    """,
                    conversation_id,
                    message_id,
                )
                if not row:
                    return
                existing_ext = row["external_message_id"]
                meta = _parse_json(row["metadata"])
                if not isinstance(meta, dict):
                    meta = {}
                existing_ids = meta.get("provider_message_ids") or []
                if not isinstance(existing_ids, list):
                    existing_ids = []
                merged = _unique_nonempty_ids([*existing_ids, *cleaned])
                meta["provider_message_ids"] = merged
                new_ext = existing_ext
                if not (existing_ext and str(existing_ext).strip()):
                    new_ext = cleaned[0]
                await conn.execute(
                    """
                    UPDATE messages
                    SET external_message_id = $3,
                        metadata = $4
                    WHERE conversation_id = $1 AND message_id = $2
                    """,
                    conversation_id,
                    message_id,
                    new_ext,
                    json.dumps(meta),
                )

    async def get_message(self, conversation_id: str, message_id: str) -> Optional[Message]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM messages WHERE conversation_id = $1 AND message_id = $2",
                conversation_id,
                message_id,
            )
        if not row:
            return None
        return Message(**_row_to_msg(row))

    async def list_messages(
        self,
        conversation_id: str,
        limit: int = 100,
        reverse: bool = True,
    ) -> list[Message]:
        pool = await get_pool()
        order = "DESC" if reverse else "ASC"
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT * FROM messages WHERE conversation_id = $1 ORDER BY timestamp {order} LIMIT $2",
                conversation_id,
                limit,
            )
        items = [Message(**_row_to_msg(r)) for r in rows]
        def _ts(m: Message):
            t = m.timestamp
            if isinstance(t, datetime):
                return t
            if isinstance(t, str):
                try:
                    return parse_utc_datetime(t)
                except (ValueError, AttributeError):
                    return utc_now()
            return utc_now()
        items.sort(key=_ts)
        if reverse:
            items.reverse()
        return items

    # Agent operations
    async def create_agent(self, agent_id: str, config: dict[str, Any]) -> dict[str, Any]:
        config_json = json.dumps(config)
        now = utc_now()
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO agents (agent_id, config, is_active, created_at, updated_at)
                VALUES ($1, $2::jsonb, TRUE, $3, $4)
                ON CONFLICT (agent_id) DO UPDATE SET
                    config = EXCLUDED.config, updated_at = EXCLUDED.updated_at
                """,
                agent_id,
                config_json,
                now,
                now,
            )
        return {
            "agent_id": agent_id,
            "config": config,
            "created_at": to_utc_iso_string(now),
            "updated_at": to_utc_iso_string(now),
            "is_active": True,
        }

    async def get_agent(self, agent_id: str) -> Optional[dict[str, Any]]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM agents WHERE agent_id = $1", agent_id)
        if not row:
            return None
        d = dict(row)
        if "config" in d:
            cfg = d["config"]
            d["config"] = cfg if isinstance(cfg, dict) else json.loads(cfg) if cfg else {}
        for k in ("created_at", "updated_at"):
            if d.get(k) and isinstance(d[k], datetime):
                d[k] = to_utc_iso_string(d[k])
        return d

    async def update_agent_status(
        self, agent_id: str, is_active: bool
    ) -> Optional[dict[str, Any]]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE agents SET is_active = $1, updated_at = $2 WHERE agent_id = $3",
                is_active,
                utc_now(),
                agent_id,
            )
        return await self.get_agent(agent_id)

    async def list_agents(self, active_only: bool = True) -> list[dict[str, Any]]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            if active_only:
                rows = await conn.fetch("SELECT * FROM agents WHERE is_active = TRUE")
            else:
                rows = await conn.fetch("SELECT * FROM agents")
        result = []
        for r in rows:
            d = dict(r)
            cfg = d.get("config")
            d["config"] = cfg if isinstance(cfg, dict) else json.loads(cfg) if cfg else {}
            for k in ("created_at", "updated_at"):
                if d.get(k) and isinstance(d[k], datetime):
                    d[k] = to_utc_iso_string(d[k])
            result.append(d)
        return result

    # Channel binding operations
    async def create_channel_binding(self, binding: ChannelBinding) -> ChannelBinding:
        ch = get_enum_value(binding.channel_type)
        meta = json.dumps(binding.metadata) if binding.metadata else "{}"
        enc_token = binding.encrypted_access_token

        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO channel_bindings (
                    binding_id, agent_id, channel_type, channel_account_id, channel_username,
                    secret_name, encrypted_access_token, is_active, is_verified,
                    created_at, updated_at, created_by, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13::jsonb)
                """,
                binding.binding_id,
                binding.agent_id,
                ch,
                binding.channel_account_id,
                binding.channel_username,
                binding.secret_name,
                enc_token,
                binding.is_active,
                binding.is_verified,
                binding.created_at,
                binding.updated_at,
                binding.created_by,
                meta,
            )
        return binding

    async def get_channel_binding(self, binding_id: str) -> Optional[ChannelBinding]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM channel_bindings WHERE binding_id = $1",
                binding_id,
            )
        if not row:
            return None
        d = _row_to_binding(row)
        d.pop("encrypted_access_token", None)
        return ChannelBinding(**d)

    async def get_channel_bindings_by_agent(
        self,
        agent_id: str,
        channel_type: Optional[str] = None,
        active_only: bool = True,
    ) -> list[ChannelBinding]:
        where = ["agent_id = $1"]
        params = [agent_id]
        if channel_type:
            where.append("channel_type = $2")
            params.append(channel_type)
        if active_only:
            where.append("is_active = TRUE")
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT * FROM channel_bindings WHERE {' AND '.join(where)}",
                *params,
            )
        result = []
        for r in rows:
            d = _row_to_binding(r)
            d.pop("encrypted_access_token", None)
            try:
                result.append(ChannelBinding(**d))
            except Exception as e:
                logger.error(f"Failed to create ChannelBinding: {e}", exc_info=True)
        return result

    async def list_channel_bindings_by_channel(
        self,
        channel_type: str,
        active_only: bool = True,
    ) -> list[ChannelBinding]:
        where = ["channel_type = $1"]
        params: list[Any] = [channel_type]
        if active_only:
            where.append("is_active = TRUE")
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT * FROM channel_bindings WHERE {' AND '.join(where)}",
                *params,
            )
        result = []
        for r in rows:
            d = _row_to_binding(r)
            d.pop("encrypted_access_token", None)
            try:
                result.append(ChannelBinding(**d))
            except Exception as e:
                logger.error(f"Failed to create ChannelBinding: {e}", exc_info=True)
        return result

    async def get_channel_binding_by_account_id(
        self, channel_type: str, account_id: str
    ) -> Optional[ChannelBinding]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM channel_bindings WHERE channel_type = $1 AND channel_account_id = $2",
                channel_type,
                account_id,
            )
        if not rows:
            return None
        active = [r for r in rows if r.get("is_active", True)]
        r = active[0] if active else rows[0]
        d = _row_to_binding(r)
        d.pop("encrypted_access_token", None)
        return ChannelBinding(**d)

    async def update_channel_binding(
        self, binding_id: str, **kwargs: Any
    ) -> Optional[ChannelBinding]:
        if not kwargs:
            return await self.get_channel_binding(binding_id)
        kwargs["updated_at"] = utc_now()
        sets = []
        params = []
        for i, (k, v) in enumerate(kwargs.items(), 1):
            if k == "channel_type":
                v = get_enum_value(v)
            if k == "metadata" and v is not None:
                # Match create_channel_binding: column is jsonb; asyncpg expects JSON text here.
                v = json.dumps(v) if isinstance(v, dict) else v
                sets.append(f'"{k}" = ${i}::jsonb')
            else:
                sets.append(f'"{k}" = ${i}')
            params.append(v)
        params.append(binding_id)
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"UPDATE channel_bindings SET {', '.join(sets)} WHERE binding_id = ${len(params)}",
                *params,
            )
        return await self.get_channel_binding(binding_id)

    async def delete_channel_binding(self, binding_id: str) -> None:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM channel_bindings WHERE binding_id = $1", binding_id)

    # Notification config operations
    async def create_notification_config(
        self, config: "NotificationConfig"
    ) -> "NotificationConfig":
        from app.models.notification_config import NotificationConfig

        nt = get_enum_value(config.notification_type)
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO notification_configs (
                    config_id, notification_type, bot_token_secret_name, encrypted_bot_token,
                    chat_id, is_active, description, created_at, updated_at, created_by
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                config.config_id,
                nt,
                config.bot_token_secret_name,
                config.encrypted_bot_token,
                config.chat_id,
                config.is_active,
                config.description,
                config.created_at,
                config.updated_at,
                config.created_by,
            )
        return config

    async def get_notification_config(
        self, config_id: str
    ) -> Optional["NotificationConfig"]:
        from app.models.notification_config import NotificationConfig

        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM notification_configs WHERE config_id = $1",
                config_id,
            )
        if not row:
            return None
        return NotificationConfig(**_row_to_notification_config(row))

    async def list_notification_configs(
        self, active_only: bool = False
    ) -> list["NotificationConfig"]:
        from app.models.notification_config import NotificationConfig

        pool = await get_pool()
        async with pool.acquire() as conn:
            if active_only:
                rows = await conn.fetch("SELECT * FROM notification_configs WHERE is_active = TRUE")
            else:
                rows = await conn.fetch("SELECT * FROM notification_configs")
        return [NotificationConfig(**_row_to_notification_config(r)) for r in rows]

    async def update_notification_config(
        self, config_id: str, **kwargs: Any
    ) -> Optional["NotificationConfig"]:
        from app.models.notification_config import NotificationConfig

        if not kwargs:
            return await self.get_notification_config(config_id)
        kwargs["updated_at"] = utc_now()
        sets = []
        params = []
        for i, (k, v) in enumerate(kwargs.items(), 1):
            if k == "notification_type":
                v = get_enum_value(v)
            sets.append(f'"{k}" = ${i}')
            params.append(v)
        params.append(config_id)
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"UPDATE notification_configs SET {', '.join(sets)} WHERE config_id = ${len(params)}",
                *params,
            )
        return await self.get_notification_config(config_id)

    async def delete_notification_config(self, config_id: str) -> None:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM notification_configs WHERE config_id = $1",
                config_id,
            )

    # Audit log operations
    async def create_audit_log(
        self,
        admin_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        # Include a UUID so two actions on the same resource in one second do not collide.
        log_id = f"{resource_type}_{resource_id}_{uuid.uuid4().hex}"
        meta = json.dumps(metadata or {})
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO audit_logs (log_id, admin_id, action, resource_type, resource_id, timestamp, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                """,
                log_id,
                admin_id,
                action,
                resource_type,
                resource_id,
                utc_now(),
                meta,
            )
        return {
            "log_id": log_id,
            "admin_id": admin_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "timestamp": to_utc_iso_string(utc_now()),
            "metadata": metadata or {},
        }

    async def list_audit_logs(
        self,
        admin_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        action: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        sort_desc: bool = True,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        where = []
        params = []
        i = 1
        if admin_id:
            where.append(f"admin_id = ${i}")
            params.append(admin_id)
            i += 1
        if resource_type:
            where.append(f"resource_type = ${i}")
            params.append(resource_type)
            i += 1
        if action:
            where.append(f"action = ${i}")
            params.append(action)
            i += 1
        if start_date is not None:
            where.append(f"timestamp >= ${i}")
            params.append(start_date)
            i += 1
        if end_date is not None:
            where.append(f"timestamp <= ${i}")
            params.append(end_date)
            i += 1
        params.append(limit)
        clause = " AND ".join(where) if where else "TRUE"
        order = "DESC" if sort_desc else "ASC"
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT * FROM audit_logs WHERE {clause} ORDER BY timestamp {order} LIMIT ${i}",
                *params,
            )
        items = []
        for r in rows:
            d = dict(r)
            if "metadata" in d and isinstance(d["metadata"], str):
                d["metadata"] = _parse_json(d["metadata"])
            if "timestamp" in d and isinstance(d["timestamp"], datetime):
                d["timestamp"] = to_utc_iso_string(d["timestamp"])
            items.append(d)
        return items

    # Instagram profile operations
    async def create_or_update_instagram_profile(
        self, profile: InstagramUserProfile
    ) -> InstagramUserProfile:
        ttl = self._calculate_profile_ttl(profile.updated_at)
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO instagram_profiles (external_user_id, name, username, profile_pic, updated_at, ttl)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (external_user_id) DO UPDATE SET
                    name = EXCLUDED.name, username = EXCLUDED.username, profile_pic = EXCLUDED.profile_pic,
                    updated_at = EXCLUDED.updated_at, ttl = EXCLUDED.ttl
                """,
                profile.external_user_id,
                profile.name,
                profile.username,
                profile.profile_pic,
                profile.updated_at,
                ttl,
            )
        return profile

    async def get_instagram_profile(self, external_user_id: str) -> Optional[InstagramUserProfile]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM instagram_profiles WHERE external_user_id = $1",
                external_user_id,
            )
        if not row:
            return None
        d = dict(row)
        if d.get("updated_at") and isinstance(d["updated_at"], datetime):
            d["updated_at"] = to_utc_iso_string(d["updated_at"])
        return InstagramUserProfile(**d)


@lru_cache()
def get_postgres_client() -> PostgreSQLClient:
    settings = get_settings()
    return PostgreSQLClient(settings)
