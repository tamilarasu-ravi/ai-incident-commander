"""Tests for LangGraph investigation pipeline."""

from unittest.mock import AsyncMock

import pytest

from ai_incident_commander.agents.graph import build_investigation_graph, run_investigation
from ai_incident_commander.config import Settings
from ai_incident_commander.models.eval_result import compute_confidence
from ai_incident_commander.models.grounding import GroundingVerdict
from ai_incident_commander.models.rca import RcaHypothesis
from tests.fixtures import DEMO_SERVICE_NAME


@pytest.fixture
def test_settings(make_settings):
    """Minimal settings for graph tests without real API keys."""
    return make_settings(
        openai_api_key="test-openai-key",
        google_api_key="test-google-key",
    )


@pytest.fixture
def mock_rca_hypothesis() -> RcaHypothesis:
    """Expected RCA output for the Redis demo scenario."""
    return RcaHypothesis(
        root_cause_candidate="Redis connection pool exhaustion",
        supporting_commit="abc123",
        commit_age_minutes=14,
        affected_service=DEMO_SERVICE_NAME,
        prior_incident_match="SCRUM-1",
    )


async def test_run_investigation_surfaces_rca_for_demo_service(
    monkeypatch: pytest.MonkeyPatch,
    test_settings: Settings,
    mock_rca_hypothesis: RcaHypothesis,
) -> None:
    """Demo service runs through the graph and surfaces an RCA card payload."""
    monkeypatch.setattr(
        "ai_incident_commander.agents.investigation.synthesize_rca_hypothesis",
        AsyncMock(return_value=mock_rca_hypothesis),
    )
    monkeypatch.setattr(
        "ai_incident_commander.agents.evaluator.check_grounding",
        AsyncMock(
            return_value=GroundingVerdict(
                grounded=True,
                grounding_score=1.0,
                citation="Redis connection pool exhausted",
            )
        ),
    )
    monkeypatch.setattr(
        "ai_incident_commander.agents.evaluator.score_consistency",
        AsyncMock(return_value=0.95),
    )

    final_state = await run_investigation(
        service=DEMO_SERVICE_NAME,
        description="latency spike",
        settings=test_settings,
    )

    assert final_state["status"] == "surfaced"
    assert final_state["rca"] == mock_rca_hypothesis
    assert final_state["eval_result"] is not None
    assert final_state["eval_result"].confidence == pytest.approx(
        compute_confidence(1.0, 1.0, 0.95)
    )
    assert final_state["investigation_id"]


async def test_run_investigation_errors_for_unknown_service(
    test_settings: Settings,
) -> None:
    """Unknown services stop early without calling external integrations."""
    final_state = await run_investigation(
        service="unknown-service",
        description="something broke",
        settings=test_settings,
    )

    assert final_state["status"] == "error"
    assert final_state.get("error_message")
    assert "No evidence collected" in final_state["error_message"]


async def test_graph_builds_without_error(test_settings: Settings) -> None:
    """Investigation graph compiles with configured settings."""
    graph = build_investigation_graph(test_settings)
    assert graph is not None
