"""Tests for GitHub integration client."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_incident_commander.config import Settings
from ai_incident_commander.integrations.github import GitHubClient, GitHubClientError
from ai_incident_commander.mcp.client import McpClientError
from ai_incident_commander.models.evidence import CommitEvidence


@pytest.fixture
def github_settings(make_settings):
    """Settings with GitHub credentials configured."""
    return make_settings(
        github_token="test-token",
        github_repo_owner="acme",
        github_repo_name="checkout-service",
    )


def test_github_client_is_configured(github_settings: Settings) -> None:
    """Client reports configured when token and repo coordinates are present."""
    client = GitHubClient(github_settings)
    assert client.is_configured is True


def test_github_client_not_configured_without_token(make_settings) -> None:
    """Client reports unconfigured when token is missing."""
    client = GitHubClient(make_settings(github_repo_owner="acme", github_repo_name="repo"))
    assert client.is_configured is False


async def test_get_recent_commits_maps_api_response(github_settings: Settings) -> None:
    """GitHub commits API payload maps to CommitEvidence models."""
    committed_at = (datetime.now(UTC) - timedelta(minutes=14)).strftime("%Y-%m-%dT%H:%M:%SZ")
    api_payload = [
        {
            "sha": "abc123def456",
            "commit": {
                "message": "fix: increase redis max connections",
                "author": {"name": "Dev", "email": "dev@example.com", "date": committed_at},
            },
        }
    ]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = api_payload

    mock_http = AsyncMock()
    mock_http.get.return_value = mock_response
    mock_http.__aenter__.return_value = mock_http
    mock_http.__aexit__.return_value = None

    with patch("ai_incident_commander.integrations.github.httpx.AsyncClient", return_value=mock_http):
        commits = await GitHubClient(github_settings).get_recent_commits("checkout-service")

    assert len(commits) == 1
    assert commits[0].sha == "abc123d"
    assert "redis" in commits[0].message
    assert commits[0].age_minutes == 14
    assert "github.com/acme/checkout-service/commit/abc123def456" in commits[0].url


async def test_get_recent_commits_raises_on_non_ascii_token(make_settings) -> None:
    """Tokens with smart punctuation raise a clear validation error."""
    settings = make_settings(
        github_token="github_pat_bad—token",
        github_repo_owner="acme",
        github_repo_name="checkout-service",
        github_use_mcp=False,
    )

    with pytest.raises(ValueError, match="non-ASCII"):
        await GitHubClient(settings).get_recent_commits("checkout-service")


async def test_get_recent_commits_raises_on_api_error(github_settings: Settings) -> None:
    """Non-200 GitHub responses raise GitHubClientError."""
    mock_response = MagicMock()
    mock_response.status_code = 401

    mock_http = AsyncMock()
    mock_http.get.return_value = mock_response
    mock_http.__aenter__.return_value = mock_http
    mock_http.__aexit__.return_value = None

    with patch("ai_incident_commander.integrations.github.httpx.AsyncClient", return_value=mock_http):
        with pytest.raises(GitHubClientError):
            await GitHubClient(github_settings).get_recent_commits("checkout-service")


async def test_get_recent_commits_uses_mcp_when_enabled(make_settings) -> None:
    """When GITHUB_USE_MCP is true, commits are fetched via the MCP wrapper."""
    settings = make_settings(
        github_token="test-token",
        github_repo_owner="acme",
        github_repo_name="checkout-service",
        github_use_mcp=True,
    )
    expected = [
        CommitEvidence(
            sha="abc123d",
            message="fix: redis pool",
            author="dev@example.com",
            age_minutes=5,
            url="https://github.com/acme/checkout-service/commit/abc123def456",
        )
    ]

    with patch(
        "ai_incident_commander.integrations.github.fetch_recent_commits_mcp",
        new_callable=AsyncMock,
        return_value=expected,
    ) as mock_mcp:
        commits = await GitHubClient(settings).get_recent_commits("checkout-service")

    assert commits == expected
    mock_mcp.assert_awaited_once()


async def test_get_recent_commits_falls_back_to_http_on_mcp_error(make_settings) -> None:
    """MCP failures fall back to the direct GitHub REST client."""
    settings = make_settings(
        github_token="test-token",
        github_repo_owner="acme",
        github_repo_name="checkout-service",
        github_use_mcp=True,
    )
    expected = [
        CommitEvidence(
            sha="abc123d",
            message="fix: redis pool",
            author="dev@example.com",
            age_minutes=5,
            url="https://github.com/acme/checkout-service/commit/abc123def456",
        )
    ]

    with patch(
        "ai_incident_commander.integrations.github.fetch_recent_commits_mcp",
        new_callable=AsyncMock,
        side_effect=McpClientError("stdio failed"),
    ), patch(
        "ai_incident_commander.integrations.github.fetch_recent_commits_http",
        new_callable=AsyncMock,
        return_value=expected,
    ) as mock_http:
        commits = await GitHubClient(settings).get_recent_commits("checkout-service")

    assert commits == expected
    mock_http.assert_awaited_once()
