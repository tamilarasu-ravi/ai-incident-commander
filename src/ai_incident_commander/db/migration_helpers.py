"""Backfill helpers for normalized investigation schema migrations."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ai_incident_commander.db.models import (
    EvalResultRow,
    EvidenceSnapshotRow,
    RcaHypothesisRow,
)
from ai_incident_commander.db.serialization import (
    build_eval_result_rows,
    evidence_bundle_to_json,
    investigation_state_from_json,
)


def backfill_normalized_children(connection: Connection) -> int:
    """
    Populate child tables from legacy ``investigations.state_json`` values.

    Args:
        connection: Active Alembic/SQLAlchemy connection.

    Returns:
        Number of investigations backfilled.
    """
    if not _has_state_json_column(connection):
        return 0

    result = connection.execute(
        text(
            """
            SELECT id, service, description, status, block_reason, error_message, state_json
            FROM investigations
            WHERE state_json IS NOT NULL
            """
        )
    )

    backfilled = 0
    for row in result.mappings():
        payload = row["state_json"]
        if not isinstance(payload, dict):
            continue

        investigation_id = row["id"]
        if _child_rows_exist(connection, investigation_id):
            continue

        state = investigation_state_from_json(payload)
        _insert_children(connection, investigation_id, state)
        backfilled += 1

    return backfilled


def _child_rows_exist(connection: Connection, investigation_id: str) -> bool:
    """Return True when normalized child rows already exist for an investigation."""
    result = connection.execute(
        text(
            """
            SELECT 1
            FROM evidence_snapshots
            WHERE investigation_id = :investigation_id
            UNION ALL
            SELECT 1
            FROM rca_hypotheses
            WHERE investigation_id = :investigation_id
            LIMIT 1
            """
        ),
        {"investigation_id": investigation_id},
    )
    return result.first() is not None


def _has_state_json_column(connection: Connection) -> bool:
    """Return True when the legacy ``state_json`` column still exists."""
    result = connection.execute(
        text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'investigations'
              AND column_name = 'state_json'
            """
        )
    )
    return result.first() is not None


def _insert_children(connection: Connection, investigation_id: str, state) -> None:
    """Insert normalized child rows for a single investigation state."""
    evidence = state.get("evidence")
    if evidence is not None:
        connection.execute(
            EvidenceSnapshotRow.__table__.insert().values(
                investigation_id=investigation_id,
                bundle_json=evidence_bundle_to_json(evidence),
            )
        )

    rca = state.get("rca")
    eval_result = state.get("eval_result")
    if rca is not None:
        confidence = eval_result.confidence if eval_result is not None else 0.0
        connection.execute(
            RcaHypothesisRow.__table__.insert().values(
                investigation_id=investigation_id,
                root_cause_candidate=rca.root_cause_candidate,
                supporting_commit=rca.supporting_commit,
                commit_age_minutes=rca.commit_age_minutes,
                affected_service=rca.affected_service,
                prior_incident_match=rca.prior_incident_match,
                confidence=confidence,
            )
        )

    if eval_result is not None:
        for eval_row in build_eval_result_rows(investigation_id, eval_result):
            connection.execute(EvalResultRow.__table__.insert().values(**eval_row))


def seed_children_from_state(
    investigation_id: str,
    state,
    evidence_row: EvidenceSnapshotRow | None,
    rca_row: RcaHypothesisRow | None,
    eval_rows: list[EvalResultRow],
) -> tuple[EvidenceSnapshotRow | None, RcaHypothesisRow | None, list[EvalResultRow]]:
    """
    Build ORM child rows from investigation state for repository upserts.

    Args:
        investigation_id: Parent investigation identifier.
        state: LangGraph investigation state.
        evidence_row: Existing evidence row when updating.
        rca_row: Existing RCA row when updating.
        eval_rows: Existing eval rows when updating.

    Returns:
        Tuple of evidence row, RCA row, and eval rows ready for persistence.
    """
    evidence = state.get("evidence")
    rca = state.get("rca")
    eval_result = state.get("eval_result")

    next_evidence = evidence_row
    if evidence is not None:
        bundle_json = evidence_bundle_to_json(evidence)
        if next_evidence is None:
            next_evidence = EvidenceSnapshotRow(
                investigation_id=investigation_id,
                bundle_json=bundle_json,
            )
        else:
            next_evidence.bundle_json = bundle_json

    next_rca = rca_row
    if rca is not None:
        confidence = eval_result.confidence if eval_result is not None else 0.0
        if next_rca is None:
            next_rca = RcaHypothesisRow(
                investigation_id=investigation_id,
                root_cause_candidate=rca.root_cause_candidate,
                supporting_commit=rca.supporting_commit,
                commit_age_minutes=rca.commit_age_minutes,
                affected_service=rca.affected_service,
                prior_incident_match=rca.prior_incident_match,
                confidence=confidence,
            )
        else:
            next_rca.root_cause_candidate = rca.root_cause_candidate
            next_rca.supporting_commit = rca.supporting_commit
            next_rca.commit_age_minutes = rca.commit_age_minutes
            next_rca.affected_service = rca.affected_service
            next_rca.prior_incident_match = rca.prior_incident_match
            next_rca.confidence = confidence

    next_eval_rows = list(eval_rows)
    if eval_result is not None:
        existing_by_type = {row.eval_type: row for row in next_eval_rows}
        rebuilt_rows: list[EvalResultRow] = []
        for payload in build_eval_result_rows(investigation_id, eval_result):
            current = existing_by_type.get(payload["eval_type"])
            if current is None:
                rebuilt_rows.append(EvalResultRow(**payload))
            else:
                current.score = payload["score"]
                current.passed = payload["passed"]
                current.explanation = payload["explanation"]
                rebuilt_rows.append(current)
        next_eval_rows = rebuilt_rows

    return next_evidence, next_rca, next_eval_rows
