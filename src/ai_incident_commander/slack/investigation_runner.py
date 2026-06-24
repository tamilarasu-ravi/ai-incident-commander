"""Shared helpers for running investigations and posting Slack results."""

import asyncio
import os

import structlog
from slack_sdk import WebClient

from ai_incident_commander.agents.graph import run_investigation
from ai_incident_commander.config import Settings
from ai_incident_commander.models.investigation import InvestigationState
from ai_incident_commander.slack.views.approval import (
    build_blocked_message_text,
    build_error_message_text,
    build_rca_approval_blocks,
    build_rca_fallback_text,
)
from ai_incident_commander.store.investigations import get_investigation_store

logger = structlog.get_logger(__name__)


def _extract_message_ts(response: object | None) -> str | None:
    """Return the Slack message timestamp from a chat.postMessage response."""
    if response is None:
        return None
    getter = getattr(response, "get", None)
    if getter is None:
        return None
    message_ts = getter("ts")
    if message_ts:
        return str(message_ts)
    message = getter("message") or {}
    nested_ts = message.get("ts") if hasattr(message, "get") else None
    return str(nested_ts) if nested_ts else None


def post_investigation_result(
    client: WebClient,
    channel_id: str,
    service: str,
    description: str,
    settings: Settings,
) -> InvestigationState | None:
    """
    Run the investigation graph and post the resulting Slack message.

    Args:
        client: Slack Web API client.
        channel_id: Target incidents channel ID.
        service: Affected service name.
        description: Incident description.
        settings: Application settings for LLM and integrations.

    Returns:
        Final investigation state when the graph completes, otherwise ``None``.
    """
    log = logger.bind(service=service, pid=os.getpid())
    log.info("investigation_started")

    try:
        final_state = asyncio.run(
            run_investigation(service=service, description=description, settings=settings)
        )
    except Exception:
        log.exception("investigation_failed")
        client.chat_postMessage(
            channel=channel_id,
            text=(
                f":warning: Investigation failed for `{service}`. "
                "Check application logs for details."
            ),
        )
        return None

    status = final_state.get("status")
    if status == "error":
        client.chat_postMessage(
            channel=channel_id,
            text=build_error_message_text(final_state),
        )
        return final_state

    if status == "blocked":
        client.chat_postMessage(
            channel=channel_id,
            text=build_blocked_message_text(final_state),
        )
        return final_state

    if status == "surfaced":
        investigation_id = final_state.get("investigation_id")
        store = get_investigation_store()

        if investigation_id:
            store.save(
                investigation_id=investigation_id,
                state=final_state,
                channel_id=channel_id,
                message_ts="",
            )
            log.info(
                "investigation_saved_for_actions",
                investigation_id=investigation_id,
                stored_count=store.count(),
                message_ts_pending=True,
                pid=os.getpid(),
            )

        response = client.chat_postMessage(
            channel=channel_id,
            text=build_rca_fallback_text(final_state),
            blocks=build_rca_approval_blocks(final_state, server_pid=os.getpid()),
        )
        message_ts = _extract_message_ts(response)
        if investigation_id and message_ts:
            store.update_message_ts(investigation_id, message_ts)
            log.info(
                "investigation_message_ts_saved",
                investigation_id=investigation_id,
                message_ts=message_ts,
            )
        elif investigation_id:
            log.warning(
                "investigation_message_ts_missing",
                investigation_id=investigation_id,
                response_type=type(response).__name__,
            )

        log.info("investigation_surfaced", investigation_id=investigation_id, status=status, pid=os.getpid())
        return final_state

    client.chat_postMessage(
        channel=channel_id,
        text=(
            f":warning: Investigation for `{service}` ended in unexpected "
            f"status `{status}`."
        ),
    )
    return final_state
