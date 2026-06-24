"""Tests for the three-stage evaluation engine."""

from unittest.mock import AsyncMock, patch

import pytest

from ai_incident_commander.agents.evaluator import run_evaluation_engine
from ai_incident_commander.config import Settings
from ai_incident_commander.evals.consistency import compare_root_causes
from ai_incident_commander.evals.coverage import score_evidence_coverage
from ai_incident_commander.evals.false_alarm import (
    assess_false_alarm,
    description_signals_false_alarm,
    is_test_only_evidence,
)
from ai_incident_commander.models.eval_result import compute_confidence
from ai_incident_commander.models.grounding import GroundingVerdict
from ai_incident_commander.models.rca import RcaHypothesis
from tests.fixtures import (
    DEMO_SERVICE_NAME,
    FLAKY_TEST_BUNDLE,
    FLAKY_TEST_SERVICE_NAME,
    NULL_DEPLOY_BUNDLE,
    NULL_DEPLOY_SERVICE_NAME,
    REDIS_POOL_EXHAUSTION_BUNDLE,
)


@pytest.fixture
def eval_settings(make_settings):
    """Settings with LLM keys for eval engine tests."""
    return make_settings(
        openai_api_key="test-openai-key",
        google_api_key="test-google-key",
    )


def _redis_rca() -> RcaHypothesis:
    return RcaHypothesis(
        root_cause_candidate="Redis connection pool exhaustion",
        supporting_commit="abc123",
        commit_age_minutes=14,
        affected_service=DEMO_SERVICE_NAME,
        prior_incident_match="SCRUM-1",
    )


def _null_deploy_rca() -> RcaHypothesis:
    return RcaHypothesis(
        root_cause_candidate="Null deploy artifact caused payment-service outage",
        supporting_commit="null01",
        commit_age_minutes=22,
        affected_service=NULL_DEPLOY_SERVICE_NAME,
    )


def _flaky_rca() -> RcaHypothesis:
    return RcaHypothesis(
        root_cause_candidate="PostgreSQL replication lag caused auth-service failures",
        supporting_commit="flk001",
        commit_age_minutes=30,
        affected_service=FLAKY_TEST_SERVICE_NAME,
    )


def _grounded_flaky_rca() -> RcaHypothesis:
    """RCA shape commonly returned by the live LLM for auth-service."""
    return RcaHypothesis(
        root_cause_candidate=(
            "Flaky auth integration test suite caused intermittent auth-service failures"
        ),
        supporting_commit="flk001",
        commit_age_minutes=30,
        affected_service=FLAKY_TEST_SERVICE_NAME,
    )


def test_redis_coverage_is_full() -> None:
    """Redis scenario evidence satisfies all coverage checks."""
    coverage, _ = score_evidence_coverage(REDIS_POOL_EXHAUSTION_BUNDLE, _redis_rca())
    assert coverage == pytest.approx(1.0)


def test_null_deploy_coverage_is_below_threshold() -> None:
    """Null deploy scenario lacks logs and prior incident context."""
    coverage, explanation = score_evidence_coverage(NULL_DEPLOY_BUNDLE, _null_deploy_rca())
    assert coverage == pytest.approx(1 / 3)
    assert "log cluster" in explanation


def test_flaky_coverage_passes_threshold() -> None:
    """Flaky test scenario has commits and logs but no prior incident context."""
    coverage, _ = score_evidence_coverage(FLAKY_TEST_BUNDLE, _flaky_rca())
    assert coverage == pytest.approx(2 / 3)


def test_flaky_fixture_is_test_only() -> None:
    """Auth-service fixture represents CI/test noise rather than production impact."""
    assert is_test_only_evidence(FLAKY_TEST_BUNDLE) is True
    assert description_signals_false_alarm("flaky test failure") is True


def test_flaky_false_alarm_guard_blocks_live_style_rca() -> None:
    """Grounded flaky-test RCA still blocks when evidence is test-only."""
    blocked, reason = assess_false_alarm(
        FLAKY_TEST_BUNDLE,
        "flaky test failure",
        _grounded_flaky_rca(),
    )
    assert blocked is True
    assert "false alarm" in reason.lower()


def test_replication_description_blocks_without_matching_evidence() -> None:
    """Replication-style alerts block when evidence has no production match."""
    blocked, reason = assess_false_alarm(
        FLAKY_TEST_BUNDLE,
        "database replication lag causing auth failures",
        _grounded_flaky_rca(),
    )
    assert blocked is True
    assert "not grounded" in reason.lower()
    assert "replication" in reason.lower()


