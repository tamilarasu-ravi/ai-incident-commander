"""Tests for parallel evidence collection orchestration."""

from unittest.mock import AsyncMock, patch

import pytest

from ai_incident_commander.config import Settings
from ai_incident_commander.integrations.collector import collect_live_evidence
from ai_incident_commander.models.evidence import (
    CommitEvidence,
    LogClusterEvidence,
    PriorIncidentEvidence,
)
from tests.fixtures import DEMO_SERVICE_NAME


@pytest.fixture
def integration_settings(make_settings):
    """Settings with GitHub and Datadog configured."""
    return make_settings(
        github_token="test-token",
        github_repo_owner="acme",
        github_repo_name="checkout-service",
        datadog_api_key="dd-api-key",
        datadog_app_key="dd-app-key",
        datadog_site="ap1.datadoghq.com",
    )


@pytest.fixture
def full_integration_settings(make_settings):
    """Settings with GitHub, Datadog, Jira, and Slack RTS configured."""
    return make_settings(
        github_token="test-token",
        github_repo_owner="acme",
        github_repo_name="checkout-service",
        datadog_api_key="dd-api-key",
        datadog_app_key="dd-app-key",
        datadog_site="ap1.datadoghq.com",
        jira_api_token="jira-token",
        jira_email="you@example.com",
        jira_base_url="https://example.atlassian.net",
        jira_project_key="SCRUM",
        slack_bot_token="xoxb-test",
        incidents_channel_id="C123INCIDENT",
    )


async def test_collect_live_evidence_merges_github_and_datadog(
    integration_settings: Settings,
) -> None:
    """Live commits and log clusters are merged with fixture prior incidents."""
    live_commits = [
        CommitEvidence(sha="live01", message="live commit", author="dev@example.com", age_minutes=5)
    ]
    live_logs = [
        LogClusterEvidence(message="live error", count=3, service=DEMO_SERVICE_NAME)
    ]

    with (
        patch(
            "ai_incident_commander.integrations.collector.GitHubClient.get_recent_commits",
            AsyncMock(return_value=live_commits),
        ),
        patch(
            "ai_incident_commander.integrations.collector.DatadogClient.get_log_clusters",
            AsyncMock(return_value=live_logs),
        ),
    ):
        bundle = await collect_live_evidence(
            DEMO_SERVICE_NAME,
            "latency spike",
            integration_settings,
        )

    assert bundle.commits == live_commits
    assert bundle.log_clusters == live_logs
    assert len(bundle.prior_incidents) == 1
    assert bundle.prior_incidents[0].incident_id == "SCRUM-1"


async def test_collect_live_evidence_merges_jira_and_rts_prior_incidents(
    full_integration_settings: Settings,
) -> None:
    """Jira and RTS prior incidents are merged and deduplicated."""
    jira_incidents = [
        PriorIncidentEvidence(
            incident_id="SCRUM-1",
            summary="Redis connection pool exhaustion on checkout-service",
            service=DEMO_SERVICE_NAME,
        )
    ]
    rts_incidents = [
        PriorIncidentEvidence(
            incident_id="SCRUM-1",
            summary="Slack mention of SCRUM-1",
            service=DEMO_SERVICE_NAME,
        ),
        PriorIncidentEvidence(
            incident_id="SCRUM-2",
            summary="checkout-service latency spike after deploy",
            service=DEMO_SERVICE_NAME,
        ),
    ]
    live_commits = [
        CommitEvidence(sha="live01", message="live commit", author="dev@example.com", age_minutes=5)
    ]
    live_logs = [
        LogClusterEvidence(message="live error", count=3, service=DEMO_SERVICE_NAME)
    ]

    with (
        patch(
            "ai_incident_commander.integrations.collector.GitHubClient.get_recent_commits",
            AsyncMock(return_value=live_commits),
        ),
        patch(
            "ai_incident_commander.integrations.collector.DatadogClient.get_log_clusters",
            AsyncMock(return_value=live_logs),
        ),
        patch(
            "ai_incident_commander.integrations.collector.JiraClient.get_prior_incidents",
            AsyncMock(return_value=jira_incidents),
        ),
        patch(
            "ai_incident_commander.integrations.collector.RtsClient.search_incident_context",
            AsyncMock(return_value=rts_incidents),
        ),
    ):
        bundle = await collect_live_evidence(
            DEMO_SERVICE_NAME,
            "latency spike",
            full_integration_settings,
        )

    incident_ids = {incident.incident_id for incident in bundle.prior_incidents}
    assert incident_ids == {"SCRUM-1", "SCRUM-2"}
    assert bundle.prior_incidents[0].incident_id == "SCRUM-1"


async def test_collect_live_evidence_raises_for_unknown_service(make_settings) -> None:
    """Unknown services without live data or fixtures raise ValueError."""
    settings = make_settings(
        github_token="test-token",
        github_repo_owner="acme",
        github_repo_name="repo",
    )

    with patch(
        "ai_incident_commander.integrations.collector.GitHubClient.get_recent_commits",
        AsyncMock(return_value=[]),
    ):
        with pytest.raises(ValueError, match="No evidence collected"):
            await collect_live_evidence("unknown-service", "something broke", settings)
