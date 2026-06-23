"""Tests for Slack RTS and channel history search."""

from unittest.mock import MagicMock

import pytest
from slack_sdk.errors import SlackApiError

from ai_incident_commander.config import Settings
from ai_incident_commander.search.rts import (
    RtsClient,
    _build_search_query,
    _extract_keywords,
    _message_matches,
    _parse_messages_to_incidents,
)


@pytest.fixture
def rts_settings(make_settings):
    """Settings with Slack bot token and incidents channel configured."""
    return make_settings(
        slack_bot_token="xoxb-test",
        incidents_channel_id="C123INCIDENT",
    )


def test_rts_client_is_configured(rts_settings: Settings) -> None:
    """Client reports configured when bot token and channel ID are present."""
    client = RtsClient(rts_settings)
    assert client.is_configured is True


def test_rts_client_not_configured_without_channel(make_settings) -> None:
    """Client reports unconfigured when incidents channel ID is missing."""
    client = RtsClient(make_settings(slack_bot_token="xoxb-test"))
    assert client.is_configured is False


def test_build_search_query_includes_service_and_keywords() -> None:
    """RTS query combines service name and description keywords."""
    query = _build_search_query("checkout-service", "latency spike redis pool")
    assert "checkout-service" in query
    assert "latency" in query
    assert "redis" in query


def test_extract_keywords_skips_stop_words() -> None:
    """Keyword extraction removes short tokens and stop words."""
    keywords = _extract_keywords("checkout-service", "the latency spike on checkout")
    assert "the" not in keywords
    assert "latency" in keywords


def test_message_matches_service_name() -> None:
    """Messages mentioning the service name are considered relevant."""
    assert _message_matches(
        "Investigating checkout-service latency spike",
        "checkout-service",
        ["latency", "spike"],
    )


def test_parse_messages_to_incidents_extracts_scrum_ids() -> None:
    """SCRUM-style ticket IDs are parsed from Slack message text."""
    messages = [
        ":rotating_light: Incident resolved — checkout-service latency spike\n*Jira:* SCRUM-1",
        "Pattern matches SCRUM-2 and SCRUM-1 from prior outages.",
    ]
    incidents = _parse_messages_to_incidents(messages, "checkout-service", limit=5)

    assert [incident.incident_id for incident in incidents] == ["SCRUM-1", "SCRUM-2"]


async def test_search_incident_context_falls_back_to_channel_history(
    rts_settings: Settings,
) -> None:
    """RTS API failures fall back to conversations.history parsing."""
    mock_client = MagicMock()
    mock_client.api_call.side_effect = SlackApiError("missing_scope", {"ok": False})
    mock_client.conversations_history.return_value = {
        "ok": True,
        "messages": [
            {
                "text": (
                    "Resolved checkout-service incident SCRUM-1 — "
                    "Redis connection pool exhausted"
                )
            }
        ],
    }

    client = RtsClient(rts_settings, slack_client=mock_client)
    incidents = await client.search_incident_context(
        service="checkout-service",
        description="latency spike redis pool",
    )

    assert len(incidents) == 1
    assert incidents[0].incident_id == "SCRUM-1"
    mock_client.conversations_history.assert_called_once()
