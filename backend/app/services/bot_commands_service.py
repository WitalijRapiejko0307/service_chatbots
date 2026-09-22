"""Telegram bot commands — restart catalog only (no payments / questionnaires)."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

import httpx

from app.models.channel_binding import ChannelBinding
from app.models.conversation import Conversation, ConversationStatus, MarketingStatus
from app.services.conversation_status_service import update_conversation_with_notifications
from app.utils.datetime_utils import utc_now
from app.utils.enum_helpers import get_enum_value

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot"

TELEGRAM_BOT_COMMANDS: list[dict[str, str]] = [
    {
        "key": "restart",
        "command": "restart",
        "description": "Начать новый чат",
    },
]

CONFIGURABLE_COMMAND_KEYS: frozenset[str] = frozenset()

_DEFAULT_RESTART_WELCOME = (
    "Здравствуйте! Начнём заново.\n\n"
    "Напишите вопрос текстом или отправьте голосовое сообщение — я помогу."
)


def get_commands_status(binding: ChannelBinding) -> list[dict[str, Any]]:
    """Return the command catalog annotated with per-binding enabled flags."""
    enabled: dict[str, bool] = (binding.metadata or {}).get("telegram_commands", {}) or {}
    rows: list[dict[str, Any]] = []
    for cmd in TELEGRAM_BOT_COMMANDS:
        key = cmd["key"]
        rows.append(
            {
                "key": key,
                "command": f"/{cmd['command']}",
                "description": cmd["description"],
                "default_description": cmd["description"],
                "enabled": bool(enabled.get(key, True if key == "restart" else False)),
                "supports_custom_content": False,
            }
        )
    return rows


async def sync_telegram_commands(bot_token: str, binding: ChannelBinding) -> None:
    """Push the enabled command list to Telegram setMyCommands."""
    enabled_commands: dict[str, bool] = (binding.metadata or {}).get("telegram_commands", {}) or {}
    commands_payload = []
    for cmd in TELEGRAM_BOT_COMMANDS:
        default_on = cmd["key"] == "restart"
        if not enabled_commands.get(cmd["key"], default_on):
            continue
        commands_payload.append(
            {"command": cmd["command"], "description": cmd["description"]}
        )

    url = f"{TELEGRAM_API_BASE}{bot_token}/setMyCommands"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json={"commands": commands_payload})
            data = resp.json()
            if not data.get("ok"):
                logger.warning("setMyCommands returned not-ok: %s", data)
            else:
                logger.info(
                    "setMyCommands: %d command(s) registered for bot",
                    len(commands_payload),
                )
    except Exception as exc:
        logger.error("setMyCommands API call failed: %s", exc, exc_info=True)


async def handle_restart(
    db: Any,
    chat_id: str,
    binding: ChannelBinding,
    bot_token: str,
) -> None:
    """Close the current conversation and open a new one."""
    try:
        channel_value = get_enum_value(binding.channel_type)
        existing: list[Any] = []
        try:
            existing = await db.list_open_conversations_by_external_user(
                agent_id=binding.agent_id,
                channel=channel_value,
                external_user_id=chat_id,
            )
        except Exception:
            all_conversations = await db.list_conversations(
                agent_id=binding.agent_id,
                limit=200,
            )
            existing = [
                c
                for c in (all_conversations or [])
                if c.external_user_id == chat_id
                and get_enum_value(c.status) != ConversationStatus.CLOSED.value
            ]

        for conv in existing:
            await update_conversation_with_notifications(
                db,
                conversation_id=conv.conversation_id,
                status=ConversationStatus.CLOSED,
                closed_at=utc_now(),
            )
            logger.info(
                "Closed conversation %s for chat_id=%s via /restart",
                conv.conversation_id,
                chat_id,
            )
            try:
                from app.services.agent_reply_coordinator import cancel_all_auto_steps, cancel_timer_trigger

                await cancel_timer_trigger(conv.conversation_id)
                await cancel_all_auto_steps(conv.conversation_id)
            except Exception as exc:
                logger.warning(
                    "Could not cancel timers for conversation %s during /restart: %s",
                    conv.conversation_id,
                    exc,
                )

        new_conv_id = str(uuid.uuid4())
        new_conversation = Conversation(
            conversation_id=new_conv_id,
            agent_id=binding.agent_id,
            channel=channel_value,
            external_user_id=chat_id,
            status=ConversationStatus.AI_ACTIVE,
            marketing_status=MarketingStatus.NEW,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        await db.create_conversation(new_conversation)
        logger.info(
            "Created new conversation %s for chat_id=%s via /restart",
            new_conv_id,
            chat_id,
        )

        welcome_text = _DEFAULT_RESTART_WELCOME
        try:
            agent_data = await db.get_agent(binding.agent_id)
            if agent_data and "config" in agent_data:
                tpl = (agent_data["config"].get("prompts") or {}).get("templates") or {}
                custom = (tpl.get("restart_welcome") or "").strip()
                if custom:
                    welcome_text = custom
        except Exception as exc:
            logger.debug("Could not load restart_welcome template: %s", exc)

        await _send_telegram_message(bot_token=bot_token, chat_id=chat_id, text=welcome_text)
    except Exception as exc:
        logger.error(
            "handle_restart failed for chat_id=%s binding=%s: %s",
            chat_id,
            binding.binding_id,
            exc,
            exc_info=True,
        )


COMMAND_HANDLERS: dict[str, Any] = {
    "restart": handle_restart,
}


async def _send_telegram_message(
    bot_token: str,
    chat_id: str,
    text: str,
) -> None:
    payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
    url = f"{TELEGRAM_API_BASE}{bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
            if not data.get("ok"):
                logger.warning("sendMessage returned not-ok: %s", data)
    except Exception as exc:
        logger.error("sendMessage failed for chat_id=%s: %s", chat_id, exc)


async def dispatch_command(
    command: str,
    chat_id: str,
    binding: ChannelBinding,
    bot_token: str,
    db: Any,
) -> bool:
    """Handle a bot command. Returns True if handled (do not pass to the agent)."""
    cmd_key = command.lstrip("/").split("@")[0].split()[0].lower()
    if cmd_key == "start":
        cmd_key = "restart"

    enabled: dict[str, bool] = (binding.metadata or {}).get("telegram_commands", {}) or {}
    # /start and /restart always work so a first-time user can reset the thread.
    if cmd_key != "restart" and not enabled.get(cmd_key, False):
        return False

    handler = COMMAND_HANDLERS.get(cmd_key)
    if handler is None:
        return False

    logger.info(
        "Dispatching bot command /%s for chat_id=%s binding=%s",
        cmd_key,
        chat_id,
        binding.binding_id,
    )
    await handler(db=db, chat_id=chat_id, binding=binding, bot_token=bot_token)
    return True
