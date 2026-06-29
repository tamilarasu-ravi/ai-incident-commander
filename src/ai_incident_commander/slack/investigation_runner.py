"""Shared helpers for running investigations and posting Slack results."""

import os

import structlog
from slack_sdk import WebClient

from ai_incident_commander.agents.graph import run_investigation
from ai_incident_commander.db.async_bridge import run_async
from ai_incident_commander.config import Settings
from ai_incident_commander.slack.action_token_store import get_action_token, get_most_recent_action_token
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
    action_token: str | None = None,
    assistant_thread: tuple[str, str] | None = None,
) -> InvestigationState | None:
    """
    Run the investigation graph and post the resulting Slack message.

    Args:
        client: Slack Web API client.
        channel_id: Target incidents channel ID.
        service: Affected service name.
        description: Incident description.
        settings: Application settings for LLM and integrations.
        action_token: Optional RTS token from an Assistant thread (enables primary RTS path).
        assistant_thread: Optional ``(channel_id, thread_ts)`` for Assistant follow-up.

    Returns:
        Final investigation state when the graph completes, otherwise ``None``.
    """
    log = logger.bind(service=service, pid=os.getpid())
    log.info("investigation_started", rts_token_provided=bool(action_token))

    try:
        resolved_token = (
            action_token
            or get_action_token(channel_id)
            or get_most_recent_action_token()
        )
        final_state = run_async(
            run_investigation(
                service=service,
                description=description,
                settings=settings,
                action_token=resolved_token,
            )
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
        _post_assistant_follow_up(client, assistant_thread, final_state, channel_id)
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

        show_server_pid = settings.log_level.lower() == "debug"
        response = client.chat_postMessage(
            channel=channel_id,
            text=build_rca_fallback_text(final_state),
            blocks=build_rca_approval_blocks(
                final_state,
                server_pid=os.getpid() if show_server_pid else None,
            ),
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
        _post_assistant_follow_up(client, assistant_thread, final_state, channel_id)
        return final_state

    client.chat_postMessage(
        channel=channel_id,
        text=(
            f":warning: Investigation for `{service}` ended in unexpected "
            f"status `{status}`."
        ),
    )
    return final_state


def _post_assistant_follow_up(
    client: WebClient,
    assistant_thread: tuple[str, str] | None,
    state: InvestigationState,
    incidents_channel_id: str,
) -> None:
    """
    Post a short investigation summary back to the Assistant thread.

    Args:
        client: Slack Web API client.
        assistant_thread: ``(channel_id, thread_ts)`` when triggered from Assistant.
        state: Final investigation state after the graph completes.
        incidents_channel_id: Channel where the full RCA card was posted.
    """
    if assistant_thread is None:
        return

    assistant_channel_id, thread_ts = assistant_thread
    if not assistant_channel_id or not thread_ts:
        return

    status = state.get("status")
    eval_result = state.get("eval_result")
    service = state.get("service", "service")

    if status == "surfaced" and eval_result is not None:
        confidence_pct = int(round(eval_result.confidence * 100))
        text = (
            f":white_check_mark: Investigation complete for `{service}` — "
            f"confidence *{confidence_pct}%*. "
            f"Review the approval card in <#{incidents_channel_id}>."
        )
    elif status == "blocked":
        reason = state.get("block_reason") or (
            eval_result.block_reason if eval_result else "Investigation blocked."
        )
        text = (
            f":no_entry: Investigation blocked for `{service}`: {reason}\n"
            f"Details posted in <#{incidents_channel_id}>."
        )
    else:
        return

    try:
        client.chat_postMessage(
            channel=assistant_channel_id,
            thread_ts=thread_ts,
            text=text,
        )
    except Exception:
        logger.warning(
            "assistant_follow_up_failed",
            assistant_channel_id=assistant_channel_id,
            thread_ts=thread_ts,
        )
