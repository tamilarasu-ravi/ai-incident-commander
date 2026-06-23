"""Block Kit views for RCA approval cards."""

from typing import Any

from ai_incident_commander.models.eval_result import EvalResult
from ai_incident_commander.models.evidence import EvidenceBundle
from ai_incident_commander.models.investigation import InvestigationState
from ai_incident_commander.models.rca import RcaHypothesis

ACTION_APPROVE = "approve_rca"
ACTION_REJECT = "reject_rca"
ACTION_SHOW_EVIDENCE = "show_evidence"


def _format_percent(score: float) -> str:
    """
    Format a float score as a whole-number percentage string.

    Args:
        score: Score in ``[0.0, 1.0]``.

    Returns:
        Percentage string such as ``87%``.
    """
    return f"{round(score * 100)}%"


def _confidence_bar(score: float) -> str:
    """
    Render a simple text confidence bar for Slack mrkdwn.

    Args:
        score: Score in ``[0.0, 1.0]``.

    Returns:
        Ten-character bar using filled and empty block characters.
    """
    filled = round(score * 10)
    return "█" * filled + "░" * (10 - filled)


def build_evidence_summary(evidence: EvidenceBundle) -> str:
    """
    Build a one-line evidence summary for the RCA card.

    Args:
        evidence: Collected evidence bundle.

    Returns:
        Slack mrkdwn summary line.
    """
    return (
        f"{len(evidence.commits)} recent commits · "
        f"{len(evidence.log_clusters)} error log clusters · "
        f"{len(evidence.prior_incidents)} prior incident match"
    )


def build_rca_approval_blocks(
    state: InvestigationState,
) -> list[dict[str, Any]]:
    """
    Build Block Kit blocks for a surfaced RCA approval card.

    Args:
        state: Completed investigation state with RCA and eval results.

    Returns:
        List of Slack Block Kit block dictionaries.

    Raises:
        ValueError: If required RCA, evidence, or eval fields are missing.
    """
    rca = state.get("rca")
    evidence = state.get("evidence")
    eval_result = state.get("eval_result")
    if rca is None or evidence is None or eval_result is None:
        raise ValueError("surfaced investigations require rca, evidence, and eval_result")

    return _build_card_blocks(
        investigation_id=state.get("investigation_id", ""),
        service=state["service"],
        description=state["description"],
        rca=rca,
        evidence=evidence,
        eval_result=eval_result,
    )


def build_blocked_message_text(state: InvestigationState) -> str:
    """
    Build a plain-text Slack message when an investigation is blocked.

    Args:
        state: Blocked investigation state.

    Returns:
        Slack mrkdwn message describing the block reason.
    """
    reason = state.get("block_reason") or state.get("error_message") or "Unknown reason."
    return (
        f":no_entry: *Investigation blocked for `{state['service']}`*\n"
        f"{reason}"
    )


def build_error_message_text(state: InvestigationState) -> str:
    """
    Build a plain-text Slack message when the pipeline errors early.

    Args:
        state: Errored investigation state.

    Returns:
        Slack mrkdwn error message.
    """
    message = state.get("error_message") or "Investigation failed."
    return f":warning: *Investigation error for `{state['service']}`*\n{message}"


def _build_card_blocks(
    investigation_id: str,
    service: str,
    description: str,
    rca: RcaHypothesis,
    evidence: EvidenceBundle,
    eval_result: EvalResult,
) -> list[dict[str, Any]]:
    """
    Build Block Kit blocks for RCA approval UI components.

    Args:
        investigation_id: Unique investigation identifier for action metadata.
        service: Affected service name.
        description: Incident description from trigger.
        rca: Synthesized RCA hypothesis.
        evidence: Evidence bundle shown in summary.
        eval_result: Evaluation scores for confidence display.

    Returns:
        List of Slack Block Kit block dictionaries.
    """
    prior_match = rca.prior_incident_match or "none"
    confidence_pct = _format_percent(eval_result.confidence)

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"RCA Ready: {service}",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Description:* {description}\n"
                    f"*Root Cause Candidate:* {rca.root_cause_candidate}\n"
                    f"*Supporting Commit:* `{rca.supporting_commit}` "
                    f"({rca.commit_age_minutes} min ago)\n"
                    f"*Prior Incident Match:* `{prior_match}`"
                ),
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Confidence Score:* {confidence_pct}\n"
                    f"Evidence: `{_confidence_bar(eval_result.evidence_coverage)}` "
                    f"{_format_percent(eval_result.evidence_coverage)}\n"
                    f"Grounding: `{_confidence_bar(eval_result.grounding_score)}` "
                    f"{_format_percent(eval_result.grounding_score)}\n"
                    f"Consistency: `{_confidence_bar(eval_result.consistency)}` "
                    f"{_format_percent(eval_result.consistency)}"
                ),
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"*Evidence collected:* {build_evidence_summary(evidence)}",
                }
            ],
        },
        {"type": "divider"},
        {
            "type": "actions",
            "block_id": "rca_approval_actions",
            "elements": [
                {
                    "type": "button",
                    "action_id": ACTION_APPROVE,
                    "text": {"type": "plain_text", "text": "Approve & Create Jira"},
                    "style": "primary",
                    "value": investigation_id,
                },
                {
                    "type": "button",
                    "action_id": ACTION_REJECT,
                    "text": {"type": "plain_text", "text": "Reject"},
                    "style": "danger",
                    "value": investigation_id,
                },
                {
                    "type": "button",
                    "action_id": ACTION_SHOW_EVIDENCE,
                    "text": {"type": "plain_text", "text": "Show Evidence"},
                    "value": investigation_id,
                },
            ],
        },
    ]
    return blocks


def build_rca_fallback_text(state: InvestigationState) -> str:
    """
    Build fallback notification text for Slack clients without blocks.

    Args:
        state: Surfaced investigation state.

    Returns:
        Plain summary string for the ``text`` field on ``chat.postMessage``.
    """
    rca = state.get("rca")
    eval_result = state.get("eval_result")
    if rca is None or eval_result is None:
        return f"RCA investigation complete for {state['service']}"

    return (
        f"RCA Ready: {state['service']} — "
        f"{rca.root_cause_candidate} "
        f"(confidence {_format_percent(eval_result.confidence)})"
    )
