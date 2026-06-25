"""Tests for Jira integration client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_incident_commander.config import Settings
from ai_incident_commander.integrations.jira import JiraClient, JiraClientError
from tests.conftest import TEST_JIRA_API_TOKEN
from ai_incident_commander.models.eval_result import EvalResult
from ai_incident_commander.models.investigation import InvestigationState
from ai_incident_commander.models.rca import RcaHypothesis
from tests.fixtures import REDIS_POOL_EXHAUSTION_BUNDLE


@pytest.fixture
def jira_settings(make_settings):
    """Settings with Jira credentials configured."""
    return make_settings(
        jira_api_token=TEST_JIRA_API_TOKEN,
        jira_email="you@example.com",
        jira_base_url="https://example.atlassian.net",
        jira_project_key="SCRUM",
    )


def test_jira_client_is_configured(jira_settings: Settings) -> None:
    """Client reports configured when token, email, and base URL are present."""
    client = JiraClient(jira_settings)
    assert client.is_configured is True


def test_jira_client_not_configured_without_email(make_settings) -> None:
    """Client reports unconfigured when email is missing."""
    client = JiraClient(
        make_settings(
            jira_api_token=TEST_JIRA_API_TOKEN,
            jira_base_url="https://example.atlassian.net",
        )
    )
    assert client.is_configured is False


async def test_get_prior_incidents_maps_api_response(jira_settings: Settings) -> None:
    """Jira search API payload maps to PriorIncidentEvidence models."""
    api_payload = {
        "issues": [
            {
                "key": "SCRUM-1",
                "fields": {
                    "summary": "Redis connection pool exhaustion on checkout-service",
                    "status": {"statusCategory": {"key": "done"}},
                    "resolution": {"name": "Done"},
                },
            }
        ]
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = api_payload

    mock_http = AsyncMock()
    mock_http.post.return_value = mock_response
    mock_http.__aenter__.return_value = mock_http
    mock_http.__aexit__.return_value = None

    with patch("ai_incident_commander.integrations.jira.httpx.AsyncClient", return_value=mock_http):
        incidents = await JiraClient(jira_settings).get_prior_incidents("checkout-service")

    assert len(incidents) == 1
    assert incidents[0].incident_id == "SCRUM-1"
    assert "Redis connection pool exhaustion" in incidents[0].summary
    assert incidents[0].service == "checkout-service"
    assert incidents[0].resolved is True


async def test_get_prior_incidents_escapes_service_in_jql(jira_settings: Settings) -> None:
    """Service names with quotes are escaped in the JQL search request."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"issues": []}

    mock_http = AsyncMock()
    mock_http.post.return_value = mock_response
    mock_http.__aenter__.return_value = mock_http
    mock_http.__aexit__.return_value = None

    malicious_service = 'evil" OR 1=1 --'

    with patch("ai_incident_commander.integrations.jira.httpx.AsyncClient", return_value=mock_http):
        await JiraClient(jira_settings).get_prior_incidents(malicious_service)

    jql = mock_http.post.call_args.kwargs["json"]["jql"]
    assert 'evil\\" OR 1=1 --' in jql
    assert 'summary ~ "evil\\" OR 1=1 --"' in jql
    assert mock_http.post.call_args.args[0].endswith("/rest/api/3/search/jql")


async def test_get_prior_incidents_raises_on_api_error(jira_settings: Settings) -> None:
    """Non-200 Jira responses raise JiraClientError."""
    mock_response = MagicMock()
    mock_response.status_code = 401

    mock_http = AsyncMock()
    mock_http.post.return_value = mock_response
    mock_http.__aenter__.return_value = mock_http
    mock_http.__aexit__.return_value = None

    with patch("ai_incident_commander.integrations.jira.httpx.AsyncClient", return_value=mock_http):
        with pytest.raises(JiraClientError):
            await JiraClient(jira_settings).get_prior_incidents("checkout-service")


async def test_create_incident_ticket_returns_issue_key(jira_settings: Settings) -> None:
    """Create issue API returns the new Jira issue key."""
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"key": "SCRUM-42"}

    mock_http = AsyncMock()
    mock_http.post.return_value = mock_response
    mock_http.__aenter__.return_value = mock_http
    mock_http.__aexit__.return_value = None

    state = InvestigationState(
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

    with patch("ai_incident_commander.integrations.jira.httpx.AsyncClient", return_value=mock_http):
        issue_key = await JiraClient(jira_settings).create_incident_ticket(state)

    assert issue_key == "SCRUM-42"
    request_json = mock_http.post.call_args.kwargs["json"]
    assert request_json["fields"]["project"]["key"] == "SCRUM"
    assert "Redis connection pool exhaustion" in request_json["fields"]["summary"]
