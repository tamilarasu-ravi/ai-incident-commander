"""Tests for Slack token validation."""

import pytest

from ai_incident_commander.slack.tokens import validate_slack_tokens


def test_validate_slack_tokens_accepts_correct_prefixes() -> None:
    """Valid bot and app tokens pass validation."""
    validate_slack_tokens("xoxb-bot-token", "xapp-app-token")


def test_validate_slack_tokens_rejects_bot_token_as_app_token() -> None:
    """Using xoxb for SLACK_APP_TOKEN raises a clear error."""
    with pytest.raises(ValueError, match="xapp-"):
        validate_slack_tokens("xoxb-bot-token", "xoxb-bot-token")
