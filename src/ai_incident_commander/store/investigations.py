"""In-memory investigation persistence for Slack approval actions."""

from dataclasses import dataclass
from threading import Lock
from typing import Literal

from ai_incident_commander.models.investigation import InvestigationState

ApprovalStatus = Literal["pending", "approved", "rejected"]


@dataclass
class StoredInvestigation:
    """Investigation state plus Slack message coordinates for follow-up actions."""

    state: InvestigationState
    channel_id: str
    message_ts: str
    approval_status: ApprovalStatus = "pending"
    jira_issue_key: str | None = None


class InvestigationStore:
    """Thread-safe in-memory store for surfaced investigations."""

    def __init__(self) -> None:
        self._records: dict[str, StoredInvestigation] = {}
        self._lock = Lock()

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
            self._records[investigation_id] = record
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
            return self._records.get(investigation_id)

    def mark_approved(self, investigation_id: str, jira_issue_key: str) -> StoredInvestigation | None:
        """
        Mark an investigation as approved and record the created Jira issue.

        Args:
            investigation_id: Unique investigation identifier.
            jira_issue_key: Created Jira issue key such as ``SCRUM-42``.

        Returns:
            Updated record when present, otherwise ``None``.
        """
        with self._lock:
            record = self._records.get(investigation_id)
            if record is None:
                return None
            record.approval_status = "approved"
            record.jira_issue_key = jira_issue_key
            return record

    def mark_rejected(self, investigation_id: str) -> StoredInvestigation | None:
        """
        Mark an investigation as rejected.

        Args:
            investigation_id: Unique investigation identifier.

        Returns:
            Updated record when present, otherwise ``None``.
        """
        with self._lock:
            record = self._records.get(investigation_id)
            if record is None:
                return None
            record.approval_status = "rejected"
            return record

    def clear(self) -> None:
        """Remove all stored investigations (used in tests)."""
        with self._lock:
            self._records.clear()


_store: InvestigationStore | None = None


def get_investigation_store() -> InvestigationStore:
    """
    Return the process-wide investigation store singleton.

    Returns:
        Shared ``InvestigationStore`` instance.
    """
    global _store
    if _store is None:
        _store = InvestigationStore()
    return _store
