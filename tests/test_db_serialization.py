"""Tests for investigation state JSON serialization."""

from ai_incident_commander.db.serialization import (
    investigation_state_from_json,
    investigation_state_to_json,
)
from ai_incident_commander.models.investigation import InvestigationState
from ai_incident_commander.models.rca import RcaHypothesis
from tests.fixtures import REDIS_POOL_EXHAUSTION_BUNDLE, REDIS_POOL_STUB_EVAL


def test_investigation_state_round_trip_preserves_nested_models() -> None:
    """JSON serialization restores evidence, RCA, and eval models."""
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

    payload = investigation_state_to_json(state)
    restored = investigation_state_from_json(payload)

    assert restored["investigation_id"] == "inv-99"
    assert restored["evidence"] is not None
    assert restored["evidence"].commits[0].sha == "abc123"
    assert restored["rca"] is not None
    assert restored["rca"].supporting_commit == "abc123"
    assert restored["eval_result"] is not None
    assert restored["eval_result"].confidence == REDIS_POOL_STUB_EVAL.confidence
