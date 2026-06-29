"""PostgreSQL CRUD for normalized investigations."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ai_incident_commander.constants import (
    APPROVAL_ACTION_APPROVE,
    APPROVAL_ACTION_REJECT,
)
from ai_incident_commander.db.migration_helpers import seed_children_from_state
from ai_incident_commander.db.models import (
    ApprovalActionRow,
    EvalResultRow,
    EvidenceSnapshotRow,
    InvestigationRow,
    RcaHypothesisRow,
)
from ai_incident_commander.db.serialization import investigation_state_from_rows
from ai_incident_commander.models.investigation import InvestigationState
from ai_incident_commander.store.types import StoredInvestigation


def row_to_record(row: InvestigationRow) -> StoredInvestigation:
    """
    Convert an ORM row graph into the shared stored investigation record.

    Args:
        row: Investigation row with child relationships loaded.

    Returns:
        Stored investigation used by Slack handlers.
    """
    state = investigation_state_from_rows(
        row=row,
        evidence_row=row.evidence_snapshot,
        rca_row=row.rca_hypothesis,
        eval_rows=list(row.eval_results),
    )
    return StoredInvestigation(
        state=state,
        channel_id=row.channel_id,
        message_ts=row.message_ts,
        approval_status=row.approval_status,  # type: ignore[arg-type]
        jira_issue_key=row.jira_issue_key,
    )


async def _get_investigation_row(
    session: AsyncSession,
    investigation_id: str,
) -> InvestigationRow | None:
    """Load an investigation row with normalized child relationships."""
    result = await session.execute(
        select(InvestigationRow)
        .where(InvestigationRow.id == investigation_id)
        .options(
            selectinload(InvestigationRow.evidence_snapshot),
            selectinload(InvestigationRow.rca_hypothesis),
            selectinload(InvestigationRow.eval_results),
        )
    )
    return result.scalar_one_or_none()


async def _replace_eval_rows(
    session: AsyncSession,
    investigation_id: str,
    eval_rows: list[EvalResultRow],
) -> None:
    """Replace eval rows for an investigation with the latest audit snapshot."""
    await session.execute(
        delete(EvalResultRow).where(EvalResultRow.investigation_id == investigation_id)
    )
    for eval_row in eval_rows:
        session.add(eval_row)


async def _record_approval_action(
    session: AsyncSession,
    investigation_id: str,
    action: str,
    actor_slack_id: str,
    metadata: dict | None = None,
) -> None:
    """
    Append an approval workflow event for auditability.

    Args:
        session: Active async database session.
        investigation_id: Parent investigation identifier.
        action: Approval action name such as ``approve`` or ``reject``.
        actor_slack_id: Slack user ID that triggered the action.
        metadata: Optional action metadata such as a created Jira issue key.
    """
    session.add(
        ApprovalActionRow(
            id=str(uuid.uuid4()),
            investigation_id=investigation_id,
            action=action,
            actor_slack_id=actor_slack_id,
            metadata_json=metadata,
        )
    )


async def upsert_investigation(
    session: AsyncSession,
    investigation_id: str,
    state: InvestigationState,
    channel_id: str,
    message_ts: str,
) -> StoredInvestigation:
    """
    Insert or update a surfaced investigation and its normalized child rows.

    Args:
        session: Active async database session.
        investigation_id: Unique investigation identifier.
        state: Final investigation state from the graph.
        channel_id: Slack channel containing the RCA card.
        message_ts: Slack message timestamp for updates.

    Returns:
        Stored investigation record.
    """
    row = await _get_investigation_row(session, investigation_id)
    if row is None:
        row = InvestigationRow(
            id=investigation_id,
            service=state.get("service", ""),
            description=state.get("description", ""),
            status=state.get("status", "pending"),
            block_reason=state.get("block_reason"),
            error_message=state.get("error_message"),
            channel_id=channel_id,
            message_ts=message_ts,
        )
        session.add(row)
        evidence_row = None
        rca_row = None
        eval_rows: list[EvalResultRow] = []
    else:
        row.service = state.get("service", row.service)
        row.description = state.get("description", row.description)
        row.status = state.get("status", row.status)
        row.block_reason = state.get("block_reason")
        row.error_message = state.get("error_message")
        row.channel_id = channel_id
        row.message_ts = message_ts
        evidence_row = row.evidence_snapshot
        rca_row = row.rca_hypothesis
        eval_rows = list(row.eval_results)

    next_evidence, next_rca, next_eval_rows = seed_children_from_state(
        investigation_id=investigation_id,
        state=state,
        evidence_row=evidence_row,
        rca_row=rca_row,
        eval_rows=eval_rows,
    )
    if next_evidence is not None:
        session.add(next_evidence)
    if next_rca is not None:
        session.add(next_rca)
    await _replace_eval_rows(session, investigation_id, next_eval_rows)

    await session.flush()
    refreshed = await _get_investigation_row(session, investigation_id)
    if refreshed is None:
        raise RuntimeError(
            f"upsert_investigation: row {investigation_id!r} missing after flush — "
            "this is a bug in the ORM session state"
        )
    return row_to_record(refreshed)


async def get_investigation(
    session: AsyncSession,
    investigation_id: str,
) -> StoredInvestigation | None:
    """
    Load a stored investigation by ID.

    Args:
        session: Active async database session.
        investigation_id: Unique investigation identifier.

    Returns:
        Stored record when present, otherwise ``None``.
    """
    row = await _get_investigation_row(session, investigation_id)
    if row is None:
        return None
    return row_to_record(row)


async def update_message_ts(
    session: AsyncSession,
    investigation_id: str,
    message_ts: str,
) -> StoredInvestigation | None:
    """
    Attach the Slack message timestamp after the RCA card is posted.

    Args:
        session: Active async database session.
        investigation_id: Unique investigation identifier.
        message_ts: Slack message timestamp for card updates.

    Returns:
        Updated record when present, otherwise ``None``.
    """
    row = await _get_investigation_row(session, investigation_id)
    if row is None:
        return None
    row.message_ts = message_ts
    await session.flush()
    return row_to_record(row)


async def mark_approved(
    session: AsyncSession,
    investigation_id: str,
    jira_issue_key: str,
    actor_slack_id: str = "",
) -> StoredInvestigation | None:
    """
    Mark an investigation as approved and record the created Jira issue.

    Args:
        session: Active async database session.
        investigation_id: Unique investigation identifier.
        jira_issue_key: Created Jira issue key such as ``SCRUM-42``.
        actor_slack_id: Slack user ID that approved the RCA.

    Returns:
        Updated record when present, otherwise ``None``.
    """
    row = await _get_investigation_row(session, investigation_id)
    if row is None:
        return None
    row.approval_status = "approved"
    row.jira_issue_key = jira_issue_key
    await _record_approval_action(
        session,
        investigation_id,
        APPROVAL_ACTION_APPROVE,
        actor_slack_id,
        metadata={"jira_issue_key": jira_issue_key},
    )
    await session.flush()
    return row_to_record(row)


async def mark_rejected(
    session: AsyncSession,
    investigation_id: str,
    actor_slack_id: str = "",
) -> StoredInvestigation | None:
    """
    Mark an investigation as rejected.

    Args:
        session: Active async database session.
        investigation_id: Unique investigation identifier.
        actor_slack_id: Slack user ID that rejected the RCA.

    Returns:
        Updated record when present, otherwise ``None``.
    """
    row = await _get_investigation_row(session, investigation_id)
    if row is None:
        return None
    row.approval_status = "rejected"
    await _record_approval_action(
        session,
        investigation_id,
        APPROVAL_ACTION_REJECT,
        actor_slack_id,
    )
    await session.flush()
    return row_to_record(row)


async def count_investigations(session: AsyncSession) -> int:
    """Return the number of investigations currently stored."""
    result = await session.execute(select(func.count()).select_from(InvestigationRow))
    return int(result.scalar_one())


async def list_investigation_ids(session: AsyncSession) -> list[str]:
    """Return stored investigation IDs (for debugging store misses)."""
    result = await session.execute(select(InvestigationRow.id))
    return [row[0] for row in result.all()]


async def clear_investigations(session: AsyncSession) -> None:
    """Remove all stored investigations (used in tests)."""
    await session.execute(delete(ApprovalActionRow))
    await session.execute(delete(EvalResultRow))
    await session.execute(delete(EvidenceSnapshotRow))
    await session.execute(delete(RcaHypothesisRow))
    await session.execute(delete(InvestigationRow))
    await session.flush()
