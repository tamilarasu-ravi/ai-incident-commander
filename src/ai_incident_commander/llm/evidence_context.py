"""Prepare and compact investigation evidence for LLM prompts."""

from __future__ import annotations

from ai_incident_commander.constants import (
    CHARS_PER_TOKEN_ESTIMATE,
    EVIDENCE_FIELD_MAX_CHARS,
    EVIDENCE_PROMPT_TOKEN_BUDGET,
)
from ai_incident_commander.models.evidence import (
    CommitEvidence,
    DeploymentEvidence,
    EvidenceBundle,
    LogClusterEvidence,
    PriorIncidentEvidence,
)

EvidencePromptMode = str  # "full" | "summary"


def truncate_text(value: str, max_chars: int = EVIDENCE_FIELD_MAX_CHARS) -> str:
    """
    Truncate a string to a maximum length with an ellipsis suffix.

    Args:
        value: Raw text to truncate.
        max_chars: Maximum allowed characters.

    Returns:
        Truncated string, or the original when within the limit.
    """
    text = value.strip()
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return f"{text[: max_chars - 3]}..."


def truncate_evidence_bundle(
    evidence: EvidenceBundle,
    max_chars: int = EVIDENCE_FIELD_MAX_CHARS,
) -> EvidenceBundle:
    """
    Truncate long free-text fields inside an evidence bundle.

    Args:
        evidence: Collected investigation evidence.
        max_chars: Maximum characters for free-text evidence fields.

    Returns:
        New bundle with commit messages, log lines, and summaries capped.
    """
    return EvidenceBundle(
        commits=[
            CommitEvidence(
                sha=commit.sha,
                message=truncate_text(commit.message, max_chars=max_chars),
                author=truncate_text(commit.author, max_chars=min(120, max_chars)),
                age_minutes=commit.age_minutes,
                url=commit.url,
            )
            for commit in evidence.commits
        ],
        log_clusters=[
            LogClusterEvidence(
                message=truncate_text(cluster.message, max_chars=max_chars),
                count=cluster.count,
                service=cluster.service,
                status=cluster.status,
            )
            for cluster in evidence.log_clusters
        ],
        prior_incidents=[
            PriorIncidentEvidence(
                incident_id=incident.incident_id,
                summary=truncate_text(incident.summary, max_chars=max_chars),
                service=incident.service,
                resolved=incident.resolved,
            )
            for incident in evidence.prior_incidents
        ],
        deployments=[
            DeploymentEvidence(
                deployment_id=deployment.deployment_id,
                environment=deployment.environment,
                service=deployment.service,
                deployed_at_minutes_ago=deployment.deployed_at_minutes_ago,
            )
            for deployment in evidence.deployments
        ],
    )


def estimate_token_count(text: str) -> int:
    """
    Estimate token count from text length using a fixed chars-per-token ratio.

    Args:
        text: Prompt text to estimate.

    Returns:
        Estimated token count (minimum 1 for non-empty text).
    """
    if not text:
        return 0
    return max(1, len(text) // CHARS_PER_TOKEN_ESTIMATE)


def apply_token_budget(
    evidence: EvidenceBundle,
    budget: int = EVIDENCE_PROMPT_TOKEN_BUDGET,
) -> EvidenceBundle:
    """
    Shrink an evidence bundle until its JSON form fits the token budget.

    Drops lowest-priority items first: deployments, prior incidents,
    log clusters, then commits.

    Args:
        evidence: Truncated evidence bundle candidate.
        budget: Maximum estimated tokens for JSON serialization.

    Returns:
        Evidence bundle that fits the budget when possible.
    """
    bundle = truncate_evidence_bundle(evidence)
    if estimate_token_count(bundle.model_dump_json()) <= budget:
        return bundle

    working = bundle.model_copy(deep=True)
    while estimate_token_count(working.model_dump_json()) > budget:
        if working.deployments:
            working.deployments = working.deployments[:-1]
            continue
        if len(working.prior_incidents) > 1:
            working.prior_incidents = working.prior_incidents[:-1]
            continue
        if len(working.log_clusters) > 1:
            working.log_clusters = working.log_clusters[:-1]
            continue
        if len(working.commits) > 1:
            working.commits = working.commits[:-1]
            continue
        break

    field_limit = EVIDENCE_FIELD_MAX_CHARS
    while estimate_token_count(working.model_dump_json()) > budget and field_limit > 80:
        field_limit = max(field_limit // 2, 80)
        working = truncate_evidence_bundle(working, max_chars=field_limit)

    return working


def prepare_evidence_for_llm(evidence: EvidenceBundle) -> EvidenceBundle:
    """
    Apply field truncation and token-budget trimming for LLM prompts.

    Args:
        evidence: Raw collected evidence.

    Returns:
        Compact evidence bundle safe for model context windows.
    """
    return apply_token_budget(evidence)


def build_evidence_summary_text(evidence: EvidenceBundle) -> str:
    """
    Build a compact human-readable evidence summary for grounding prompts.

    Args:
        evidence: Prepared evidence bundle.

    Returns:
        Multi-line summary without full JSON payload.
    """
    lines = [
        f"Commits: {len(evidence.commits)}",
        f"Log clusters: {len(evidence.log_clusters)}",
        f"Prior incidents: {len(evidence.prior_incidents)}",
        f"Deployments: {len(evidence.deployments)}",
        "",
    ]

    if evidence.commits:
        lines.append("Recent commits:")
        for commit in evidence.commits:
            lines.append(f"- {commit.sha} ({commit.age_minutes}m ago): {commit.message}")

    if evidence.log_clusters:
        lines.append("Error log clusters:")
        for cluster in evidence.log_clusters:
            lines.append(f"- [{cluster.count}x] {cluster.message}")

    if evidence.prior_incidents:
        lines.append("Prior incidents:")
        for incident in evidence.prior_incidents:
            lines.append(f"- {incident.incident_id}: {incident.summary}")

    if evidence.deployments:
        lines.append("Deployments:")
        for deployment in evidence.deployments:
            lines.append(
                f"- {deployment.deployment_id} ({deployment.environment}, "
                f"{deployment.deployed_at_minutes_ago}m ago)"
            )

    return "\n".join(lines)


def format_evidence_for_llm(
    evidence: EvidenceBundle,
    *,
    mode: EvidencePromptMode = "full",
) -> str:
    """
    Format evidence for inclusion in an LLM user message.

    Args:
        evidence: Prepared evidence bundle.
        mode: ``full`` for JSON synthesis prompts, ``summary`` for grounding.

    Returns:
        Serialized evidence string for the prompt.
    """
    if mode == "summary":
        return build_evidence_summary_text(evidence)
    return evidence.model_dump_json(indent=2)
