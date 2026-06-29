"""Slack Assistant middleware handlers (primary hackathon demo entry point)."""

from __future__ import annotations

import os
from typing import Any, Callable

import structlog
from slack_bolt import App, Assistant, BoltContext, Say, SetStatus
from slack_sdk import WebClient

from ai_incident_commander.config import Settings
from ai_incident_commander.constants import INVESTIGATION_ANNOUNCEMENT_TEMPLATE
from ai_incident_commander.slack.action_token_store import set_action_token
from ai_incident_commander.slack.incident_parse import (
    IncidentCommandParseError,
    build_investigation_message,
    parse_incident_trigger,
)
from ai_incident_commander.slack.investigation_runner import submit_investigation

logger = structlog.get_logger(__name__)

ASSISTANT_LOADING_MESSAGES = (
    "Collecting GitHub commits via MCP…",
    "Searching #incidents with Real-Time Search…",
    "Running evaluation engine…",
    "Validating RCA grounding…",
)


def register_assistant_handlers(app: App, settings: Settings) -> None:
    """
    Register Bolt Assistant middleware for Assistant-first investigations.

    Uses the same pattern as Slack's ``bolt-python-assistant-template``:
    ``Assistant.thread_started`` caches RTS ``action_token`` values and
    ``Assistant.user_message`` triggers investigations with RTS enabled.

    Args:
        app: Configured Bolt application instance.
        settings: Application settings for channel and integration configuration.
    """
    assistant = Assistant()

    @assistant.thread_started
    def handle_thread_started(
        event: dict,
        say: Say,
        logger: Any,  # noqa: ANN401
    ) -> None:
        """
        Greet the user and cache the RTS action token from the new thread.

        Args:
            event: ``assistant_thread_started`` event payload.
            say: Bolt helper to post into the Assistant thread.
            logger: Bolt logger for failures.
        """
        thread = event.get("assistant_thread") or {}
        context = thread.get("context") or {}
        channel_id = context.get("channel_id") or thread.get("channel_id") or ""
        action_token = context.get("action_token") or ""
        _cache_action_token(channel_id, action_token)
        structlog.get_logger(__name__).info(
            "assistant_thread_started",
            channel_id=channel_id,
            has_action_token=bool(action_token),
        )

        try:
            say(
                ":wave: I'm *Incident Commander*. Send a service and description "
                "(e.g. `checkout-service latency spike`), or pick a suggested prompt.\n\n"
                "I'll search Slack with *Real-Time Search*, gather evidence via *MCP*, "
                "and post the scored RCA to your incidents channel."
            )
        except Exception as error:
            logger.exception("assistant_thread_started_failed", error=str(error))

    @assistant.user_message
    def handle_user_message(
        client: WebClient,
        context: BoltContext,
        payload: dict,
        say: Say,
        set_status: SetStatus,
        get_thread_context: Callable[[], dict | None],
        logger: Any,  # noqa: ANN401
    ) -> None:
        """
        Parse Assistant messages and start an investigation with RTS enabled.

        Args:
            client: Slack Web API client.
            context: Bolt request context.
            payload: ``message.im`` payload from the Assistant thread.
            say: Bolt helper to reply in the Assistant thread.
            set_status: Bolt helper to show Assistant loading status.
            get_thread_context: Returns cached Assistant thread context including tokens.
            logger: Bolt logger for failures.
        """
        log = structlog.get_logger(__name__).bind(pid=os.getpid())
        text = (payload.get("text") or "").strip()
        log.info("assistant_message_received", text=text)

        if not settings.incidents_channel_id:
            say(
                ":warning: `INCIDENTS_CHANNEL_ID` is not configured. "
                "Set it in `.env` and restart the app."
            )
            return

        try:
            service, description = parse_incident_trigger(text)
        except IncidentCommandParseError as error:
            say(
                f":information_source: {error}\n\n"
                "In Assistant, send: `checkout-service latency spike` "
                "or pick a suggested prompt."
            )
            return

        action_token = _resolve_action_token(payload, get_thread_context)
        assistant_channel_id = payload.get("channel") or context.channel_id or ""
        assistant_thread_ts = payload.get("thread_ts") or context.thread_ts or ""
        if action_token and assistant_channel_id:
            set_action_token(assistant_channel_id, action_token)

        set_status(
            status=f"Investigating {service}…",
            loading_messages=list(ASSISTANT_LOADING_MESSAGES),
        )

        announcement = build_investigation_message(service, description)
        try:
            client.chat_postMessage(
                channel=settings.incidents_channel_id,
                text=announcement,
                mrkdwn=True,
            )
        except Exception:
            say(
                ":warning: Failed to post to #incidents. "
                "Invite the bot to the channel and verify `INCIDENTS_CHANNEL_ID`."
            )
            return

        say(
            INVESTIGATION_ANNOUNCEMENT_TEMPLATE.format(
                service=service,
                description=description,
            )
            + f"\n\nResults will also appear in <#{settings.incidents_channel_id}>."
        )

        submit_investigation(
            channel_id=settings.incidents_channel_id,
            service=service,
            description=description,
            settings=settings,
            action_token=action_token,
            assistant_thread=(assistant_channel_id, assistant_thread_ts),
        )

    app.assistant(assistant)


def _cache_action_token(channel_id: str, action_token: str) -> None:
    """
    Cache an RTS action token when Assistant thread events include one.

    Args:
        channel_id: Slack channel ID from the Assistant thread context.
        action_token: Short-lived RTS token for ``assistant.search.context``.
    """
    if channel_id and action_token:
        set_action_token(channel_id, action_token)
        structlog.get_logger(__name__).info(
            "action_token_cached",
            source="assistant_thread_started",
            channel_id=channel_id,
        )


def _resolve_action_token(
    payload: dict,
    get_thread_context: Callable[[], dict | None],
) -> str | None:
    """
    Resolve an RTS action token from the message payload or thread context.

    Args:
        payload: Incoming Assistant ``message.im`` payload.
        get_thread_context: Bolt helper returning cached Assistant context.

    Returns:
        Action token string when available, otherwise ``None``.
    """
    direct_token = payload.get("action_token")
    if isinstance(direct_token, str) and direct_token:
        return direct_token

    try:
        thread_context = get_thread_context()
    except Exception:
        thread_context = None

    if isinstance(thread_context, dict):
        token = thread_context.get("action_token")
        if isinstance(token, str) and token:
            return token

    return None
