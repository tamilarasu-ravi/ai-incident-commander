"""Tests for LLM evidence compaction and prompt formatting."""

from ai_incident_commander.constants import EVIDENCE_FIELD_MAX_CHARS, EVIDENCE_PROMPT_TOKEN_BUDGET
from ai_incident_commander.llm.evidence_context import (
    apply_token_budget,
    build_evidence_summary_text,
    estimate_token_count,
    format_evidence_for_llm,
    prepare_evidence_for_llm,
    truncate_evidence_bundle,
    truncate_text,
)
from ai_incident_commander.models.evidence import (
    CommitEvidence,
    DeploymentEvidence,
    EvidenceBundle,
    LogClusterEvidence,
    PriorIncidentEvidence,
)


def test_truncate_text_adds_ellipsis_for_long_values() -> None:
    """Long strings are shortened with an ellipsis suffix."""
    value = "x" * 600
    truncated = truncate_text(value, max_chars=500)
    assert len(truncated) == 500
    assert truncated.endswith("...")


def test_truncate_evidence_bundle_caps_commit_and_log_messages() -> None:
    """Evidence free-text fields are capped before LLM serialization."""
    bundle = EvidenceBundle(
        commits=[
            CommitEvidence(
                sha="abc1234",
                message="m" * 700,
                author="dev@example.com",
                age_minutes=10,
            )
        ],
        log_clusters=[
            LogClusterEvidence(
                message="e" * 700,
                count=3,
                service="checkout-service",
            )
        ],
    )

    compact = truncate_evidence_bundle(bundle)
    assert len(compact.commits[0].message) == EVIDENCE_FIELD_MAX_CHARS
    assert len(compact.log_clusters[0].message) == EVIDENCE_FIELD_MAX_CHARS


def test_apply_token_budget_drops_lowest_priority_evidence_first() -> None:
    """Token budget trimming removes deployments before commits."""
    bundle = EvidenceBundle(
        commits=[
            CommitEvidence(
                sha=f"sha{i}",
                message=f"commit-{i}",
                author="dev@example.com",
                age_minutes=i,
            )
            for i in range(5)
        ],
        log_clusters=[
            LogClusterEvidence(
                message=f"log-{i}",
                count=i + 1,
                service="checkout-service",
            )
            for i in range(5)
        ],
        prior_incidents=[
            PriorIncidentEvidence(
                incident_id=f"INC-{i}",
                summary=f"incident-{i}",
                service="checkout-service",
            )
            for i in range(5)
        ],
        deployments=[
            DeploymentEvidence(
                deployment_id=f"dep-{i}",
                environment="prod",
                service="checkout-service",
                deployed_at_minutes_ago=i,
            )
            for i in range(3)
        ],
    )

    compact = apply_token_budget(bundle, budget=80)
    assert len(compact.deployments) < len(bundle.deployments)
    assert estimate_token_count(compact.model_dump_json()) <= 80


def test_format_evidence_for_llm_summary_is_more_compact_than_full_json() -> None:
    """Grounding summary mode is smaller than full JSON evidence."""
    bundle = EvidenceBundle(
        commits=[
            CommitEvidence(
                sha="abc1234",
                message="Redis pool exhaustion",
                author="dev@example.com",
                age_minutes=12,
            )
        ],
        log_clusters=[
            LogClusterEvidence(
                message="max connections reached",
                count=8,
                service="checkout-service",
            )
        ],
    )
    prepared = prepare_evidence_for_llm(bundle)
    summary = format_evidence_for_llm(prepared, mode="summary")
    full = format_evidence_for_llm(prepared, mode="full")

    assert "Recent commits:" in summary
    assert estimate_token_count(summary) < estimate_token_count(full)


def test_build_evidence_summary_text_lists_each_evidence_section() -> None:
    """Summary text includes readable sections for each evidence type."""
    bundle = EvidenceBundle(
        commits=[
            CommitEvidence(
                sha="abc1234",
                message="fix pool",
                author="dev@example.com",
                age_minutes=5,
            )
        ],
        prior_incidents=[
            PriorIncidentEvidence(
                incident_id="INC-1",
                summary="prior outage",
                service="checkout-service",
            )
        ],
    )

    summary = build_evidence_summary_text(bundle)
    assert "Recent commits:" in summary
    assert "Prior incidents:" in summary
    assert "INC-1" in summary


def test_prepare_evidence_for_llm_respects_default_token_budget() -> None:
    """Prepared evidence stays within the configured default token budget."""
    huge_message = "z" * 2000
    bundle = EvidenceBundle(
        commits=[
            CommitEvidence(
                sha=f"sha{i}",
                message=huge_message,
                author="dev@example.com",
                age_minutes=i,
            )
            for i in range(20)
        ],
        log_clusters=[
            LogClusterEvidence(
                message=huge_message,
                count=10,
                service="checkout-service",
            )
            for _ in range(20)
        ],
    )

    prepared = prepare_evidence_for_llm(bundle)
    assert estimate_token_count(prepared.model_dump_json()) <= EVIDENCE_PROMPT_TOKEN_BUDGET
