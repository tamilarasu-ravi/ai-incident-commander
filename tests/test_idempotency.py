"""Tests for investigation idempotency keys."""

from ai_incident_commander.models.investigation_job import derive_investigation_id


def test_derive_investigation_id_is_stable() -> None:
    """The same idempotency key always maps to the same investigation ID."""
    first = derive_investigation_id("pagerduty-event-123")
    second = derive_investigation_id("pagerduty-event-123")
    assert first == second


def test_derive_investigation_id_without_key_is_unique() -> None:
    """Missing idempotency keys produce unique investigation IDs."""
    assert derive_investigation_id(None) != derive_investigation_id(None)
