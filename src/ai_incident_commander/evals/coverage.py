"""Eval 1 — deterministic evidence coverage scoring."""

from ai_incident_commander.models.evidence import EvidenceBundle
from ai_incident_commander.models.rca import RcaHypothesis


def score_evidence_coverage(
    evidence: EvidenceBundle,
    rca: RcaHypothesis,
) -> tuple[float, str]:
    """
    Score how well collected evidence supports the RCA hypothesis.

    Checks three equal-weight criteria:
    - RCA cites a commit present in the evidence bundle
    - At least one log cluster exists
    - At least one prior incident or deployment exists

    Args:
        evidence: Collected investigation evidence.
        rca: Synthesized RCA hypothesis.

    Returns:
        Tuple of coverage score in ``[0.0, 1.0]`` and an explanation string.
    """
    cited_commit = _rca_cites_known_commit(evidence, rca)
    has_log_cluster = evidence.has_log_cluster()
    has_prior_or_deploy = evidence.has_prior_incident_or_deployment()

    checks = [
        ("cited commit", cited_commit),
        ("log cluster", has_log_cluster),
        ("prior incident or deployment", has_prior_or_deploy),
    ]
    passed = sum(1 for _, ok in checks if ok)
    score = passed / len(checks)

    missing = [name for name, ok in checks if not ok]
    if missing:
        explanation = f"Missing evidence types: {', '.join(missing)}."
    else:
        explanation = "Evidence includes cited commit, log clusters, and prior context."

    return score, explanation


def _rca_cites_known_commit(evidence: EvidenceBundle, rca: RcaHypothesis) -> bool:
    """
    Return True when the RCA supporting commit matches evidence commit SHAs.

    Args:
        evidence: Collected investigation evidence.
        rca: Synthesized RCA hypothesis.

    Returns:
        Whether a supporting commit is present and matches evidence.
    """
    if not rca.supporting_commit or not evidence.commits:
        return False

    cited = rca.supporting_commit.lower()
    for commit in evidence.commits:
        sha = commit.sha.lower()
        if sha.startswith(cited) or cited.startswith(sha):
            return True
    return False
