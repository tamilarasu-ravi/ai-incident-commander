"""Tests for Slack Socket Mode startup behavior."""

from unittest.mock import MagicMock, patch

from ai_incident_commander.slack import app as slack_app_module


def test_start_socket_mode_spawns_background_connect_thread(make_settings) -> None:
    """FastAPI startup should not block on the Socket Mode connect call."""
    settings = make_settings(
        slack_bot_token="xoxb-bot-token",
        slack_app_token="xapp-app-token",
    )
    started: dict[str, object] = {}

    class FakeThread:
        """Capture thread target without running Socket Mode in tests."""

        def __init__(self, target, args=(), name=None, daemon=None) -> None:
            started["target"] = target
            started["args"] = args
            started["name"] = name

        def start(self) -> None:
            started["started"] = True

        def join(self, timeout=None) -> None:
            return None

    slack_app_module.stop_socket_mode()

    with (
        patch.object(slack_app_module, "_is_pytest_running", return_value=False),
        patch.object(slack_app_module.threading, "Thread", FakeThread),
    ):
        slack_app_module.start_socket_mode(settings)

    assert started.get("started") is True
    assert started["target"] is slack_app_module._connect_socket_mode_loop
    assert started["args"] == (settings,)

    slack_app_module.stop_socket_mode()


def test_connect_socket_mode_loop_sets_handler_on_success(make_settings) -> None:
    """Background connect stores the handler when Socket Mode becomes ready."""
    settings = make_settings(
        slack_bot_token="xoxb-bot-token",
        slack_app_token="xapp-app-token",
    )
    handler = MagicMock()
    handler.client.session_id.return_value = "sess-123"
    handler.client.is_connected.return_value = True

    slack_app_module._socket_shutdown.clear()
    slack_app_module._socket_handler = None
    slack_app_module._socket_thread = None

    with (
        patch.object(slack_app_module, "get_slack_app", return_value=MagicMock()),
        patch.object(slack_app_module, "SocketModeHandler", return_value=handler),
        patch.object(slack_app_module, "_wait_for_socket_session", return_value="sess-123"),
    ):
        slack_app_module._connect_socket_mode_loop(settings)

    assert slack_app_module._socket_handler is handler
    slack_app_module.stop_socket_mode()
