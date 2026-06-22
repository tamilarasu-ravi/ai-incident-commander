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

    log_level: str = Field(default="info", validation_alias="LOG_LEVEL")

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
