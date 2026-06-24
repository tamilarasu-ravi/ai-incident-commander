"""Tests for normalized investigation persistence helpers."""

from datetime import UTC, datetime

from ai_incident_commander.constants import (
    EVAL_TYPE_CONSISTENCY,
    EVAL_TYPE_COVERAGE,
    EVAL_TYPE_GROUNDING,
)
from ai_incident_commander.db.models import (
    EvalResultRow,
    EvidenceSnapshotRow,
    InvestigationRow,
    RcaHypothesisRow,
)
from ai_incident_commander.db.serialization import (
    build_eval_result_rows,
    evidence_bundle_to_json,
    evidence_bundle_from_json,
    investigation_state_from_rows,
    investigation_state_to_json,
    investigation_state_from_json,
)
from ai_incident_commander.models.investigation import InvestigationState
from ai_incident_commander.models.rca import RcaHypothesis
from tests.fixtures import REDIS_POOL_EXHAUSTION_BUNDLE, REDIS_POOL_STUB_EVAL


def test_build_eval_result_rows_creates_three_audit_rows() -> None:
    """Normalized eval persistence stores one row per eval component."""
    rows = build_eval_result_rows("inv-1", REDIS_POOL_STUB_EVAL)
    assert {row["eval_type"] for row in rows} == {
        EVAL_TYPE_COVERAGE,
        EVAL_TYPE_GROUNDING,
        EVAL_TYPE_CONSISTENCY,
    }


def test_investigation_state_from_rows_round_trip() -> None:
    """Normalized rows rehydrate the same investigation state as legacy JSONB."""
    state = InvestigationState(
        investigation_id="inv-99",
        service="checkout-service",
        description="latency spike",
        evidence=REDIS_POOL_EXHAUSTION_BUNDLE,
        rca=RcaHypothesis(
            root_cause_candidate="Redis connection pool exhaustion",
            supporting_commit="abc123",
            commit_age_minutes=14,
            affected_service="checkout-service",
            prior_incident_match="SCRUM-1",
        ),
        eval_result=REDIS_POOL_STUB_EVAL,
        status="surfaced",
    )
    legacy = investigation_state_from_json(investigation_state_to_json(state))

    row = InvestigationRow(
        id="inv-99",
        service="checkout-service",
        description="latency spike",
        status="surfaced",
        block_reason=None,
        error_message=None,
        channel_id="C123",
        message_ts="111.222",
        approval_status="pending",
        jira_issue_key=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    evidence_row = EvidenceSnapshotRow(
        investigation_id="inv-99",
        bundle_json=evidence_bundle_to_json(legacy["evidence"]),  # type: ignore[arg-type]
    )
    rca = legacy["rca"]
    assert rca is not None
    eval_result = legacy["eval_result"]
    assert eval_result is not None
    rca_row = RcaHypothesisRow(
        investigation_id="inv-99",
        root_cause_candidate=rca.root_cause_candidate,
        supporting_commit=rca.supporting_commit,
        commit_age_minutes=rca.commit_age_minutes,
        affected_service=rca.affected_service,
        prior_incident_match=rca.prior_incident_match,
        confidence=eval_result.confidence,
    )
    eval_rows = [
        EvalResultRow(
            id=f"eval-{eval_type}",
            investigation_id="inv-99",
            eval_type=eval_type,
            score=score,
            passed=True,
            explanation="",
        )
        for eval_type, score in (
            (EVAL_TYPE_COVERAGE, eval_result.evidence_coverage),
            (EVAL_TYPE_GROUNDING, eval_result.grounding_score),
            (EVAL_TYPE_CONSISTENCY, eval_result.consistency),
        )
    ]

    restored = investigation_state_from_rows(row, evidence_row, rca_row, eval_rows)

    assert restored["investigation_id"] == "inv-99"
    assert restored["evidence"] is not None
    assert restored["evidence"].commits[0].sha == "abc123"
    assert restored["rca"] is not None
    assert restored["rca"].supporting_commit == "abc123"
    assert restored["eval_result"] is not None
    assert restored["eval_result"].confidence == REDIS_POOL_STUB_EVAL.confidence


def test_evidence_bundle_json_round_trip() -> None:
    """Evidence snapshots store and restore the full evidence bundle."""
    payload = evidence_bundle_to_json(REDIS_POOL_EXHAUSTION_BUNDLE)
    restored = evidence_bundle_from_json(payload)
    assert restored.commits[0].sha == REDIS_POOL_EXHAUSTION_BUNDLE.commits[0].sha
