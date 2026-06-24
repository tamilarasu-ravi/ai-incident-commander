"""Investigation persistence for Slack approval actions."""

from ai_incident_commander.config import get_settings
from ai_incident_commander.db.url import resolve_database_url
from ai_incident_commander.store.pickle_store import PickleInvestigationStore
from ai_incident_commander.store.types import (
    ApprovalStatus,
    InvestigationStoreProtocol,
    StoredInvestigation,
)

_store: InvestigationStoreProtocol | None = None
_postgres_database_url: str | None = None
_force_pickle: bool = False


def configure_investigation_store(*, use_postgres: bool, database_url: str = "") -> None:
    """
    Select the investigation store backend for this process.

    Args:
        use_postgres: Whether PostgreSQL should back Slack approval actions.
        database_url: Resolved PostgreSQL URL when ``use_postgres`` is True.
    """
    global _store, _postgres_database_url, _force_pickle
    _force_pickle = not use_postgres
    _postgres_database_url = database_url if use_postgres else None
    _store = None


def get_investigation_store() -> InvestigationStoreProtocol:
    """
    Return the process-wide investigation store singleton.

    Uses PostgreSQL when configured and reachable; otherwise falls back to pickle.

    Returns:
        Shared investigation store instance.
    """
    global _store
    if _store is None:
        settings = get_settings()
        if not _force_pickle and (_postgres_database_url or settings.database_url):
            from ai_incident_commander.store.postgres_store import PostgresInvestigationStore

            database_url = _postgres_database_url or resolve_database_url(settings.database_url)
            _store = PostgresInvestigationStore(database_url)
        else:
            _store = PickleInvestigationStore()
    return _store


def reset_investigation_store() -> None:
    """Reset the singleton (used in tests when the store backend changes)."""
    global _store, _postgres_database_url, _force_pickle
    _store = None
    _postgres_database_url = None
    _force_pickle = False


# Backward-compatible alias for direct pickle store construction in tests.
InvestigationStore = PickleInvestigationStore

__all__ = [
    "ApprovalStatus",
    "InvestigationStore",
    "InvestigationStoreProtocol",
    "StoredInvestigation",
    "configure_investigation_store",
    "get_investigation_store",
    "reset_investigation_store",
]
