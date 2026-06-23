"""Tests for Block Kit RCA approval views."""

import pytest

from ai_incident_commander.models.eval_result import EvalResult
from ai_incident_commander.models.investigation import InvestigationState
from ai_incident_commander.models.rca import RcaHypothesis
from ai_incident_commander.slack.views.approval import (
    ACTION_APPROVE,
    ACTION_REJECT,
    ACTION_SHOW_EVIDENCE,
    build_blocked_message_text,
    build_evidence_summary,
    build_rca_approval_blocks,
)
from tests.fixtures import REDIS_POOL_EXHAUSTION_BUNDLE, REDIS_POOL_STUB_EVAL


@pytest.fixture
def surfaced_state() -> InvestigationState:
    """Investigation state ready for RCA surfacing."""
    return InvestigationState(
        investigation_id="inv-123",
        service="checkout-service",
        description="latency spike",
        evidence=REDIS_POOL_EXHAUSTION_BUNDLE,
        rca=RcaHypothesis(
            root_cause_candidate="Redis connection pool exhaustion",
            supporting_commit="abc123",
            commit_age_minutes=14,
            affected_service="checkout-service",
            prior_incident_match="SCRUM-1",
        ),
        eval_result=REDIS_POOL_STUB_EVAL,
        status="surfaced",
    )


def test_build_evidence_summary_formats_counts() -> None:
    """Evidence summary includes commit, log, and prior incident counts."""
    summary = build_evidence_summary(REDIS_POOL_EXHAUSTION_BUNDLE)
    assert "4 recent commits" in summary
    assert "3 error log clusters" in summary
    assert "1 prior incident match" in summary


def test_build_rca_approval_blocks_contains_actions(surfaced_state: InvestigationState) -> None:
    """RCA card includes approve, reject, and show evidence buttons."""
    blocks = build_rca_approval_blocks(surfaced_state)
    action_block = next(block for block in blocks if block["type"] == "actions")
    action_ids = {element["action_id"] for element in action_block["elements"]}
    assert action_ids == {ACTION_APPROVE, ACTION_REJECT, ACTION_SHOW_EVIDENCE}


def test_build_rca_approval_blocks_shows_confidence(surfaced_state: InvestigationState) -> None:
    """RCA card displays confidence percentage."""
    blocks = build_rca_approval_blocks(surfaced_state)
    section_text = " ".join(
        block["text"]["text"]
        for block in blocks
        if block.get("type") == "section" and "text" in block
    )
    assert "87%" in section_text
    assert "Redis connection pool exhaustion" in section_text


def test_build_blocked_message_text_includes_reason() -> None:
    """Blocked message surfaces the block reason to the channel."""
    state = InvestigationState(
        service="checkout-service",
        description="latency spike",
        status="blocked",
        block_reason="Blocked by Eval 1",
    )
    message = build_blocked_message_text(state)
    assert "blocked" in message.lower()
    assert "Blocked by Eval 1" in message
