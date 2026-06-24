"""Tests for investigation runner Slack posting."""

from unittest.mock import MagicMock, patch

from ai_incident_commander.config import Settings
from ai_incident_commander.models.eval_result import EvalResult
from ai_incident_commander.models.investigation import InvestigationState
from ai_incident_commander.models.rca import RcaHypothesis
from ai_incident_commander.slack.investigation_runner import post_investigation_result
from ai_incident_commander.store.investigations import get_investigation_store
from tests.fixtures import REDIS_POOL_EXHAUSTION_BUNDLE


def _surfaced_state() -> InvestigationState:
    return InvestigationState(
        investigation_id="inv-save-test",
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
        eval_result=EvalResult.from_component_scores(1.0, 1.0, 0.95),
        status="surfaced",
    )


def test_post_investigation_result_saves_before_posting_rca(make_settings) -> None:
    """Surfaced investigations are stored before Show Evidence can be clicked."""
    settings: Settings = make_settings(incidents_channel_id="C123")
    store = get_investigation_store()
    client = MagicMock()
    client.chat_postMessage.return_value = {"ok": True, "ts": "1717171717.0001"}

    with patch(
        "ai_incident_commander.slack.investigation_runner.run_investigation",
        return_value=_surfaced_state(),
    ):
        post_investigation_result(
            client=client,
            channel_id="C123",
            service="checkout-service",
            description="latency spike",
            settings=settings,
        )

    record = store.get("inv-save-test")
    assert record is not None
    assert record.channel_id == "C123"
    assert record.message_ts == "1717171717.0001"
