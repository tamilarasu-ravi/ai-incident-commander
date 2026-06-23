"""Slack WebClient factory with reliable TLS certificate verification."""

import ssl

import certifi
from slack_sdk import WebClient


def create_slack_web_client(token: str) -> WebClient:
    """
    Build a Slack WebClient using Mozilla's CA bundle via certifi.

    Python.org macOS installs often lack system CA certificates, which causes
    ``CERTIFICATE_VERIFY_FAILED`` when Bolt calls ``auth.test`` on startup.

    Args:
        token: Slack bot user OAuth token (``xoxb-...``).

    Returns:
        Configured ``WebClient`` with an explicit SSL context.
    """
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    return WebClient(token=token, ssl=ssl_context)
