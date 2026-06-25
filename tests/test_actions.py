"""Tests for Block Kit approval action handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

from ai_incident_commander.config import Settings
from ai_incident_commander.models.eval_result import EvalResult
from tests.conftest import TEST_JIRA_API_TOKEN
from ai_incident_commander.models.investigation import InvestigationState
from ai_incident_commander.models.rca import RcaHypothesis
from ai_incident_commander.slack.handlers.actions import _process_approve, _process_reject
from ai_incident_commander.store.investigations import get_investigation_store
from tests.fixtures import REDIS_POOL_EXHAUSTION_BUNDLE


def _surfaced_state() -> InvestigationState:
    return InvestigationState(
        investigation_id="inv-123",
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


def test_process_approve_creates_jira_and_updates_store(make_settings) -> None:
    """Approve action creates a Jira ticket and marks the investigation approved."""
    settings: Settings = make_settings(
        jira_api_token=TEST_JIRA_API_TOKEN,
        jira_email="you@example.com",
        jira_base_url="https://example.atlassian.net",
    )
    store = get_investigation_store()
    store.save("inv-123", _surfaced_state(), channel_id="C123", message_ts="111.222")

    client = MagicMock()
    client.chat_update.return_value = {"ok": True}

    with patch(
        "ai_incident_commander.slack.handlers.actions.JiraClient.create_incident_ticket",
        AsyncMock(return_value="SCRUM-42"),
    ):
        _process_approve(
            client=client,
            settings=settings,
            investigation_id="inv-123",
            actor_id="U123",
            channel_id="C123",
            message_ts="111.222",
        )

    record = store.get("inv-123")
    assert record is not None
    assert record.approval_status == "approved"
    assert record.jira_issue_key == "SCRUM-42"
    client.chat_update.assert_called_once()


def test_process_approve_rejects_duplicate_approval(make_settings) -> None:
    """Second approve click is rejected without creating another Jira ticket."""
    settings: Settings = make_settings(
        jira_api_token=TEST_JIRA_API_TOKEN,
        jira_email="you@example.com",
        jira_base_url="https://example.atlassian.net",
    )
    store = get_investigation_store()
    store.save("inv-123", _surfaced_state(), channel_id="C123", message_ts="111.222")
    store.mark_approved("inv-123", "SCRUM-42")

    client = MagicMock()

    with patch(
        "ai_incident_commander.slack.handlers.actions.JiraClient.create_incident_ticket",
        AsyncMock(return_value="SCRUM-99"),
    ) as jira_mock:
        _process_approve(
            client=client,
            settings=settings,
            investigation_id="inv-123",
            actor_id="U123",
            channel_id="C123",
            message_ts="111.222",
        )

    jira_mock.assert_not_called()
    client.chat_update.assert_not_called()
    client.chat_postEphemeral.assert_called_once()
    assert "already approved" in client.chat_postEphemeral.call_args.kwargs["text"]


def test_process_reject_marks_investigation_rejected(make_settings) -> None:
    """Reject action marks the investigation rejected and updates the card."""
    settings: Settings = make_settings()
    store = get_investigation_store()
    store.save("inv-123", _surfaced_state(), channel_id="C123", message_ts="111.222")

    client = MagicMock()
    client.chat_update.return_value = {"ok": True}

    _process_reject(
        client=client,
        settings=settings,
        investigation_id="inv-123",
        actor_id="U123",
        channel_id="C123",
        message_ts="111.222",
    )

    record = store.get("inv-123")
    assert record is not None
    assert record.approval_status == "rejected"
    client.chat_update.assert_called_once()
