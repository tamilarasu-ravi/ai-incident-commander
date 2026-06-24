"""Shared investigation store types."""

from dataclasses import dataclass
from typing import Literal, Protocol

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


class InvestigationStoreProtocol(Protocol):
    """Shared interface for pickle and PostgreSQL investigation stores."""

    def save(
        self,
        investigation_id: str,
        state: InvestigationState,
        channel_id: str,
        message_ts: str,
    ) -> StoredInvestigation: ...

    def get(self, investigation_id: str) -> StoredInvestigation | None: ...

    def update_message_ts(self, investigation_id: str, message_ts: str) -> StoredInvestigation | None: ...

    def mark_approved(
        self,
        investigation_id: str,
        jira_issue_key: str,
        actor_slack_id: str = "",
    ) -> StoredInvestigation | None: ...

    def mark_rejected(
        self,
        investigation_id: str,
        actor_slack_id: str = "",
    ) -> StoredInvestigation | None: ...

    def count(self) -> int: ...

    def list_ids(self) -> list[str]: ...

    def clear(self) -> None: ...
