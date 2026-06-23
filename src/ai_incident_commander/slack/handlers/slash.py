"""Slash command handlers for incident escalation."""

import asyncio
import threading

from slack_bolt import App
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from ai_incident_commander.agents.graph import run_investigation
from ai_incident_commander.config import Settings
from ai_incident_commander.constants import (
    INCIDENT_SLASH_COMMAND,
    INCIDENT_USAGE_HINT,
    INVESTIGATION_ANNOUNCEMENT_TEMPLATE,
)
from ai_incident_commander.slack.views.approval import (
    build_blocked_message_text,
    build_error_message_text,
    build_rca_approval_blocks,
    build_rca_fallback_text,
)


class IncidentCommandParseError(ValueError):
    """Raised when `/incident` command text is missing required parts."""


def parse_incident_command(text: str) -> tuple[str, str]:
    """
    Parse slash command text into a service name and incident description.

    Args:
        text: Payload text after the command name (e.g. ``checkout-service latency spike``).

    Returns:
        Tuple of ``(service, description)``.

    Raises:
        IncidentCommandParseError: If either service or description is missing.
    """
    normalized = text.strip()
    if not normalized:
        raise IncidentCommandParseError(
            f"Missing arguments. Usage: {INCIDENT_USAGE_HINT}"
        )

    parts = normalized.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        raise IncidentCommandParseError(
            f"Description is required. Usage: {INCIDENT_USAGE_HINT}"
        )

    service = parts[0].strip()
    description = parts[1].strip()
    if not service:
        raise IncidentCommandParseError(
            f"Service name is required. Usage: {INCIDENT_USAGE_HINT}"
        )

    return service, description


def build_investigation_message(service: str, description: str) -> str:
    """
    Build the announcement message posted to the incidents channel.

    Args:
        service: Affected service name from the slash command.
        description: Free-text incident description from the slash command.

    Returns:
        Slack mrkdwn-formatted investigation announcement.
    """
    return INVESTIGATION_ANNOUNCEMENT_TEMPLATE.format(
        service=service,
        description=description,
    )


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
    try:
        final_state = asyncio.run(
            run_investigation(service=service, description=description, settings=settings)
        )
    except Exception:
        client.chat_postMessage(
            channel=channel_id,
            text=(
                f":warning: Investigation failed for `{service}`. "
                "Check application logs for details."
            ),
        )
        return

    status = final_state.get("status")
    if status == "error":
        client.chat_postMessage(
            channel=channel_id,
            text=build_error_message_text(final_state),
        )
        return

    if status == "blocked":
        client.chat_postMessage(
            channel=channel_id,
            text=build_blocked_message_text(final_state),
        )
        return

    if status == "surfaced":
        client.chat_postMessage(
            channel=channel_id,
            text=build_rca_fallback_text(final_state),
            blocks=build_rca_approval_blocks(final_state),
        )
        return

    client.chat_postMessage(
        channel=channel_id,
        text=(
            f":warning: Investigation for `{service}` ended in unexpected "
            f"status `{status}`."
        ),
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
                "RCA card will appear when analysis completes."
            ),
        )
