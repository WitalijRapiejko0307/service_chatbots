"""Lightweight Telegram Bot API helper for owner notifications.

Block D will add a full TelegramService for inbound chat. Until then, escalation
alerts and the notifications test endpoint POST to sendMessage / getMe directly.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE_URL = "https://api.telegram.org/bot"
TELEGRAM_MESSAGE_MAX_LENGTH = 4096


def _truncate_for_telegram_text(message_text: str) -> str:
    if len(message_text) <= TELEGRAM_MESSAGE_MAX_LENGTH:
        return message_text
    return message_text[: TELEGRAM_MESSAGE_MAX_LENGTH - 1] + "…"


async def verify_telegram_bot_token(bot_token: str) -> bool:
    """Verify a bot token via Telegram getMe. Returns False on any failure."""
    url = f"{TELEGRAM_API_BASE_URL}{bot_token}/getMe"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            result = response.json()
            if result.get("ok") and result.get("result"):
                bot_info = result["result"]
                logger.info(
                    "Telegram bot verified: @%s (id: %s)",
                    bot_info.get("username"),
                    bot_info.get("id"),
                )
                return True
            return False
    except Exception as e:
        logger.error("Error verifying Telegram bot token: %s", e, exc_info=True)
        return False


async def send_telegram_notification(
    bot_token: str, chat_id: str, message_text: str
) -> dict[str, Any]:
    """Send a notification message via Telegram sendMessage (no ChannelBinding)."""
    url = f"{TELEGRAM_API_BASE_URL}{bot_token}/sendMessage"
    text = _truncate_for_telegram_text(message_text)
    if len(text) < len(message_text):
        logger.warning(
            "Telegram notification truncated: %s → %s chars (API limit %s)",
            len(message_text),
            len(text),
            TELEGRAM_MESSAGE_MAX_LENGTH,
        )
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json={"chat_id": chat_id, "text": text})
        response.raise_for_status()
        result = response.json()
        if not result.get("ok"):
            raise ValueError(f"Telegram API error: {result.get('description')}")
        return result
