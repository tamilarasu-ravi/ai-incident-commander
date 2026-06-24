"""Eval 3 — dual-run RCA consistency scoring."""

from ai_incident_commander.config import Settings
from ai_incident_commander.llm.adapter import synthesize_rca_hypothesis
from ai_incident_commander.models.evidence import EvidenceBundle
from ai_incident_commander.models.rca import RcaHypothesis


async def score_consistency(
    evidence: EvidenceBundle,
    service: str,
    description: str,
    settings: Settings | None = None,
    baseline_rca: RcaHypothesis | None = None,
) -> float:
    """
    Score RCA consistency by comparing two synthesis runs.

    When ``baseline_rca`` is provided (the graph's first synthesis at
    ``temperature=0``), only one additional synthesis is required.

    Args:
        evidence: Collected investigation evidence.
        service: Affected service name.
        description: Incident description from the trigger.
        settings: Optional settings override for LLM configuration.
        baseline_rca: RCA from the initial graph synthesis, when available.

    Returns:
        Consistency float in ``[0.0, 1.0]`` where ``1.0`` means identical root causes.
    """
    if baseline_rca is not None:
        second = await synthesize_rca_hypothesis(
            evidence=evidence,
            service=service,
            description=description,
            settings=settings,
        )
        return compare_root_causes(baseline_rca, second)

    first = await synthesize_rca_hypothesis(
        evidence=evidence,
        service=service,
        description=description,
        settings=settings,
    )
    second = await synthesize_rca_hypothesis(
        evidence=evidence,
        service=service,
        description=description,
        settings=settings,
    )
    return compare_root_causes(first, second)


def compare_root_causes(first: RcaHypothesis, second: RcaHypothesis) -> float:
    """
    Compare two RCA hypotheses and return a consistency score.

    Args:
        first: First synthesized RCA hypothesis.
        second: Second synthesized RCA hypothesis.

    Returns:
        ``1.0`` for identical normalized root causes, partial scores for overlap.
    """
    left = _normalize_root_cause(first.root_cause_candidate)
    right = _normalize_root_cause(second.root_cause_candidate)

    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if left in right or right in left:
        return 0.85

    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return 0.0

    overlap = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    return round(max(overlap, 0.0), 2)


def _normalize_root_cause(value: str) -> str:
    """
    Normalize a root-cause string for comparison.

    Args:
        value: Raw root cause candidate text.

    Returns:
        Lowercased, whitespace-collapsed string.
    """
    return " ".join(value.lower().split())
