"""Pickle-backed investigation store for local development without PostgreSQL."""

import os
import pickle
from pathlib import Path
from threading import Lock

from ai_incident_commander.models.investigation import InvestigationState
from ai_incident_commander.store.types import StoredInvestigation

DEFAULT_STORE_FILE = Path(".investigation_store.pkl")


class PickleInvestigationStore:
    """
    Thread-safe investigation store with disk persistence.

    Survives uvicorn ``--reload`` and is shared across processes on the same host
    via a pickle file (default: ``.investigation_store.pkl``).
    """

    def __init__(self, store_file: Path | None = None) -> None:
        self._records: dict[str, StoredInvestigation] = {}
        self._lock = Lock()
        self._store_file = store_file or Path(
            os.environ.get("INVESTIGATION_STORE_FILE", str(DEFAULT_STORE_FILE))
        )
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        """Merge investigations from the on-disk pickle file into memory."""
        if not self._store_file.exists():
            return
        try:
            with self._store_file.open("rb") as handle:
                payload = pickle.load(handle)
        except (OSError, pickle.PickleError):
            return
        if isinstance(payload, dict):
            self._records.update(payload)

    def _persist_to_disk(self) -> None:
        """Write the in-memory store to disk for cross-process/reload recovery."""
        self._store_file.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._store_file.with_suffix(".tmp")
        with temp_path.open("wb") as handle:
            pickle.dump(self._records, handle)
        temp_path.replace(self._store_file)

    def save(
        self,
        investigation_id: str,
        state: InvestigationState,
        channel_id: str,
        message_ts: str,
    ) -> StoredInvestigation:
        """
        Persist a surfaced investigation for later Block Kit actions.

        Args:
            investigation_id: Unique investigation identifier.
            state: Final investigation state from the graph.
            channel_id: Slack channel containing the RCA card.
            message_ts: Slack message timestamp for updates.

        Returns:
            Stored investigation record.
        """
        record = StoredInvestigation(
            state=state,
            channel_id=channel_id,
            message_ts=message_ts,
        )
        with self._lock:
            self._load_from_disk()
            self._records[investigation_id] = record
            self._persist_to_disk()
        return record

    def get(self, investigation_id: str) -> StoredInvestigation | None:
        """
        Load a stored investigation by ID.

        Args:
            investigation_id: Unique investigation identifier.

        Returns:
            Stored record when present, otherwise ``None``.
        """
        with self._lock:
            self._load_from_disk()
            return self._records.get(investigation_id)

    def update_message_ts(self, investigation_id: str, message_ts: str) -> StoredInvestigation | None:
        """
        Attach the Slack message timestamp after the RCA card is posted.

        Args:
            investigation_id: Unique investigation identifier.
            message_ts: Slack message timestamp for card updates.

        Returns:
            Updated record when present, otherwise ``None``.
        """
        with self._lock:
            self._load_from_disk()
            record = self._records.get(investigation_id)
            if record is None:
                return None
            record.message_ts = message_ts
            self._persist_to_disk()
            return record

    def mark_approved(
        self,
        investigation_id: str,
        jira_issue_key: str,
        actor_slack_id: str = "",
    ) -> StoredInvestigation | None:
        """
        Mark an investigation as approved and record the created Jira issue.

        Args:
            investigation_id: Unique investigation identifier.
            jira_issue_key: Created Jira issue key such as ``SCRUM-42``.

        Returns:
            Updated record when present, otherwise ``None``.
        """
        with self._lock:
            self._load_from_disk()
            record = self._records.get(investigation_id)
            if record is None:
                return None
            record.approval_status = "approved"
            record.jira_issue_key = jira_issue_key
            self._persist_to_disk()
            return record

    def mark_rejected(
        self,
        investigation_id: str,
        actor_slack_id: str = "",
    ) -> StoredInvestigation | None:
        """
        Mark an investigation as rejected.

        Args:
            investigation_id: Unique investigation identifier.

        Returns:
            Updated record when present, otherwise ``None``.
        """
        with self._lock:
            self._load_from_disk()
            record = self._records.get(investigation_id)
            if record is None:
                return None
            record.approval_status = "rejected"
            self._persist_to_disk()
            return record

    def count(self) -> int:
        """Return the number of investigations currently stored."""
        with self._lock:
            self._load_from_disk()
            return len(self._records)

    def list_ids(self) -> list[str]:
        """Return stored investigation IDs (for debugging store misses)."""
        with self._lock:
            self._load_from_disk()
            return list(self._records.keys())

    def clear(self) -> None:
        """Remove all stored investigations (used in tests)."""
        with self._lock:
            self._records.clear()
        if self._store_file.exists():
            self._store_file.unlink()
