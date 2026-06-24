"""Tests for consistency scoring with baseline RCA reuse."""

from unittest.mock import AsyncMock, patch

import pytest

from ai_incident_commander.evals.consistency import score_consistency
from ai_incident_commander.models.rca import RcaHypothesis
from tests.fixtures import DEMO_SERVICE_NAME, REDIS_POOL_EXHAUSTION_BUNDLE


def _redis_rca() -> RcaHypothesis:
    return RcaHypothesis(
        root_cause_candidate="Redis connection pool exhaustion",
        supporting_commit="abc123",
        commit_age_minutes=14,
        affected_service=DEMO_SERVICE_NAME,
        prior_incident_match="SCRUM-1",
    )


@pytest.mark.asyncio
async def test_score_consistency_reuses_baseline_rca() -> None:
    """Baseline RCA from the graph avoids a duplicate first synthesis call."""
    baseline = _redis_rca()
    second = baseline.model_copy(
        update={"root_cause_candidate": "Redis connection pool exhaustion"}
    )

    with patch(
        "ai_incident_commander.evals.consistency.synthesize_rca_hypothesis",
        AsyncMock(return_value=second),
    ) as synthesis_mock:
        score = await score_consistency(
            evidence=REDIS_POOL_EXHAUSTION_BUNDLE,
            service=DEMO_SERVICE_NAME,
            description="latency spike",
            baseline_rca=baseline,
        )

    synthesis_mock.assert_awaited_once()
    assert score == pytest.approx(1.0)
