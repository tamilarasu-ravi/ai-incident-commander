"""Tests for external query escaping helpers."""

from ai_incident_commander.integrations.query_escape import (
    escape_jql_string,
    format_datadog_service_filter,
)


def test_escape_jql_string_escapes_quotes_and_backslashes() -> None:
    """JQL literals escape characters that would break or manipulate the query."""
    assert escape_jql_string('checkout" OR 1=1 --') == 'checkout\\" OR 1=1 --'
    assert escape_jql_string("path\\to\\service") == "path\\\\to\\\\service"


def test_format_datadog_service_filter_quotes_service_name() -> None:
    """Datadog service filters quote and escape user-controlled values."""
    assert format_datadog_service_filter("checkout-service") == 'service:"checkout-service"'
    assert (
        format_datadog_service_filter('evil" OR service:admin')
        == 'service:"evil\\" OR service:admin"'
    )