def test_compare_root_causes_exact_match() -> None:
    """Identical root causes produce maximum consistency."""
    rca = _redis_rca()
    assert compare_root_causes(rca, rca) == 1.0


async def test_redis_scenario_invokes_consistency_eval(eval_settings: Settings) -> None:
    """Consistency eval runs after grounding passes."""
    grounded = GroundingVerdict(
        grounded=True,
        grounding_score=1.0,
        citation="Redis connection pool exhausted: max connections reached",
    )

    with (
        patch(
            "ai_incident_commander.agents.evaluator.check_grounding",
            AsyncMock(return_value=grounded),
        ),
        patch(
            "ai_incident_commander.agents.evaluator.score_consistency",
            AsyncMock(return_value=0.95),
        ) as consistency_mock,
    ):
        await run_evaluation_engine(
            evidence=REDIS_POOL_EXHAUSTION_BUNDLE,
            rca=_redis_rca(),
            service=DEMO_SERVICE_NAME,
            description="latency spike",
            settings=eval_settings,
        )

    consistency_mock.assert_awaited_once()


async def test_redis_scenario_surfaces_for_approval(eval_settings: Settings) -> None:
    """Redis pool exhaustion passes all evals and is not blocked."""
    grounded = GroundingVerdict(
        grounded=True,
        grounding_score=1.0,
        citation="Redis connection pool exhausted: max connections reached",
    )

    with (
        patch(
            "ai_incident_commander.agents.evaluator.check_grounding",
            AsyncMock(return_value=grounded),
        ),
        patch(
            "ai_incident_commander.agents.evaluator.score_consistency",
            AsyncMock(return_value=0.95),
        ),
    ):
        result = await run_evaluation_engine(
            evidence=REDIS_POOL_EXHAUSTION_BUNDLE,
            rca=_redis_rca(),
            service=DEMO_SERVICE_NAME,
            description="latency spike",
            settings=eval_settings,
        )

    assert result.blocked is False
    assert result.evidence_coverage == pytest.approx(1.0)
    assert result.grounding_score == pytest.approx(1.0)
    assert result.consistency == pytest.approx(0.95)
    assert result.confidence == pytest.approx(compute_confidence(1.0, 1.0, 0.95))


async def test_null_deploy_blocked_by_coverage(eval_settings: Settings) -> None:
    """Null deploy scenario is blocked by Eval 1 before grounding runs."""
    with patch(
        "ai_incident_commander.agents.evaluator.check_grounding",
        AsyncMock(),
    ) as grounding_mock:
        result = await run_evaluation_engine(
            evidence=NULL_DEPLOY_BUNDLE,
            rca=_null_deploy_rca(),
            service=NULL_DEPLOY_SERVICE_NAME,
            description="deploy regression",
            settings=eval_settings,
        )

    assert result.blocked is True
    assert result.evidence_coverage == pytest.approx(1 / 3)
    assert result.grounding_score == 0.0
    assert "Evidence coverage" in result.block_reason
    grounding_mock.assert_not_called()


async def test_flaky_alarm_blocked_by_grounding(eval_settings: Settings) -> None:
    """Flaky test false alarm blocks before the grounding LLM runs."""
    with (
        patch(
            "ai_incident_commander.agents.evaluator.check_grounding",
            AsyncMock(),
        ) as grounding_mock,
        patch(
            "ai_incident_commander.agents.evaluator.score_consistency",
            AsyncMock(return_value=0.7),
        ) as consistency_mock,
    ):
        result = await run_evaluation_engine(
            evidence=FLAKY_TEST_BUNDLE,
            rca=_grounded_flaky_rca(),
            service=FLAKY_TEST_SERVICE_NAME,
            description="flaky test failure",
            settings=eval_settings,
        )

    assert result.blocked is True
    assert result.evidence_coverage == pytest.approx(2 / 3)
    assert result.grounding_score == 0.0
    assert "false alarm" in result.block_reason.lower()
    grounding_mock.assert_not_called()
    consistency_mock.assert_not_called()


async def test_replication_description_blocked_in_evaluator(eval_settings: Settings) -> None:
    """Replication-style auth alerts block deterministically in live Slack demos."""
    with patch(
        "ai_incident_commander.agents.evaluator.check_grounding",
        AsyncMock(),
    ) as grounding_mock:
        result = await run_evaluation_engine(
            evidence=FLAKY_TEST_BUNDLE,
            rca=_grounded_flaky_rca(),
            service=FLAKY_TEST_SERVICE_NAME,
            description="database replication lag causing auth failures",
            settings=eval_settings,
        )

    assert result.blocked is True
    assert "replication" in result.block_reason.lower()
    grounding_mock.assert_not_called()
