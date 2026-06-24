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


def test_store_survives_reload_from_disk(tmp_path, monkeypatch) -> None:
    """Investigations persist to disk and reload in a new store instance."""
    from ai_incident_commander.store.investigations import (
        InvestigationStore,
        reset_investigation_store,
    )

    store_file = tmp_path / "persist.pkl"
    monkeypatch.setenv("INVESTIGATION_STORE_FILE", str(store_file))
    reset_investigation_store()

    state = InvestigationState(
        investigation_id="inv-3",
        service="checkout-service",
        description="latency spike",
        status="surfaced",
    )
    get_investigation_store().save("inv-3", state, channel_id="C123", message_ts="111.222")

    reloaded = InvestigationStore(store_file=store_file)
    record = reloaded.get("inv-3")
    assert record is not None
    assert record.channel_id == "C123"


def test_get_investigation_store_uses_postgres_when_database_url_configured(
    monkeypatch,
) -> None:
    """Factory selects PostgreSQL backend when DATABASE_URL is set."""
    from ai_incident_commander.config import get_settings
    from ai_incident_commander.store.investigations import reset_investigation_store
    from ai_incident_commander.store.postgres_store import PostgresInvestigationStore

    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://incident:incident@localhost:5432/incident_commander",
    )
    get_settings.cache_clear()
    reset_investigation_store()

    store = get_investigation_store()
    assert isinstance(store, PostgresInvestigationStore)

    reset_investigation_store()
    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()
