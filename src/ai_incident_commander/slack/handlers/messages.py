"""Channel and mention message handlers for incident triggers outside slash commands."""

from __future__ import annotations

import os
import re
import threading

import structlog
from slack_bolt import App
from slack_sdk import WebClient

from ai_incident_commander.config import Settings
from ai_incident_commander.slack.incident_parse import (
    IncidentCommandParseError,
    build_investigation_message,
    parse_incident_trigger,
)
from ai_incident_commander.slack.investigation_runner import post_investigation_result

logger = structlog.get_logger(__name__)

_MESSAGE_SUBTYPES_TO_IGNORE = frozenset(
    {
        "message_changed",
        "message_deleted",
        "bot_message",
        "channel_join",
        "channel_leave",
    }
)


def _is_incident_channel_message(event: dict, incidents_channel_id: str) -> bool:
    """
    Return True when an event is a human message in the configured incidents channel.

    Args:
        event: Slack ``message`` event payload.
        incidents_channel_id: Configured ``INCIDENTS_CHANNEL_ID`` value.

    Returns:
        Whether the event should be treated as a channel incident trigger.
    """
    if not incidents_channel_id:
        return False
    if event.get("channel") != incidents_channel_id:
        return False
    if event.get("bot_id"):
        return False
    subtype = event.get("subtype")
    if subtype in _MESSAGE_SUBTYPES_TO_IGNORE:
        return False
    if event.get("channel_type") not in (None, "channel"):
        return False
    return bool((event.get("text") or "").strip())


def _strip_bot_mention(text: str, bot_user_id: str | None) -> str:
    """
    Remove a leading ``<@BOTID>`` mention from message text.

    Args:
        text: Raw Slack message text.
        bot_user_id: Bot user ID from Bolt context, when available.

    Returns:
        Message text without the bot mention prefix.
    """
    cleaned = text.strip()
    if bot_user_id:
        mention = f"<@{bot_user_id}>"
        if cleaned.startswith(mention):
            return cleaned[len(mention) :].strip()
    return re.sub(r"^<@[A-Z0-9]+>\s*", "", cleaned).strip()


def _start_channel_investigation(
    client: WebClient,
    settings: Settings,
    service: str,
    description: str,
    *,
    thread_ts: str | None = None,
) -> None:
    """
    Announce and run an investigation triggered from a channel message.

    Args:
        client: Slack Web API client.
        settings: Application settings.
        service: Affected service name.
        description: Incident description.
        thread_ts: Optional parent message timestamp for threaded replies.
    """
    announcement = build_investigation_message(service, description)
    client.chat_postMessage(
        channel=settings.incidents_channel_id,
        text=announcement,
        thread_ts=thread_ts,
        mrkdwn=True,
    )
    post_investigation_result(
        client=client,
        channel_id=settings.incidents_channel_id,
        service=service,
        description=description,
        settings=settings,
    )


def register_message_handlers(app: App, settings: Settings) -> None:
    """
    Register handlers for ``#incidents`` channel text and ``@app_mention`` triggers.

    Plain text like ``checkout-service latency spike`` only works when posted in
    ``INCIDENTS_CHANNEL_ID`` or when the bot is @mentioned. The Slack Assistant
    panel is handled separately by ``handlers/assistant.py``.

    Args:
        app: Configured Bolt application instance.
        settings: Application settings containing channel configuration.
    """

    @app.event("message")
    def handle_channel_incident_message(event: dict, client: WebClient, context) -> None:
        """
        Start investigations from plain messages in the incidents channel.

        Args:
            event: Slack ``message`` event payload.
            client: Slack Web API client.
            context: Bolt context (may include ``bot_user_id``).
        """
        if event.get("channel_type") == "im":
            return

        if not _is_incident_channel_message(event, settings.incidents_channel_id):
            return

        text = (event.get("text") or "").strip()
        log = logger.bind(pid=os.getpid(), channel_id=event.get("channel"))
        log.info("channel_message_received", text=text)

        try:
            service, description = parse_incident_trigger(text)
        except IncidentCommandParseError:
            return

        thread = threading.Thread(
            target=_start_channel_investigation,
            kwargs={
                "client": client,
                "settings": settings,
                "service": service,
                "description": description,
                "thread_ts": event.get("ts"),
            },
            name=f"channel-investigation-{service}",
            daemon=True,
        )
        thread.start()

    @app.event("app_mention")
    def handle_app_mention(event: dict, client: WebClient, context) -> None:
        """
        Start investigations when the bot is @mentioned with service and description.

        Args:
            event: Slack ``app_mention`` event payload.
            client: Slack Web API client.
            context: Bolt context (may include ``bot_user_id``).
        """
        bot_user_id = getattr(context, "bot_user_id", None)
        text = _strip_bot_mention((event.get("text") or "").strip(), bot_user_id)
        if not text:
            return

        log = logger.bind(pid=os.getpid(), channel_id=event.get("channel"))
        log.info("app_mention_received", text=text)

        try:
            service, description = parse_incident_trigger(text)
        except IncidentCommandParseError as error:
            client.chat_postMessage(
                channel=event.get("channel"),
                thread_ts=event.get("ts"),
                text=(
                    f":information_source: {error}\n"
                    "Example: `@Incident Commander checkout-service latency spike`"
                ),
            )
            return

        thread = threading.Thread(
            target=_start_channel_investigation,
            kwargs={
                "client": client,
                "settings": settings,
                "service": service,
                "description": description,
                "thread_ts": event.get("ts"),
            },
            name=f"mention-investigation-{service}",
            daemon=True,
        )
        thread.start()
