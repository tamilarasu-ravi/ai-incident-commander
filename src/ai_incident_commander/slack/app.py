"""Bolt application factory and Socket Mode lifecycle helpers."""

import os
import time
from typing import TYPE_CHECKING

import structlog
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_bolt.util.utils import get_boot_message

from ai_incident_commander.config import Settings, get_settings
from ai_incident_commander.slack.client import create_slack_web_client
from ai_incident_commander.slack.handlers.actions import register_action_handlers
from ai_incident_commander.slack.handlers.slash import register_slash_handlers

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)

_socket_handler: SocketModeHandler | None = None
_bolt_app: App | None = None
SOCKET_MODE_CONNECT_TIMEOUT_SECONDS = 30.0


def get_slack_app(settings: Settings | None = None) -> App:
    """
    Return the shared Bolt application instance.

    Args:
        settings: Optional settings override used on first initialization.

    Returns:
        Configured Bolt ``App`` with slash and action handlers registered.
    """
    global _bolt_app
    if _bolt_app is None:
        _bolt_app = create_slack_app(settings)
    return _bolt_app


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


def _wait_for_socket_session(handler: SocketModeHandler, timeout: float) -> str:
    """
    Block until the Socket Mode WebSocket session is active.

    Args:
        handler: Connected Socket Mode handler.
        timeout: Maximum seconds to wait.

    Returns:
        Active Slack Socket Mode session ID.

    Raises:
        TimeoutError: If the session does not become ready in time.
    """
    deadline = time.monotonic() + timeout
    client = handler.client

    while time.monotonic() < deadline:
        session_id = client.session_id()
        if session_id and client.is_connected():
            # IntervalRunner starts receiving on a ~100ms tick after connect().
            time.sleep(0.15)
            if client.is_connected():
                return session_id
        time.sleep(0.05)

    raise TimeoutError(
        f"Socket Mode did not become ready within {timeout:.0f}s. "
        "Check SLACK_APP_TOKEN and network connectivity."
    )


def start_socket_mode(settings: Settings | None = None) -> None:
    """
    Connect Bolt Socket Mode and block until the WebSocket session is ready.

    Skips startup during pytest or when Slack tokens are not configured.

    Args:
        settings: Optional settings override; defaults to cached ``get_settings()``.

    Raises:
        TimeoutError: If Socket Mode does not connect within the timeout window.
        ValueError: If tokens are set but Socket Mode fails to initialize.
    """
    global _socket_handler

    if _is_pytest_running():
        return

    resolved = settings or get_settings()
    if not resolved.is_slack_socket_mode_ready:
        return

    if _socket_handler is not None:
        return

    bolt_app = get_slack_app(resolved)
    handler = SocketModeHandler(bolt_app, resolved.slack_app_token)
    handler.connect()
    session_id = _wait_for_socket_session(handler, SOCKET_MODE_CONNECT_TIMEOUT_SECONDS)
    _socket_handler = handler

    logger.info("slack_bolt_ready", message=get_boot_message())
    logger.info(
        "slack_socket_ready",
        session_id=session_id,
        pid=os.getpid(),
        hint="Safe to run /incident now — slash + buttons must hit this pid",
    )


def stop_socket_mode() -> None:
    """
    Stop the Socket Mode handler if it is running.

    Safe to call when Socket Mode was never started.
    """
    global _socket_handler

    if _socket_handler is not None:
        _socket_handler.close()
        _socket_handler = None
