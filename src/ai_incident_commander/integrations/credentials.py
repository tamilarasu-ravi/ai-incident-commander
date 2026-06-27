"""Startup validation for third-party integration credentials."""

from __future__ import annotations

import os
import re

import structlog

from ai_incident_commander.config import Settings

logger = structlog.get_logger(__name__)

GITHUB_TOKEN_PREFIXES = ("ghp_", "github_pat_", "gho_", "ghu_", "ghs_")
DATADOG_KEY_MIN_LENGTH = 32
JIRA_BASE_URL_PATTERN = re.compile(r"^https://[a-z0-9.-]+\.[a-z]{2,}(/.*)?$", re.IGNORECASE)


def validate_ascii_secret(value: str, env_name: str) -> None:
    """
    Ensure a secret contains only ASCII characters safe for HTTP headers.

    Args:
        value: Credential string from environment settings.
        env_name: Environment variable name for error messages.

    Raises:
        ValueError: If the value contains non-ASCII characters.
    """
    cleaned = value.strip()
    if cleaned and not cleaned.isascii():
        raise ValueError(
            f"{env_name} contains non-ASCII characters (often a smart dash from copy/paste). "
            f"Regenerate the credential and update `.env`."
        )


def validate_github_credentials(token: str, owner: str, repo: str) -> None:
    """
    Validate GitHub token shape and repository coordinates.

    Args:
        token: GitHub personal access token from ``GITHUB_TOKEN``.
        owner: Repository owner from ``GITHUB_REPO_OWNER``.
        repo: Repository name from ``GITHUB_REPO_NAME``.

    Raises:
        ValueError: If the token or repository coordinates look misconfigured.
    """
    cleaned_token = token.strip()
    cleaned_owner = owner.strip()
    cleaned_repo = repo.strip()

    validate_ascii_secret(cleaned_token, "GITHUB_TOKEN")

    if not any(cleaned_token.startswith(prefix) for prefix in GITHUB_TOKEN_PREFIXES):
        raise ValueError(
            "GITHUB_TOKEN must start with 'ghp_' or 'github_pat_'. "
            "Create a token at https://github.com/settings/tokens and paste the full value."
        )

    if not cleaned_owner or not cleaned_repo:
        raise ValueError(
            "GITHUB_REPO_OWNER and GITHUB_REPO_NAME are required when GITHUB_TOKEN is set."
        )

    if " " in cleaned_owner or " " in cleaned_repo:
        raise ValueError(
            "GITHUB_REPO_OWNER and GITHUB_REPO_NAME must not contain spaces."
        )


def validate_jira_credentials(api_token: str, email: str, base_url: str) -> None:
    """
    Validate Jira Cloud API token, email, and site URL.

    Args:
        api_token: Jira API token from ``JIRA_API_TOKEN``.
        email: Atlassian account email from ``JIRA_EMAIL``.
        base_url: Jira site URL from ``JIRA_BASE_URL``.

    Raises:
        ValueError: If credentials look swapped or malformed.
    """
    cleaned_token = api_token.strip()
    cleaned_email = email.strip()
    cleaned_url = base_url.strip().rstrip("/")

    validate_ascii_secret(cleaned_token, "JIRA_API_TOKEN")
    validate_ascii_secret(cleaned_email, "JIRA_EMAIL")

    if "@" not in cleaned_email:
        raise ValueError(
            "JIRA_EMAIL must be your Atlassian account email (for example you@example.com)."
        )

    if cleaned_token == cleaned_email:
        raise ValueError(
            "JIRA_API_TOKEN and JIRA_EMAIL must be different. "
            "Use your Atlassian email for JIRA_EMAIL and the API token for JIRA_API_TOKEN."
        )

    if not cleaned_url.startswith("https://"):
        raise ValueError(
            "JIRA_BASE_URL must start with https:// (for example https://your-org.atlassian.net)."
        )

    if not JIRA_BASE_URL_PATTERN.match(cleaned_url):
        raise ValueError(
            "JIRA_BASE_URL does not look like a valid Jira Cloud site URL. "
            "Use https://<your-org>.atlassian.net without a trailing /browse path."
        )


def validate_datadog_credentials(api_key: str, app_key: str, site: str) -> None:
    """
    Validate Datadog API key, application key, and site hostname.

    Args:
        api_key: Datadog API key from ``DATADOG_API_KEY``.
        app_key: Datadog application key from ``DATADOG_APP_KEY``.
        site: Datadog site hostname from ``DATADOG_SITE``.

    Raises:
        ValueError: If keys or site look misconfigured.
    """
    cleaned_api_key = api_key.strip()
    cleaned_app_key = app_key.strip()
    cleaned_site = site.strip()

    validate_ascii_secret(cleaned_api_key, "DATADOG_API_KEY")
    validate_ascii_secret(cleaned_app_key, "DATADOG_APP_KEY")

    if cleaned_api_key == cleaned_app_key:
        raise ValueError(
            "DATADOG_API_KEY and DATADOG_APP_KEY must be different. "
            "Copy the API key and Application key separately from Datadog → Organization Settings → API Keys."
        )

    if len(cleaned_api_key) < DATADOG_KEY_MIN_LENGTH:
        raise ValueError(
            f"DATADOG_API_KEY looks too short (expected at least {DATADOG_KEY_MIN_LENGTH} characters)."
        )

    if len(cleaned_app_key) < DATADOG_KEY_MIN_LENGTH:
        raise ValueError(
            f"DATADOG_APP_KEY looks too short (expected at least {DATADOG_KEY_MIN_LENGTH} characters)."
        )

    if not cleaned_site:
        raise ValueError("DATADOG_SITE is required when Datadog keys are configured.")

    if cleaned_site.startswith("http://") or cleaned_site.startswith("https://"):
        raise ValueError(
            "DATADOG_SITE should be a hostname like ap1.datadoghq.com, not a full URL."
        )

    if " " in cleaned_site or "/" in cleaned_site:
        raise ValueError(
            "DATADOG_SITE must be a hostname only (for example datadoghq.com or ap1.datadoghq.com)."
        )


