"""Orchestrates the three-stage RCA evaluation engine."""

import structlog

from ai_incident_commander.config import Settings
from ai_incident_commander.constants import EVIDENCE_COVERAGE_THRESHOLD
from ai_incident_commander.evals.consistency import score_consistency
from ai_incident_commander.evals.coverage import score_evidence_coverage
from ai_incident_commander.evals.false_alarm import assess_false_alarm
from ai_incident_commander.evals.grounding import check_grounding
from ai_incident_commander.models.eval_result import EvalResult
from ai_incident_commander.models.evidence import EvidenceBundle
from ai_incident_commander.models.rca import RcaHypothesis

logger = structlog.get_logger(__name__)


async def run_evaluation_engine(
    evidence: EvidenceBundle,
    rca: RcaHypothesis,
    service: str,
    description: str,
    settings: Settings | None = None,
) -> EvalResult:
    """
    Run coverage, grounding, and consistency evals before human approval.

    Eval 1 blocks when evidence coverage is below threshold.
    False-alarm guard blocks flaky-test-only investigations before grounding.
    Eval 2 blocks when the RCA is not grounded in raw evidence.
    Eval 3 penalizes confidence when dual-run synthesis diverges.

    Args:
        evidence: Collected investigation evidence.
        rca: Synthesized RCA hypothesis.
        service: Affected service name.
        description: Incident description from the trigger.
        settings: Optional settings override for LLM-backed evals.

    Returns:
        Combined ``EvalResult`` with routing metadata.
    """
    log = logger.bind(service=service)
    coverage, coverage_reason = score_evidence_coverage(evidence, rca)
    log.info("eval_coverage_completed", score=coverage)

    if coverage < EVIDENCE_COVERAGE_THRESHOLD:
        block_reason = (
            f"Evidence coverage {coverage:.0%} is below "
            f"{EVIDENCE_COVERAGE_THRESHOLD:.0%} threshold. {coverage_reason}"
        )
        return EvalResult.from_component_scores(
            evidence_coverage=coverage,
            grounding_score=0.0,
            consistency=0.0,
            blocked=True,
            block_reason=block_reason,
        )

    false_alarm, false_alarm_reason = assess_false_alarm(evidence, description, rca)
    if false_alarm:
        log.info("eval_false_alarm_blocked", reason=false_alarm_reason)
        return EvalResult.from_component_scores(
            evidence_coverage=coverage,
            grounding_score=0.0,
            consistency=0.0,
            blocked=True,
            block_reason=false_alarm_reason,
        )

    grounding = await check_grounding(evidence, rca, settings=settings)
    log.info(
        "eval_grounding_completed",
        grounded=grounding.grounded,
        score=grounding.grounding_score,
    )

    if grounding.grounding_score < 1.0:
        block_reason = (
            "RCA is not grounded in collected evidence."
            if not grounding.citation
            else f"RCA is not grounded in collected evidence: {grounding.citation}"
        )
        return EvalResult.from_component_scores(
            evidence_coverage=coverage,
            grounding_score=0.0,
            consistency=0.0,
            blocked=True,
            block_reason=block_reason,
        )

    consistency = await score_consistency(
        evidence=evidence,
        service=service,
        description=description,
        settings=settings,
    )
    log.info("eval_consistency_completed", score=consistency)

    return EvalResult.from_component_scores(
        evidence_coverage=coverage,
        grounding_score=grounding.grounding_score,
        consistency=consistency,
        blocked=False,
    )
