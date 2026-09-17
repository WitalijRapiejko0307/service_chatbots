"""Channel sender factory and ChannelType enum tests."""

import pytest

from app.models.channel_binding import ChannelType
from app.models.message import MessageChannel
from app.services.channel_sender import (
    InstagramSender,
    TelegramSender,
    TikTokSender,
    ViberSender,
    WebChatSender,
    get_channel_sender,
)
from tests.conftest import FakeDB


def test_get_channel_sender_returns_real_senders():
    db = FakeDB()
    assert isinstance(get_channel_sender(MessageChannel.WEB_CHAT, db), WebChatSender)
    assert isinstance(get_channel_sender(MessageChannel.TELEGRAM, db), TelegramSender)
    assert isinstance(get_channel_sender(MessageChannel.VIBER, db), ViberSender)
    assert isinstance(get_channel_sender(MessageChannel.INSTAGRAM, db), InstagramSender)
    assert isinstance(get_channel_sender(MessageChannel.TIKTOK, db), TikTokSender)


def test_get_channel_sender_unknown_channel_errors():
    db = FakeDB()
    with pytest.raises(ValueError, match="Unsupported channel"):
        get_channel_sender("whatsapp", db)
    with pytest.raises(ValueError, match="Unsupported channel"):
        get_channel_sender("vk", db)


def test_channel_type_has_no_whatsapp_vk_max():
    values = {c.value for c in ChannelType}
    assert values == {"web_chat", "telegram", "viber", "instagram", "tiktok"}
    assert "whatsapp" not in values
    assert "vk" not in values
    assert "max" not in values

    msg_values = {c.value for c in MessageChannel}
    assert "whatsapp" not in msg_values
    assert "vk" not in msg_values
    assert "max" not in msg_values
