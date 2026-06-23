"""Shared pytest fixtures."""

import pytest

from ai_incident_commander.config import Settings


@pytest.fixture
def make_settings():
    """
    Build ``Settings`` without reading ``.env`` or process environment.

    Returns:
        Callable that accepts field overrides and returns a ``Settings`` instance.
    """

    def _make_settings(**overrides) -> Settings:
        base = {
            "slack_bot_token": "",
            "slack_app_token": "",
            "slack_signing_secret": "",
            "incidents_channel_id": "",
            "openai_api_key": "",
            "openai_model": "gpt-4.1",
            "google_api_key": "",
            "google_model": "gemini-2.0-flash",
            "database_url": "",
            "github_token": "",
            "github_repo_owner": "",
            "github_repo_name": "",
            "jira_api_token": "",
            "jira_base_url": "",
            "jira_email": "",
            "jira_project_key": "SCRUM",
            "datadog_api_key": "",
            "datadog_app_key": "",
            "datadog_site": "datadoghq.com",
            "datadog_log_index": "main",
            "evidence_lookback_hours": 2,
            "log_level": "info",
        }
        base.update(overrides)
        return Settings.model_construct(**base)

    return _make_settings
