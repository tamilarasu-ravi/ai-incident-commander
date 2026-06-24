"""Escape user-controlled values before external search queries."""


def escape_jql_string(value: str) -> str:
    """
    Escape a string for safe inclusion inside JQL double quotes.

    Args:
        value: Raw user-supplied text such as a service name.

    Returns:
        Escaped string safe to embed in ``"..."`` JQL literals.
    """
    return value.replace("\\", "\\\\").replace('"', '\\"')


def format_datadog_service_filter(service: str) -> str:
    """
    Build a Datadog ``service:`` filter with quoted, escaped service value.

    Args:
        service: Affected service name from an incident trigger.

    Returns:
        Datadog query fragment such as ``service:"checkout-service"``.
    """
    escaped = escape_jql_string(service)
    return f'service:"{escaped}"'
