"""Per-channel capability matrix (API source of truth).

Keep in lockstep with ``configs/channel-support-matrix.json``. Tests assert they match.
Values: ``yes`` | ``limited`` | ``no`` for boolean-like cells; window/notes are keys
translated in the admin UI.
"""

from __future__ import annotations

from typing import Any

# Capability keys shown as rows in the admin support-matrix table.
CAPABILITY_KEYS: tuple[str, ...] = (
    "text_in",
    "text_out",
    "images",
    "media_other",
    "quick_replies",
    "typing",
    "restart_command",
    "proactive_first_message",
    "response_window",
    "human_handoff",
    "notes",
)

CHANNEL_ORDER: tuple[str, ...] = (
    "telegram",
    "viber",
    "instagram",
    "tiktok",
    "web_chat",
)

CHANNEL_SUPPORT_MATRIX: dict[str, dict[str, str]] = {
    "telegram": {
        "text_in": "yes",
        "text_out": "yes",
        "images": "yes",
        "media_other": "yes",
        "quick_replies": "yes",
        "typing": "no",
        "restart_command": "yes",
        "proactive_first_message": "yes",
        "response_window": "none",
        "human_handoff": "yes",
        "notes": "telegram_media_and_commands",
    },
    "viber": {
        "text_in": "yes",
        "text_out": "yes",
        "images": "yes",
        "media_other": "limited",
        "quick_replies": "yes",
        "typing": "no",
        "restart_command": "no",
        "proactive_first_message": "limited",
        "response_window": "none",
        "human_handoff": "yes",
        "notes": "viber_welcome_on_start",
    },
    "instagram": {
        "text_in": "yes",
        "text_out": "yes",
        "images": "yes",
        "media_other": "limited",
        "quick_replies": "no",
        "typing": "no",
        "restart_command": "no",
        "proactive_first_message": "no",
        "response_window": "24h",
        "human_handoff": "yes",
        "notes": "instagram_user_must_start",
    },
    "tiktok": {
        "text_in": "yes",
        "text_out": "yes",
        "images": "limited",
        "media_other": "no",
        "quick_replies": "no",
        "typing": "no",
        "restart_command": "no",
        "proactive_first_message": "no",
        "response_window": "48h_10",
        "human_handoff": "yes",
        "notes": "tiktok_text_fallback",
    },
    "web_chat": {
        "text_in": "yes",
        "text_out": "yes",
        "images": "yes",
        "media_other": "limited",
        "quick_replies": "no",
        "typing": "yes",
        "restart_command": "no",
        "proactive_first_message": "yes",
        "response_window": "none",
        "human_handoff": "yes",
        "notes": "web_chat_in_app_test",
    },
}


def get_channel_support_matrix_payload(*, tiktok_messaging_enabled: bool) -> dict[str, Any]:
    """JSON body for GET /admin/channel-support-matrix."""
    return {
        "channels": CHANNEL_ORDER,
        "capabilities": list(CAPABILITY_KEYS),
        "matrix": CHANNEL_SUPPORT_MATRIX,
        "tiktok_messaging_enabled": bool(tiktok_messaging_enabled),
        "legend": ["yes", "limited", "no"],
    }
