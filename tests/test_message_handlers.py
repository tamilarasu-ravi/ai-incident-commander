"""Tests for channel and mention incident message handlers."""

from ai_incident_commander.slack.handlers.messages import (
    _is_incident_channel_message,
    _strip_bot_mention,
)


def test_is_incident_channel_message_accepts_human_channel_post() -> None:
    """Human messages in the incidents channel qualify as triggers."""
    event = {
        "channel": "CINCIDENTS",
        "channel_type": "channel",
        "text": "checkout-service latency spike",
    }
    assert _is_incident_channel_message(event, "CINCIDENTS") is True


def test_is_incident_channel_message_ignores_other_channels() -> None:
    """Messages outside the incidents channel are ignored."""
    event = {
        "channel": "COTHER",
        "channel_type": "channel",
        "text": "checkout-service latency spike",
    }
    assert _is_incident_channel_message(event, "CINCIDENTS") is False


def test_is_incident_channel_message_ignores_im_messages() -> None:
    """Assistant IM traffic is handled by Assistant middleware."""
    event = {
        "channel": "D123",
        "channel_type": "im",
        "text": "checkout-service latency spike",
    }
    assert _is_incident_channel_message(event, "CINCIDENTS") is False


def test_strip_bot_mention_removes_leading_mention() -> None:
    """App mention text has the bot mention stripped before parsing."""
    text = "<@U123BOT> checkout-service latency spike"
    assert _strip_bot_mention(text, "U123BOT") == "checkout-service latency spike"