def validate_llm_credentials(openai_api_key: str, google_api_key: str) -> None:
    """
    Validate LLM provider API key shape when keys are configured.

    Args:
        openai_api_key: OpenAI API key from ``OPENAI_API_KEY``.
        google_api_key: Google API key from ``GOOGLE_API_KEY``.

    Raises:
        ValueError: If a configured key looks malformed.
    """
    cleaned_openai = openai_api_key.strip()
    cleaned_google = google_api_key.strip()

    if cleaned_openai:
        validate_ascii_secret(cleaned_openai, "OPENAI_API_KEY")
        if not cleaned_openai.startswith("sk-"):
            raise ValueError(
                "OPENAI_API_KEY must start with 'sk-'. "
                "Create a key at https://platform.openai.com/api-keys."
            )

    if cleaned_google:
        validate_ascii_secret(cleaned_google, "GOOGLE_API_KEY")
        if len(cleaned_google) < 20:
            raise ValueError("GOOGLE_API_KEY looks too short.")


def validate_startup_credentials(settings: Settings) -> None:
    """
    Validate Slack and integration credentials before the application starts.

    Logs each invalid credential, then raises once with a combined summary so
    operators can fix every issue before retrying startup.

    Args:
        settings: Application settings loaded from the environment.

    Raises:
        ValueError: If any configured secret fails validation.
    """
    if "PYTEST_CURRENT_TEST" in os.environ:
        return

    from ai_incident_commander.slack.tokens import validate_slack_tokens

    errors: list[str] = []

    if settings.is_slack_socket_mode_ready:
        try:
            validate_slack_tokens(settings.slack_bot_token, settings.slack_app_token)
        except ValueError as error:
            _record_startup_credential_error(errors, "slack", error)

        if not settings.incidents_channel_id.strip():
            _record_startup_credential_error(
                errors,
                "slack",
                ValueError(
                    "INCIDENTS_CHANNEL_ID is required when Socket Mode is enabled."
                ),
            )

        if not settings.openai_api_key and not settings.google_api_key:
            _record_startup_credential_error(
                errors,
                "llm",
                ValueError(
                    "OPENAI_API_KEY or GOOGLE_API_KEY is required for RCA investigations."
                ),
            )
    elif settings.slack_bot_token or settings.slack_app_token:
        message = (
            "SLACK_BOT_TOKEN and SLACK_APP_TOKEN must both be set for Socket Mode."
        )
        _record_startup_credential_error(errors, "slack", ValueError(message))

    if settings.openai_api_key or settings.google_api_key:
        try:
            validate_llm_credentials(settings.openai_api_key, settings.google_api_key)
        except ValueError as error:
            _record_startup_credential_error(errors, "llm", error)

    if settings.is_github_configured:
        try:
            validate_github_credentials(
                settings.github_token,
                settings.github_repo_owner,
                settings.github_repo_name,
            )
        except ValueError as error:
            _record_startup_credential_error(errors, "github", error)

    if settings.is_jira_configured:
        try:
            validate_jira_credentials(
                settings.jira_api_token,
                settings.jira_email,
                settings.jira_base_url,
            )
        except ValueError as error:
            _record_startup_credential_error(errors, "jira", error)

    if settings.is_datadog_configured:
        try:
            validate_datadog_credentials(
                settings.datadog_api_key,
                settings.datadog_app_key,
                settings.datadog_site,
            )
        except ValueError as error:
            _record_startup_credential_error(errors, "datadog", error)

    if errors:
        summary = "Startup blocked — fix credential errors in `.env`:\n" + "\n".join(
            f"  - {item}" for item in errors
        )
        raise ValueError(summary)


def _record_startup_credential_error(
    errors: list[str],
    scope: str,
    error: ValueError,
) -> None:
    """
    Append a startup credential failure and emit a structured error log.

    Args:
        errors: Mutable list collecting all validation failures.
        scope: Credential group such as ``slack`` or ``github``.
        error: Validation error with operator-facing detail.
    """
    message = f"{scope}: {error}"
    errors.append(message)
    logger.error(
        "startup_credentials_invalid",
        scope=scope,
        error=str(error),
    )
