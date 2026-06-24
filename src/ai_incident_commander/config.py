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
    slack_signing_secret: str = Field(default="", validation_alias="SLACK_SIGNING_SECRET")

    incidents_channel_id: str = Field(default="", validation_alias="INCIDENTS_CHANNEL_ID")

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

    log_level: str = Field(default="info", validation_alias="LOG_LEVEL")

    @property
    def is_github_configured(self) -> bool:
        """Return True when GitHub token and repository coordinates are set."""
        return bool(self.github_token and self.github_repo_owner and self.github_repo_name)

    @property
    def is_datadog_configured(self) -> bool:
        """Return True when Datadog API and application keys are set."""
        return bool(self.datadog_api_key and self.datadog_app_key)

    @property
    def is_jira_configured(self) -> bool:
        """Return True when Jira API token, email, and base URL are set."""
        return bool(self.jira_api_token and self.jira_email and self.jira_base_url)

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
