"""Tests for integration credential validation."""

import pytest

from ai_incident_commander.integrations.credentials import (
    validate_datadog_credentials,
    validate_github_credentials,
    validate_integration_credentials,
    validate_jira_credentials,
    validate_startup_credentials,
)


def test_validate_github_credentials_accepts_fine_grained_token() -> None:
    """Fine-grained GitHub PATs pass prefix validation."""
    validate_github_credentials(
        "github_pat_11ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnop",
        "acme",
        "checkout-service",
    )


def test_validate_github_credentials_rejects_non_ascii_token() -> None:
    """Smart punctuation in GitHub tokens is rejected."""
    with pytest.raises(ValueError, match="non-ASCII"):
        validate_github_credentials(
            "github_pat_bad—token",
            "acme",
            "checkout-service",
        )


def test_validate_github_credentials_rejects_invalid_prefix() -> None:
    """Tokens without a GitHub PAT prefix are rejected."""
    with pytest.raises(ValueError, match="ghp_"):
        validate_github_credentials("not-a-github-token", "acme", "checkout-service")


def test_validate_jira_credentials_accepts_valid_values() -> None:
    """Valid Jira Cloud credentials pass validation."""
    validate_jira_credentials(
        "jira-api-token-value",
        "you@example.com",
        "https://your-org.atlassian.net",
    )


def test_validate_jira_credentials_rejects_swapped_email_and_token() -> None:
    """Using the email as the API token is rejected."""
    with pytest.raises(ValueError, match="must be different"):
        validate_jira_credentials(
            "you@example.com",
            "you@example.com",
            "https://your-org.atlassian.net",
        )


def test_validate_jira_credentials_rejects_http_base_url() -> None:
    """Jira base URLs must use HTTPS."""
    with pytest.raises(ValueError, match="https://"):
        validate_jira_credentials(
            "jira-api-token-value",
            "you@example.com",
            "http://your-org.atlassian.net",
        )


def test_validate_datadog_credentials_accepts_valid_keys() -> None:
    """Distinct Datadog API and app keys pass validation."""
    api_key = "a" * 32
    app_key = "b" * 32
    validate_datadog_credentials(api_key, app_key, "ap1.datadoghq.com")


def test_validate_datadog_credentials_rejects_identical_keys() -> None:
    """Copying the same value into both Datadog keys is rejected."""
    key = "a" * 32
    with pytest.raises(ValueError, match="must be different"):
        validate_datadog_credentials(key, key, "datadoghq.com")


def test_validate_datadog_credentials_rejects_full_site_url() -> None:
    """Datadog site must be a hostname, not a full URL."""
    with pytest.raises(ValueError, match="hostname"):
        validate_datadog_credentials("a" * 32, "b" * 32, "https://ap1.datadoghq.com")


def test_validate_startup_credentials_raises_on_invalid_github(
    make_settings,
    monkeypatch,
) -> None:
    """Startup validation blocks the process and reports invalid GitHub credentials."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    settings = make_settings(
        slack_bot_token="xoxb-bot-token",
        slack_app_token="xapp-app-token",
        github_token="not-a-github-token",
        github_repo_owner="acme",
        github_repo_name="checkout-service",
    )

    with pytest.raises(ValueError, match="Startup blocked"):
        validate_startup_credentials(settings)


def test_validate_startup_credentials_reports_all_invalid_secrets(
    make_settings,
    monkeypatch,
) -> None:
    """Startup validation collects every invalid credential before raising."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    settings = make_settings(
        slack_bot_token="xoxb-bot-token",
        slack_app_token="xoxb-bot-token",
        github_token="not-a-github-token",
        github_repo_owner="acme",
        github_repo_name="checkout-service",
        jira_api_token="you@example.com",
        jira_email="you@example.com",
        jira_base_url="http://bad.example.com",
        datadog_api_key="a" * 32,
        datadog_app_key="a" * 32,
        datadog_site="https://ap1.datadoghq.com",
    )

    with pytest.raises(ValueError, match="slack:") as exc_info:
        validate_startup_credentials(settings)

    message = str(exc_info.value)
    assert "github:" in message
    assert "jira:" in message
    assert "datadog:" in message


def test_validate_integration_credentials_skips_unconfigured_integrations(make_settings) -> None:
    """Startup validation ignores integrations with missing required fields."""
    settings = make_settings()
    validate_integration_credentials(settings)
