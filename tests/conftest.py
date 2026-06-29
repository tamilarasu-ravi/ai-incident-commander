"""Shared pytest fixtures."""

import pytest

from ai_incident_commander.config import Settings

TEST_GITHUB_TOKEN = "github_pat_" + ("x" * 40)
TEST_DATADOG_API_KEY = "a" * 32
TEST_DATADOG_APP_KEY = "b" * 32
TEST_JIRA_API_TOKEN = "c" * 32


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
            "github_use_mcp": False,
            "jira_api_token": "",
            "jira_base_url": "",
            "jira_email": "",
            "jira_project_key": "SCRUM",
            "jira_issue_type": "Task",
            "datadog_api_key": "",
            "datadog_app_key": "",
            "datadog_site": "datadoghq.com",
            "datadog_log_index": "main",
            "evidence_lookback_hours": 2,
            "evidence_field_max_chars": 500,
            "evidence_prompt_token_budget": 6000,
            "chars_per_token_estimate": 4,
            "openai_grounding_model": "",
            "google_grounding_model": "",
            "log_level": "info",
            "pagerduty_webhook_secret": "",
            "demo_mode": False,
        }
        base.update(overrides)
        return Settings.model_construct(**base)

    return _make_settings


@pytest.fixture(autouse=True)
def clear_investigation_store(monkeypatch, tmp_path):
    """Isolate investigation store state between tests."""
    from ai_incident_commander.config import get_settings
    from ai_incident_commander.db.session import reset_database_runtime
    from ai_incident_commander.server.pagerduty_security import reset_pagerduty_dedup_cache
    from ai_incident_commander.store.investigations import (
        get_investigation_store,
        reset_investigation_store,
    )

    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("EVIDENCE_CACHE_ENABLED", "false")
    monkeypatch.setenv("REDIS_URL", "")
    get_settings.cache_clear()
    reset_database_runtime()
    reset_pagerduty_dedup_cache()

    from ai_incident_commander.integrations.circuit_breaker import reset_circuit_breakers
    from ai_incident_commander.integrations.evidence_cache import clear_evidence_cache
    from ai_incident_commander.cache.redis_client import reset_redis_client
    from ai_incident_commander.ops.investigation_queue import stop_investigation_workers

    clear_evidence_cache()
    reset_circuit_breakers()
    reset_redis_client()
    stop_investigation_workers()

    store_file = tmp_path / "investigations.json"
    monkeypatch.setenv("INVESTIGATION_STORE_FILE", str(store_file))
    reset_investigation_store()
    store = get_investigation_store()
    store.clear()
    yield
    store.clear()
    reset_investigation_store()
    reset_database_runtime()
    reset_pagerduty_dedup_cache()
    clear_evidence_cache()
    reset_circuit_breakers()
    reset_redis_client()
    stop_investigation_workers()
    get_settings.cache_clear()
