"""Tests for parallel evidence collection orchestration."""

from unittest.mock import AsyncMock, patch

import pytest

from ai_incident_commander.config import Settings
from ai_incident_commander.integrations.collector import collect_live_evidence
from ai_incident_commander.models.evidence import CommitEvidence, LogClusterEvidence
from tests.fixtures import DEMO_SERVICE_NAME


@pytest.fixture
def integration_settings(make_settings):
    """Settings with both GitHub and Datadog configured."""
    return make_settings(
        github_token="test-token",
        github_repo_owner="acme",
        github_repo_name="checkout-service",
        datadog_api_key="dd-api-key",
        datadog_app_key="dd-app-key",
        datadog_site="ap1.datadoghq.com",
    )


async def test_collect_live_evidence_merges_github_and_datadog(
    integration_settings: Settings,
) -> None:
    """Live commits and log clusters are merged with fixture supplements."""
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
        bundle = await collect_live_evidence(DEMO_SERVICE_NAME, integration_settings)

    assert bundle.commits == live_commits
    assert bundle.log_clusters == live_logs
    assert len(bundle.prior_incidents) == 1
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
            await collect_live_evidence("unknown-service", settings)
