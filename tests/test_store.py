"""Tests for in-memory investigation store."""

from ai_incident_commander.models.investigation import InvestigationState
from ai_incident_commander.store.investigations import get_investigation_store


def test_save_and_get_investigation() -> None:
    """Stored investigations can be loaded by ID."""
    store = get_investigation_store()
    state = InvestigationState(
        investigation_id="inv-1",
        service="checkout-service",
        description="latency spike",
        status="surfaced",
    )
    store.save("inv-1", state, channel_id="C123", message_ts="111.222")

    record = store.get("inv-1")
    assert record is not None
    assert record.channel_id == "C123"
    assert record.message_ts == "111.222"
    assert record.approval_status == "pending"


def test_mark_approved_records_jira_key() -> None:
    """Approval updates status and stores the created Jira issue key."""
    store = get_investigation_store()
    state = InvestigationState(investigation_id="inv-2", service="checkout-service")
    store.save("inv-2", state, channel_id="C123", message_ts="111.222")

    updated = store.mark_approved("inv-2", "SCRUM-42")
    assert updated is not None
    assert updated.approval_status == "approved"
    assert updated.jira_issue_key == "SCRUM-42"
