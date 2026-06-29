"""Slash command handlers for incident escalation."""

import os
import threading

import structlog
from slack_bolt import App
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from ai_incident_commander.config import Settings
from ai_incident_commander.constants import INCIDENT_SLASH_COMMAND
from ai_incident_commander.slack.incident_parse import (
    IncidentCommandParseError,
    build_investigation_message,
    parse_incident_command,
)
from ai_incident_commander.slack.investigation_runner import post_investigation_result

logger = structlog.get_logger(__name__)


def _post_investigation_result(
    client: WebClient,
    channel_id: str,
    service: str,
    description: str,
    settings: Settings,
) -> None:
    """
    Run the investigation graph and post the resulting Slack message.

    Args:
        client: Slack Web API client.
        channel_id: Target incidents channel ID.
        service: Affected service name.
        description: Incident description.
        settings: Application settings for LLM configuration.
    """
    post_investigation_result(
        client=client,
        channel_id=channel_id,
        service=service,
        description=description,
        settings=settings,
    )


def register_slash_handlers(app: App, settings: Settings) -> None:
    """
    Register slash command handlers on the Bolt application.

    Args:
        app: Configured Bolt ``App`` instance.
        settings: Application settings containing channel and token configuration.
    """

    @app.command(INCIDENT_SLASH_COMMAND)
    def handle_incident_command(
        ack,
        command,
        client: WebClient,
        respond,
    ) -> None:
        """
        Acknowledge `/incident`, announce, and run the investigation graph.

        Args:
            ack: Bolt ack function — must be called within three seconds.
            command: Slash command payload from Slack.
            client: Slack Web API client for posting channel messages.
            respond: Bolt respond utility for ephemeral user feedback.

        Raises:
            Does not raise — parse and API errors are returned to the user in Slack.
        """
        ack()
        log = logger.bind(pid=os.getpid())
        log.info(
            "slash_command_received",
            command=command.get("command"),
            text=command.get("text", ""),
        )

        if not settings.incidents_channel_id:
            respond(
                response_type="ephemeral",
                text=(
                    "INCIDENTS_CHANNEL_ID is not configured. "
                    "Set it in `.env` and restart the app."
                ),
            )
            return

        try:
            service, description = parse_incident_command(command.get("text", ""))
        except IncidentCommandParseError as error:
            respond(response_type="ephemeral", text=str(error))
            return

        message = build_investigation_message(service, description)

        try:
            client.chat_postMessage(
                channel=settings.incidents_channel_id,
                text=message,
                mrkdwn=True,
            )
        except SlackApiError:
            respond(
                response_type="ephemeral",
                text=(
                    "Failed to post to #incidents. "
                    "Ensure the bot is invited to the channel and "
                    "INCIDENTS_CHANNEL_ID is correct."
                ),
            )
            return

        thread = threading.Thread(
            target=_post_investigation_result,
            args=(
                client,
                settings.incidents_channel_id,
                service,
                description,
                settings,
            ),
            name=f"investigation-{service}",
            daemon=True,
        )
        thread.start()

        respond(
            response_type="ephemeral",
            text=(
                f"Investigation started in <#{settings.incidents_channel_id}>. "
                "RCA card will appear when analysis completes.\n\n"
                "_Tip: open the Incident Commander Assistant for Real-Time Search._"
            ),
        )
