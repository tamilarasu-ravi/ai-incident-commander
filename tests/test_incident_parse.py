"""Tests for incident trigger parsing."""

import pytest

from ai_incident_commander.slack.incident_parse import (
    IncidentCommandParseError,
    parse_incident_command,
    parse_incident_trigger,
)


def test_parse_incident_trigger_strips_incident_prefix() -> None:
    """Assistant messages may include the /incident prefix from older prompts."""
    service, description = parse_incident_trigger(
        "/incident checkout-service latency spike"
    )
    assert service == "checkout-service"
    assert description == "latency spike"


def test_parse_incident_trigger_strips_investigate_prefix() -> None:
    """Natural-language Assistant prompts may start with investigate."""
    service, description = parse_incident_trigger(
        "Investigate auth-service flaky integration test failure"
    )
    assert service == "auth-service"
    assert "flaky" in description


def test_parse_incident_trigger_accepts_plain_service_description() -> None:
    """Suggested prompts use service + description without slash syntax."""
    service, description = parse_incident_trigger("payment-service null deploy regression")
    assert service == "payment-service"
    assert description == "null deploy regression"


def test_parse_incident_command_matches_trigger_without_prefix() -> None:
    """Slash args and plain triggers share the same core parser."""
    assert parse_incident_command("checkout-service latency spike") == parse_incident_trigger(
        "checkout-service latency spike"
    )


@pytest.mark.parametrize("text", ["", "checkout-only"])
def test_parse_incident_trigger_rejects_invalid_input(text: str) -> None:
    """Missing description raises IncidentCommandParseError."""
    with pytest.raises(IncidentCommandParseError):
        parse_incident_trigger(text)
