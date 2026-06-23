"""Shared helpers for running investigations and posting Slack results."""

import asyncio

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
        response = client.chat_postMessage(
            channel=channel_id,
            text=build_rca_fallback_text(final_state),
            blocks=build_rca_approval_blocks(final_state),
        )
        investigation_id = final_state.get("investigation_id")
        message_ts = response.get("ts") if response else None
        if investigation_id and message_ts:
            get_investigation_store().save(
                investigation_id=investigation_id,
                state=final_state,
                channel_id=channel_id,
                message_ts=message_ts,
            )
        return final_state

    client.chat_postMessage(
        channel=channel_id,
        text=(
            f":warning: Investigation for `{service}` ended in unexpected "
            f"status `{status}`."
        ),
    )
    return final_state
