"""Unit tests for `/incident` slash command parsing."""

import pytest

from ai_incident_commander.slack.incident_parse import (
    IncidentCommandParseError,
    build_investigation_message,
    parse_incident_command,
)


def test_parse_incident_command_splits_service_and_description() -> None:
    """Valid input returns service as first token and remainder as description."""
    service, description = parse_incident_command(
        "checkout-service latency spike on payment API"
    )
    assert service == "checkout-service"
    assert description == "latency spike on payment API"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "checkout-only",
        "service ",
    ],
)
def test_parse_incident_command_rejects_invalid_input(text: str) -> None:
    """Missing service or description raises IncidentCommandParseError."""
    with pytest.raises(IncidentCommandParseError):
        parse_incident_command(text)


def test_build_investigation_message_formats_announcement() -> None:
    """Announcement template includes service and description."""
    message = build_investigation_message("api-gateway", "5xx errors spiking")
    assert "api-gateway" in message
    assert "5xx errors spiking" in message
