"""Deterministic false-alarm detection for test-only incident evidence."""

from ai_incident_commander.models.evidence import EvidenceBundle
from ai_incident_commander.models.rca import RcaHypothesis

FALSE_ALARM_DESCRIPTION_PATTERNS = (
    "flaky",
    "test failure",
    "false alarm",
    "integration test",
    "failed test",
    "flaky test",
)

TEST_LOG_MARKERS = (
    "integration test",
    "test retry",
    "test failed",
    "failed test",
    "test suite",
    "spec failed",
)

TEST_COMMIT_MARKERS = (
    "test",
    "flaky",
    "spec",
    "suite",
)

PRODUCTION_DESCRIPTION_TERMS = (
    "replication",
    "database",
    "postgres",
    "postgresql",
    "db lag",
    "connection pool",
    "outage",
)


def assess_false_alarm(
    evidence: EvidenceBundle,
    description: str,
    rca: RcaHypothesis,
) -> tuple[bool, str]:
    """
    Detect investigations that should be blocked before human approval.

    Blocks two live-demo cases for auth-service:
    - Test-only evidence with a flaky-test style alert (false alarm)
    - Alert claims a production cause that does not appear anywhere in evidence

    Args:
        evidence: Collected investigation evidence.
        description: Incident description from the trigger.
        rca: Synthesized RCA hypothesis.

    Returns:
        Tuple of whether to block and a human-readable block reason.
    """
    if is_test_only_evidence(evidence) and description_signals_false_alarm(description):
        return (
            True,
            "Flaky test false alarm: evidence only shows test retries, not a production incident.",
        )

    mismatch, mismatch_reason = description_claims_production_without_evidence(
        description,
        evidence,
        rca,
    )
    if mismatch:
        return True, mismatch_reason

    return False, ""


def is_test_only_evidence(evidence: EvidenceBundle) -> bool:
    """
    Return True when evidence contains only test-related signals.

    Args:
        evidence: Collected investigation evidence.

    Returns:
        Whether the bundle looks like CI/test noise rather than production impact.
    """
    if evidence.has_prior_incident_or_deployment():
        return False
    if not evidence.log_clusters:
        return False

    for cluster in evidence.log_clusters:
        if not _is_test_log_message(cluster.message):
            return False

    for commit in evidence.commits:
        combined = f"{commit.message} {commit.sha}".lower()
        if not any(marker in combined for marker in TEST_COMMIT_MARKERS):
            return False

    return True


def description_signals_false_alarm(description: str) -> bool:
    """
    Return True when the alert description indicates a flaky-test investigation.

    Args:
        description: Incident description from the trigger.

    Returns:
        Whether the description matches false-alarm language.
    """
    lowered = description.lower()
    return any(pattern in lowered for pattern in FALSE_ALARM_DESCRIPTION_PATTERNS)


def description_claims_production_without_evidence(
    description: str,
    evidence: EvidenceBundle,
    rca: RcaHypothesis,
) -> tuple[bool, str]:
    """
    Return True when the alert or RCA cites production failure terms missing from evidence.

    Args:
        description: Incident description from the trigger.
        evidence: Collected investigation evidence.
        rca: Synthesized RCA hypothesis.

    Returns:
        Tuple of whether to block and an explanation string.
    """
    description_terms = _find_production_terms(description)
    rca_terms = _find_production_terms(rca.root_cause_candidate)
    claimed_terms = _merge_terms(description_terms, rca_terms)
    if not claimed_terms:
        return False, ""

    evidence_text = _evidence_corpus(evidence).lower()
    missing_terms = [term for term in claimed_terms if term not in evidence_text]
    if not missing_terms:
        return False, ""

    primary = missing_terms[0].replace("_", " ")
    return (
        True,
        "RCA is not grounded in collected evidence: "
        f"alert or hypothesis cites {primary} but collected evidence contains no matching production signals.",
    )


def _merge_terms(primary: list[str], secondary: list[str]) -> list[str]:
    """Merge production term lists while preserving first-seen order."""
    merged: list[str] = []
    for term in [*primary, *secondary]:
        if term not in merged:
            merged.append(term)
    return merged


def _is_test_log_message(message: str) -> bool:
    """Return True when a log cluster message appears test-related."""
    lowered = message.lower()
    return any(marker in lowered for marker in TEST_LOG_MARKERS) or " test " in f" {lowered} "


def _find_production_terms(text: str) -> list[str]:
    """Extract production-incident terms present in free text."""
    lowered = text.lower()
    return [term for term in PRODUCTION_DESCRIPTION_TERMS if term in lowered]


def _evidence_corpus(evidence: EvidenceBundle) -> str:
    """Concatenate evidence fields into a single searchable string."""
    parts: list[str] = []
    for commit in evidence.commits:
        parts.extend([commit.sha, commit.message, commit.author])
    for cluster in evidence.log_clusters:
        parts.append(cluster.message)
    for incident in evidence.prior_incidents:
        parts.extend([incident.incident_id, incident.summary])
    for deployment in evidence.deployments:
        parts.extend([deployment.deployment_id, deployment.environment])
    return " ".join(parts)
