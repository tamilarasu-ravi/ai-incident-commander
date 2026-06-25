"""Slack WebClient factory with reliable TLS certificate verification."""

import ssl

import certifi
from slack_sdk import WebClient

DEFAULT_SLACK_API_TIMEOUT_SECONDS = 60


def create_slack_web_client(
    token: str,
    timeout: int = DEFAULT_SLACK_API_TIMEOUT_SECONDS,
) -> WebClient:
    """
    Build a Slack WebClient using Mozilla's CA bundle via certifi.

    Python.org macOS installs often lack system CA certificates, which causes
    ``CERTIFICATE_VERIFY_FAILED`` when Bolt calls ``auth.test`` on startup.

    Args:
        token: Slack bot or app-level token.
        timeout: HTTP request timeout in seconds.

    Returns:
        Configured ``WebClient`` with an explicit SSL context.
    """
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    return WebClient(token=token, ssl=ssl_context, timeout=timeout)


def create_socket_mode_web_client(app_token: str) -> WebClient:
    """
    Build a WebClient for Socket Mode ``apps.connections.open`` calls.

    Args:
        app_token: App-level token from ``SLACK_APP_TOKEN``.

    Returns:
        WebClient configured with certifi TLS and an extended timeout.
    """
    return create_slack_web_client(app_token)
