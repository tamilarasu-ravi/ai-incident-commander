"""Block Kit action handlers for RCA approval workflow."""

import asyncio
import threading

from slack_bolt import App
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from ai_incident_commander.config import Settings
from ai_incident_commander.integrations.jira import JiraClient, JiraClientError
from ai_incident_commander.slack.views.approval import (
    ACTION_APPROVE,
    ACTION_REJECT,
    ACTION_SHOW_EVIDENCE,
    build_evidence_detail_text,
    build_rca_fallback_text,
    build_rca_resolved_blocks,
)
from ai_incident_commander.store.investigations import get_investigation_store


def register_action_handlers(app: App, settings: Settings) -> None:
    """
    Register Block Kit action handlers on the Bolt application.

    Args:
        app: Configured Bolt ``App`` instance.
        settings: Application settings for Jira and Slack configuration.
    """

    @app.action(ACTION_APPROVE)
    def handle_approve(ack, body, client: WebClient, action) -> None:
        """Approve an RCA and create a Jira ticket."""
        ack()
        investigation_id = action.get("value", "")
        actor_id = body.get("user", {}).get("id", "")
        channel_id = body.get("channel", {}).get("id", "")
        message_ts = body.get("message", {}).get("ts", "")

        thread = threading.Thread(
            target=_process_approve,
            args=(client, settings, investigation_id, actor_id, channel_id, message_ts),
            name=f"approve-{investigation_id}",
            daemon=True,
        )
        thread.start()

    @app.action(ACTION_REJECT)
    def handle_reject(ack, body, client: WebClient, action) -> None:
        """Reject an RCA and disable approval buttons."""
        ack()
        investigation_id = action.get("value", "")
        actor_id = body.get("user", {}).get("id", "")
        channel_id = body.get("channel", {}).get("id", "")
        message_ts = body.get("message", {}).get("ts", "")

        thread = threading.Thread(
            target=_process_reject,
            args=(client, settings, investigation_id, actor_id, channel_id, message_ts),
            name=f"reject-{investigation_id}",
            daemon=True,
        )
        thread.start()

    @app.action(ACTION_SHOW_EVIDENCE)
    def handle_show_evidence(ack, body, client: WebClient, action) -> None:
        """Post an ephemeral evidence dump to the acting user."""
        ack()
        investigation_id = action.get("value", "")
        user_id = body.get("user", {}).get("id", "")
        channel_id = body.get("channel", {}).get("id", "")

        record = get_investigation_store().get(investigation_id)
        if record is None:
            _post_ephemeral(client, channel_id, user_id, "Investigation not found or expired.")
            return

        try:
            text = build_evidence_detail_text(record.state)
        except ValueError as error:
            _post_ephemeral(client, channel_id, user_id, str(error))
            return

        _post_ephemeral(client, channel_id, user_id, text)


def _process_approve(
    client: WebClient,
    settings: Settings,
    investigation_id: str,
    actor_id: str,
    channel_id: str,
    message_ts: str,
) -> None:
    """Create a Jira ticket and update the RCA card after approval."""
    store = get_investigation_store()
    record = store.get(investigation_id)
    if record is None:
        _post_ephemeral(client, channel_id, actor_id, "Investigation not found or expired.")
        return

    if record.approval_status != "pending":
        _post_ephemeral(
            client,
            channel_id,
            actor_id,
            f"This investigation was already {record.approval_status}.",
        )
        return

    try:
        issue_key = asyncio.run(JiraClient(settings).create_incident_ticket(record.state))
    except (JiraClientError, ValueError) as error:
        _post_ephemeral(
            client,
            channel_id,
            actor_id,
            f"Failed to create Jira ticket: {error}",
        )
        return

    store.mark_approved(investigation_id, issue_key)
    _update_resolved_card(
        client=client,
        settings=settings,
        state=record.state,
        channel_id=record.channel_id or channel_id,
        message_ts=record.message_ts or message_ts,
        resolution="Approved",
        actor_id=actor_id,
        jira_issue_key=issue_key,
    )


def _process_reject(
    client: WebClient,
    settings: Settings,
    investigation_id: str,
    actor_id: str,
    channel_id: str,
    message_ts: str,
) -> None:
    """Mark an investigation rejected and update the RCA card."""
    store = get_investigation_store()
    record = store.get(investigation_id)
    if record is None:
        _post_ephemeral(client, channel_id, actor_id, "Investigation not found or expired.")
        return

    if record.approval_status != "pending":
        _post_ephemeral(
            client,
            channel_id,
            actor_id,
            f"This investigation was already {record.approval_status}.",
        )
        return

    store.mark_rejected(investigation_id)
    _update_resolved_card(
        client=client,
        settings=settings,
        state=record.state,
        channel_id=record.channel_id or channel_id,
        message_ts=record.message_ts or message_ts,
        resolution="Rejected",
        actor_id=actor_id,
    )


def _update_resolved_card(
    client: WebClient,
    settings: Settings,
    state,
    channel_id: str,
    message_ts: str,
    resolution: str,
    actor_id: str,
    jira_issue_key: str | None = None,
) -> None:
    """Replace an RCA card with a resolved version without action buttons."""
    try:
        client.chat_update(
            channel=channel_id,
            ts=message_ts,
            text=build_rca_fallback_text(state),
            blocks=build_rca_resolved_blocks(
                state,
                resolution=resolution,
                actor_id=actor_id,
                jira_issue_key=jira_issue_key,
                jira_base_url=settings.jira_base_url.rstrip("/"),
            ),
        )
    except SlackApiError:
        return


def _post_ephemeral(
    client: WebClient,
    channel_id: str,
    user_id: str,
    text: str,
) -> None:
    """Post an ephemeral Slack message when available."""
    if not channel_id or not user_id:
        return
    try:
        client.chat_postEphemeral(channel=channel_id, user=user_id, text=text)
    except SlackApiError:
        return
