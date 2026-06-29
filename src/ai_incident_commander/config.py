"""Environment-backed application settings."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Load configuration from environment variables and optional `.env` file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    slack_bot_token: str = Field(default="", validation_alias="SLACK_BOT_TOKEN")
    slack_app_token: str = Field(default="", validation_alias="SLACK_APP_TOKEN")
    slack_signing_secret: str = Field(
        default="", validation_alias="SLACK_SIGNING_SECRET"
    )

    incidents_channel_id: str = Field(
        default="", validation_alias="INCIDENTS_CHANNEL_ID"
    )

    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1", validation_alias="OPENAI_MODEL")
    google_api_key: str = Field(default="", validation_alias="GOOGLE_API_KEY")
    google_model: str = Field(
        default="gemini-2.0-flash",
        validation_alias="GOOGLE_MODEL",
    )

    database_url: str = Field(default="", validation_alias="DATABASE_URL")

    github_token: str = Field(default="", validation_alias="GITHUB_TOKEN")
    github_repo_owner: str = Field(default="", validation_alias="GITHUB_REPO_OWNER")
    github_repo_name: str = Field(default="", validation_alias="GITHUB_REPO_NAME")
    github_use_mcp: bool = Field(default=True, validation_alias="GITHUB_USE_MCP")

    jira_api_token: str = Field(default="", validation_alias="JIRA_API_TOKEN")
    jira_base_url: str = Field(default="", validation_alias="JIRA_BASE_URL")
    jira_email: str = Field(default="", validation_alias="JIRA_EMAIL")
    jira_project_key: str = Field(default="SCRUM", validation_alias="JIRA_PROJECT_KEY")
    jira_issue_type: str = Field(default="Task", validation_alias="JIRA_ISSUE_TYPE")

    datadog_api_key: str = Field(default="", validation_alias="DATADOG_API_KEY")
    datadog_app_key: str = Field(default="", validation_alias="DATADOG_APP_KEY")
    datadog_site: str = Field(default="datadoghq.com", validation_alias="DATADOG_SITE")
    datadog_log_index: str = Field(default="main", validation_alias="DATADOG_LOG_INDEX")

    evidence_lookback_hours: int = Field(
        default=2,
        validation_alias="EVIDENCE_LOOKBACK_HOURS",
    )
    evidence_field_max_chars: int = Field(
        default=500,
        validation_alias="EVIDENCE_FIELD_MAX_CHARS",
    )
    evidence_prompt_token_budget: int = Field(
        default=6000,
        validation_alias="EVIDENCE_PROMPT_TOKEN_BUDGET",
    )
    chars_per_token_estimate: int = Field(
        default=4,
        validation_alias="CHARS_PER_TOKEN_ESTIMATE",
    )
    openai_grounding_model: str = Field(
        default="",
        validation_alias="OPENAI_GROUNDING_MODEL",
    )
    google_grounding_model: str = Field(
        default="",
        validation_alias="GOOGLE_GROUNDING_MODEL",
    )

    log_level: str = Field(default="info", validation_alias="LOG_LEVEL")

    pagerduty_webhook_secret: str = Field(
        default="",
        validation_alias="PAGERDUTY_WEBHOOK_SECRET",
    )
    pagerduty_dedup_file: str = Field(
        default="",
        validation_alias="PAGERDUTY_DEDUP_FILE",
    )
    demo_mode: bool = Field(default=False, validation_alias="DEMO_MODE")

    app_env: str = Field(default="development", validation_alias="APP_ENV")
    require_postgres_in_production: bool = Field(
        default=True,
        validation_alias="REQUIRE_POSTGRES_IN_PRODUCTION",
    )

    run_async_timeout_seconds: int = Field(
        default=120,
        validation_alias="RUN_ASYNC_TIMEOUT_SECONDS",
    )
    max_concurrent_investigations: int = Field(
        default=3,
        validation_alias="MAX_CONCURRENT_INVESTIGATIONS",
    )
    investigation_queue_max_size: int = Field(
        default=50,
        validation_alias="INVESTIGATION_QUEUE_MAX_SIZE",
    )
    investigation_worker_threads: int = Field(
        default=2,
        validation_alias="INVESTIGATION_WORKER_THREADS",
    )
    investigation_worker_enabled: bool = Field(
        default=True,
        validation_alias="INVESTIGATION_WORKER_ENABLED",
    )

    slack_socket_mode_enabled: bool = Field(
        default=True,
        validation_alias="SLACK_SOCKET_MODE_ENABLED",
    )

    redis_url: str = Field(default="", validation_alias="REDIS_URL")

    db_pool_size: int = Field(default=5, validation_alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=10, validation_alias="DB_MAX_OVERFLOW")

    circuit_breaker_enabled: bool = Field(
        default=True,
        validation_alias="CIRCUIT_BREAKER_ENABLED",
    )
    circuit_breaker_failure_threshold: int = Field(
        default=5,
        validation_alias="CIRCUIT_BREAKER_FAILURE_THRESHOLD",
    )
    circuit_breaker_recovery_seconds: int = Field(
        default=60,
        validation_alias="CIRCUIT_BREAKER_RECOVERY_SECONDS",
    )

    evidence_cache_enabled: bool = Field(
        default=True,
        validation_alias="EVIDENCE_CACHE_ENABLED",
    )
    evidence_cache_ttl_seconds: int = Field(
        default=120,
        validation_alias="EVIDENCE_CACHE_TTL_SECONDS",
    )

    @property
    def is_production(self) -> bool:
        """Return True when ``APP_ENV`` is set to production."""
        return self.app_env.strip().lower() == "production"

    @property
    def should_start_socket_mode(self) -> bool:
        """Return True when Socket Mode should be started on API boot."""
        return self.slack_socket_mode_enabled and self.is_slack_socket_mode_ready
    def is_github_configured(self) -> bool:
        """Return True when GitHub token and repository coordinates are set."""
        return bool(
            self.github_token and self.github_repo_owner and self.github_repo_name
        )

    @property
    def is_datadog_configured(self) -> bool:
        """Return True when Datadog API and application keys are set."""
        return bool(self.datadog_api_key and self.datadog_app_key)

    @property
    def is_jira_configured(self) -> bool:
        """Return True when Jira API token, email, and base URL are set."""
        return bool(self.jira_api_token and self.jira_email and self.jira_base_url)

    @property
    def is_database_configured(self) -> bool:
        """Return True when a PostgreSQL database URL is configured."""
        return bool(self.database_url)

    @property
    def is_slack_socket_mode_ready(self) -> bool:
        """Return True when Socket Mode can be started with the configured tokens."""
        return bool(self.slack_bot_token and self.slack_app_token)


@lru_cache
def get_settings() -> Settings:
    """
    Return cached application settings loaded from the environment.

    Returns:
        Settings instance populated from env vars and `.env` when present.
    """
    return Settings()
