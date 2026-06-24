"""Block Kit action handlers for RCA approval workflow."""

import os
import threading

import structlog
from slack_bolt import App
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from ai_incident_commander.config import Settings
from ai_incident_commander.db.async_bridge import run_async
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
from ai_incident_commander.store.types import StoredInvestigation

logger = structlog.get_logger(__name__)


def _format_store_miss_message(investigation_id: str, stored_ids: list[str]) -> str:
    """Explain why Show Evidence could not find the investigation on this server."""
    short_requested = investigation_id[:8] if investigation_id else "?"
    short_stored = [item[:8] for item in stored_ids]
    lines = [
        f"Investigation `{short_requested}` is not on this server (pid `{os.getpid()}`).",
    ]
    if short_stored:
        stored_label = ", ".join(f"`{item}`" for item in short_stored)
        lines.append(f"This server only has: {stored_label}.")
    lines.extend(
        [
            "",
            "This usually means `/incident` ran on a *different* server than the one "
            "handling button clicks. In your Slack app settings, clear the Slash Command "
            "Request URL when using Socket Mode, or point Slash Command + Interactivity "
            "URLs to the same instance.",
            "",
            "Run `/incident` again after `slack_socket_ready` in your terminal and use "
            "the newest RCA card (check *server pid* matches your terminal process).",
        ]
    )
    return "\n".join(lines)


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
        investigation_id = (action or {}).get("value", "").strip()
        if not investigation_id:
            for item in body.get("actions", []):
                if item.get("action_id") == ACTION_SHOW_EVIDENCE:
                    investigation_id = str(item.get("value", "")).strip()
                    break
        user_id = body.get("user", {}).get("id", "")
        channel_id = body.get("channel", {}).get("id", "")

        logger.info(
            "show_evidence_clicked",
            investigation_id=investigation_id or "<empty>",
            pid=os.getpid(),
        )

        store = get_investigation_store()
        record = store.get(investigation_id)
        if record is None:
            stored_ids = store.list_ids()
            logger.warning(
                "investigation_store_miss",
                investigation_id=investigation_id or "<empty>",
                stored_count=store.count(),
                stored_ids=[item[:8] for item in stored_ids],
                action=ACTION_SHOW_EVIDENCE,
                pid=os.getpid(),
            )
            _post_ephemeral(
                client,
                channel_id,
                user_id,
                _format_store_miss_message(investigation_id, stored_ids),
            )
            return

        logger.info(
            "investigation_store_hit",
            investigation_id=investigation_id,
            pid=os.getpid(),
        )

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
    try:
        record, issue_key = run_async(
            _approve_investigation(
                settings=settings,
                investigation_id=investigation_id,
                actor_id=actor_id,
            )
        )
    except (JiraClientError, ValueError) as error:
        _post_ephemeral(
            client,
            channel_id,
            actor_id,
            f"Failed to create Jira ticket: {error}",
        )
        return

    if record is None:
        _post_ephemeral(client, channel_id, actor_id, "Investigation not found or expired.")
        return

    if issue_key is None:
        _post_ephemeral(
            client,
            channel_id,
            actor_id,
            f"This investigation was already {record.approval_status}.",
        )
        return

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


async def _approve_investigation(
    settings: Settings,
    investigation_id: str,
    actor_id: str = "",
) -> tuple[StoredInvestigation | None, str | None]:
    """
    Load, approve, and persist an investigation in one background-loop turn.

    Args:
        settings: Application settings for Jira integration.
        investigation_id: Unique investigation identifier.
        actor_id: Slack user ID that approved the RCA.

    Returns:
        Tuple of ``(record, issue_key)``. ``issue_key`` is ``None`` when the
        investigation was already resolved or missing.
    """
    from ai_incident_commander.db import repository
    from ai_incident_commander.db.session import session_scope
    from ai_incident_commander.store.investigations import get_investigation_store
    from ai_incident_commander.store.postgres_store import PostgresInvestigationStore

    store = get_investigation_store()
    if isinstance(store, PostgresInvestigationStore):
        async with session_scope(store._database_url) as session:  # noqa: SLF001
            record = await repository.get_investigation(session, investigation_id)
            if record is None:
                return None, None
            if record.approval_status != "pending":
                return record, None
        issue_key = await JiraClient(settings).create_incident_ticket(record.state)
        async with session_scope(store._database_url) as session:  # noqa: SLF001
            updated = await repository.mark_approved(
                session,
                investigation_id,
                issue_key,
                actor_slack_id=actor_id,
            )
        return updated, issue_key

    record = store.get(investigation_id)
    if record is None:
        return None, None
    if record.approval_status != "pending":
        return record, None
    issue_key = await JiraClient(settings).create_incident_ticket(record.state)
    updated = store.mark_approved(investigation_id, issue_key, actor_slack_id=actor_id)
    return updated, issue_key


def _process_reject(
    client: WebClient,
    settings: Settings,
    investigation_id: str,
    actor_id: str,
    channel_id: str,
    message_ts: str,
) -> None:
    """Mark an investigation rejected and update the RCA card."""
    record, rejected = run_async(
        _reject_investigation(
            investigation_id=investigation_id,
            actor_id=actor_id,
        )
    )
    if record is None:
        _post_ephemeral(client, channel_id, actor_id, "Investigation not found or expired.")
        return

    if not rejected:
        _post_ephemeral(
            client,
            channel_id,
            actor_id,
            f"This investigation was already {record.approval_status}.",
        )
        return

    _update_resolved_card(
        client=client,
        settings=settings,
        state=record.state,
        channel_id=record.channel_id or channel_id,
        message_ts=record.message_ts or message_ts,
        resolution="Rejected",
        actor_id=actor_id,
    )


async def _reject_investigation(
    investigation_id: str,
    actor_id: str = "",
) -> tuple[StoredInvestigation | None, bool]:
    """
    Load and reject an investigation in one background-loop turn.

    Args:
        investigation_id: Unique investigation identifier.
        actor_id: Slack user ID that rejected the RCA.

    Returns:
        Tuple of ``(record, rejected_now)``. ``rejected_now`` is False when the
        investigation was already resolved or missing.
    """
    from ai_incident_commander.db import repository
    from ai_incident_commander.db.session import session_scope
    from ai_incident_commander.store.investigations import get_investigation_store
    from ai_incident_commander.store.postgres_store import PostgresInvestigationStore

    store = get_investigation_store()
    if isinstance(store, PostgresInvestigationStore):
        async with session_scope(store._database_url) as session:  # noqa: SLF001
            record = await repository.get_investigation(session, investigation_id)
            if record is None:
                return None, False
            if record.approval_status != "pending":
                return record, False
            updated = await repository.mark_rejected(
                session,
                investigation_id,
                actor_slack_id=actor_id,
            )
            return updated, updated is not None

    record = store.get(investigation_id)
    if record is None:
        return None, False
    if record.approval_status != "pending":
        return record, False
    updated = store.mark_rejected(investigation_id, actor_slack_id=actor_id)
    return updated, updated is not None


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
