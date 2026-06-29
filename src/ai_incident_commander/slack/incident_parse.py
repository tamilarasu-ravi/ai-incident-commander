"""Parse incident investigation triggers from slash commands and Assistant messages."""

from ai_incident_commander.constants import INCIDENT_USAGE_HINT, INVESTIGATION_ANNOUNCEMENT_TEMPLATE


class IncidentCommandParseError(ValueError):
    """Raised when incident command text is missing required parts."""


def parse_incident_command(text: str) -> tuple[str, str]:
    """
    Parse command text into a service name and incident description.

    Args:
        text: Payload after optional prefixes (e.g. ``checkout-service latency spike``).

    Returns:
        Tuple of ``(service, description)``.

    Raises:
        IncidentCommandParseError: If either service or description is missing.
    """
    normalized = text.strip()
    if not normalized:
        raise IncidentCommandParseError(
            f"Missing arguments. Usage: {INCIDENT_USAGE_HINT}"
        )

    parts = normalized.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        raise IncidentCommandParseError(
            f"Description is required. Usage: {INCIDENT_USAGE_HINT}"
        )

    service = parts[0].strip()
    description = parts[1].strip()
    if not service:
        raise IncidentCommandParseError(
            f"Service name is required. Usage: {INCIDENT_USAGE_HINT}"
        )

    return service, description


def parse_incident_trigger(text: str) -> tuple[str, str]:
    """
    Parse Assistant or slash-style incident text into service and description.

    Strips optional ``/incident`` and ``investigate`` prefixes so suggested
    prompts and natural-language Assistant messages work without slash syntax.

    Args:
        text: Raw user message from Assistant or slash command args.

    Returns:
        Tuple of ``(service, description)``.

    Raises:
        IncidentCommandParseError: If service or description cannot be parsed.
    """
    normalized = text.strip()
    if normalized.lower().startswith("/incident"):
        normalized = normalized[len("/incident") :].strip()
    if normalized.lower().startswith("investigate "):
        normalized = normalized[len("investigate ") :].strip()
    return parse_incident_command(normalized)


def build_investigation_message(service: str, description: str) -> str:
    """
    Build the announcement message posted to the incidents channel.

    Args:
        service: Affected service name from the incident trigger.
        description: Free-text incident description.

    Returns:
        Slack mrkdwn-formatted investigation announcement.
    """
    return INVESTIGATION_ANNOUNCEMENT_TEMPLATE.format(
        service=service,
        description=description,
    )
