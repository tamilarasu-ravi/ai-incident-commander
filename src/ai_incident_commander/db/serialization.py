"""Serialize investigation state to and from normalized PostgreSQL rows."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from ai_incident_commander.constants import (
    EVAL_TYPE_CONSISTENCY,
    EVAL_TYPE_COVERAGE,
    EVAL_TYPE_GROUNDING,
    EVIDENCE_COVERAGE_THRESHOLD,
)
from ai_incident_commander.models.eval_result import EvalResult
from ai_incident_commander.models.evidence import EvidenceBundle
from ai_incident_commander.models.investigation import InvestigationState
from ai_incident_commander.models.rca import RcaHypothesis

if TYPE_CHECKING:
    from ai_incident_commander.db.models import (
        EvalResultRow,
        EvidenceSnapshotRow,
        InvestigationRow,
        RcaHypothesisRow,
    )


def evidence_bundle_to_json(evidence: EvidenceBundle) -> dict:
    """
    Convert an evidence bundle into JSON-serializable data.

    Args:
        evidence: Collected investigation evidence.

    Returns:
        Plain dict suitable for JSONB storage.
    """
    return evidence.model_dump(mode="json")


def evidence_bundle_from_json(payload: dict) -> EvidenceBundle:
    """
    Rehydrate an evidence bundle from JSONB storage.

    Args:
        payload: Serialized evidence bundle dict.

    Returns:
        Validated ``EvidenceBundle``.
    """
    return EvidenceBundle.model_validate(payload)


def investigation_state_to_json(state: InvestigationState) -> dict:
    """
    Convert investigation state into JSON-serializable data.

    Args:
        state: LangGraph investigation state.

    Returns:
        Plain dict suitable for legacy JSONB storage or debugging.
    """
    payload = dict(state)
    evidence = payload.get("evidence")
    rca = payload.get("rca")
    eval_result = payload.get("eval_result")

    if evidence is not None:
        payload["evidence"] = evidence.model_dump(mode="json")
    if rca is not None:
        payload["rca"] = rca.model_dump(mode="json")
    if eval_result is not None:
        payload["eval_result"] = eval_result.model_dump(mode="json")

    return payload


def investigation_state_from_json(payload: dict) -> InvestigationState:
    """
    Rehydrate investigation state from JSONB storage.

    Args:
        payload: Serialized investigation state dict.

    Returns:
        Investigation state with nested Pydantic models restored.
    """
    state = dict(payload)
    evidence = state.get("evidence")
    rca = state.get("rca")
    eval_result = state.get("eval_result")

    if evidence is not None:
        state["evidence"] = EvidenceBundle.model_validate(evidence)
    if rca is not None:
        state["rca"] = RcaHypothesis.model_validate(rca)
    if eval_result is not None:
        state["eval_result"] = EvalResult.model_validate(eval_result)

    return InvestigationState(**state)


def build_eval_result_rows(
    investigation_id: str,
    eval_result: EvalResult,
) -> list[dict]:
    """
    Build eval result row payloads from a combined eval result.

    Args:
        investigation_id: Parent investigation identifier.
        eval_result: Combined evaluation outcome.

    Returns:
        Row dicts for ``coverage``, ``grounding``, and ``consistency`` eval types.
    """
    block_reason = eval_result.block_reason or ""
    return [
        {
            "id": str(uuid.uuid4()),
            "investigation_id": investigation_id,
            "eval_type": EVAL_TYPE_COVERAGE,
            "score": eval_result.evidence_coverage,
            "passed": eval_result.evidence_coverage >= EVIDENCE_COVERAGE_THRESHOLD,
            "explanation": block_reason if eval_result.blocked else "",
        },
        {
            "id": str(uuid.uuid4()),
            "investigation_id": investigation_id,
            "eval_type": EVAL_TYPE_GROUNDING,
            "score": eval_result.grounding_score,
            "passed": eval_result.grounding_score >= 1.0,
            "explanation": block_reason if eval_result.blocked else "",
        },
        {
            "id": str(uuid.uuid4()),
            "investigation_id": investigation_id,
            "eval_type": EVAL_TYPE_CONSISTENCY,
            "score": eval_result.consistency,
            "passed": not eval_result.blocked,
            "explanation": block_reason if eval_result.blocked else "",
        },
    ]


def eval_rows_to_result(eval_rows: list[EvalResultRow]) -> EvalResult | None:
    """
    Reconstruct a combined eval result from normalized eval rows.

    Args:
        eval_rows: Persisted eval rows for one investigation.

    Returns:
        Combined ``EvalResult`` when component rows exist, otherwise ``None``.
    """
    if not eval_rows:
        return None

    scores = {row.eval_type: row for row in eval_rows}
    coverage_row = scores.get(EVAL_TYPE_COVERAGE)
    grounding_row = scores.get(EVAL_TYPE_GROUNDING)
    consistency_row = scores.get(EVAL_TYPE_CONSISTENCY)
    if coverage_row is None or grounding_row is None or consistency_row is None:
        return None

    blocked = not all(row.passed for row in eval_rows)
    block_reason = next((row.explanation for row in eval_rows if row.explanation), "")
    return EvalResult.from_component_scores(
        evidence_coverage=coverage_row.score,
        grounding_score=grounding_row.score,
        consistency=consistency_row.score,
        blocked=blocked,
        block_reason=block_reason,
    )


def investigation_state_from_rows(
    row: InvestigationRow,
    evidence_row: EvidenceSnapshotRow | None,
    rca_row: RcaHypothesisRow | None,
    eval_rows: list[EvalResultRow],
) -> InvestigationState:
    """
    Reconstruct LangGraph state from normalized investigation rows.

    Args:
        row: Parent investigation row.
        evidence_row: Optional evidence snapshot row.
        rca_row: Optional RCA hypothesis row.
        eval_rows: Eval audit rows for the investigation.

    Returns:
        Investigation state used by Slack handlers and Jira integration.
    """
    evidence = (
        evidence_bundle_from_json(evidence_row.bundle_json)
        if evidence_row is not None
        else None
    )
    rca = (
        RcaHypothesis(
            root_cause_candidate=rca_row.root_cause_candidate,
            supporting_commit=rca_row.supporting_commit,
            commit_age_minutes=rca_row.commit_age_minutes,
            affected_service=rca_row.affected_service,
            prior_incident_match=rca_row.prior_incident_match,
        )
        if rca_row is not None
        else None
    )
    eval_result = eval_rows_to_result(eval_rows)

    return InvestigationState(
        investigation_id=row.id,
        service=row.service,
        description=row.description,
        evidence=evidence,
        rca=rca,
        eval_result=eval_result,
        status=row.status,  # type: ignore[typeddict-item]
        block_reason=row.block_reason,
        error_message=row.error_message,
    )
