"""Bolt application factory and Socket Mode lifecycle helpers."""

import os
import threading
from typing import TYPE_CHECKING

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from ai_incident_commander.config import Settings, get_settings
from ai_incident_commander.slack.client import create_slack_web_client
from ai_incident_commander.slack.handlers.actions import register_action_handlers
from ai_incident_commander.slack.handlers.slash import register_slash_handlers

if TYPE_CHECKING:
    pass

_socket_handler: SocketModeHandler | None = None
_socket_thread: threading.Thread | None = None


def create_slack_app(settings: Settings | None = None) -> App:
    """
    Create a Bolt app with slash command handlers registered.

    Args:
        settings: Optional settings override; defaults to cached ``get_settings()``.

    Returns:
        Configured Bolt ``App`` instance.

    Raises:
        ValueError: If ``SLACK_BOT_TOKEN`` is not configured.
    """
    resolved = settings or get_settings()
    if not resolved.slack_bot_token:
        raise ValueError("SLACK_BOT_TOKEN is required to create the Slack app")

    client = create_slack_web_client(resolved.slack_bot_token)
    app = App(
        client=client,
        signing_secret=resolved.slack_signing_secret or None,
    )
    register_slash_handlers(app, resolved)
    register_action_handlers(app, resolved)
    return app


def _is_pytest_running() -> bool:
    """Return True when code is executing inside a pytest session."""
    return "PYTEST_CURRENT_TEST" in os.environ


def start_socket_mode(settings: Settings | None = None) -> None:
    """
    Start Bolt Socket Mode in a background daemon thread.

    Skips startup during pytest or when Slack tokens are not configured.

    Args:
        settings: Optional settings override; defaults to cached ``get_settings()``.

    Raises:
        ValueError: If tokens are set but Socket Mode fails to initialize.
    """
    global _socket_handler, _socket_thread

    if _is_pytest_running():
        return

    resolved = settings or get_settings()
    if not resolved.is_slack_socket_mode_ready:
        return

    if _socket_handler is not None:
        return

    bolt_app = create_slack_app(resolved)
    _socket_handler = SocketModeHandler(bolt_app, resolved.slack_app_token)
    _socket_thread = threading.Thread(
        target=_socket_handler.start,
        name="slack-socket-mode",
        daemon=True,
    )
    _socket_thread.start()


def stop_socket_mode() -> None:
    """
    Stop the Socket Mode handler if it is running.

    Safe to call when Socket Mode was never started.
    """
    global _socket_handler, _socket_thread

    if _socket_handler is not None:
        _socket_handler.close()
        _socket_handler = None

    _socket_thread = None
