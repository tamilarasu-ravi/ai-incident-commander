"""Evaluation result models and confidence scoring."""

from pydantic import BaseModel, Field

from ai_incident_commander.constants import (
    CONFIDENCE_WEIGHT_CONSISTENCY,
    CONFIDENCE_WEIGHT_EVIDENCE,
    CONFIDENCE_WEIGHT_GROUNDING,
)


def compute_confidence(
    evidence_coverage: float,
    grounding_score: float,
    consistency: float,
) -> float:
    """
    Compute deterministic confidence from eval component scores.

    Args:
        evidence_coverage: Float in ``[0.0, 1.0]`` measuring evidence breadth.
        grounding_score: Float in ``[0.0, 1.0]`` measuring grounding verdict.
        consistency: Float in ``[0.0, 1.0]`` measuring dual-run consistency.

    Returns:
        Confidence float in ``[0.0, 1.0]``.
    """
    return (
        evidence_coverage * CONFIDENCE_WEIGHT_EVIDENCE
        + grounding_score * CONFIDENCE_WEIGHT_GROUNDING
        + consistency * CONFIDENCE_WEIGHT_CONSISTENCY
    )


class EvalResult(BaseModel):
    """Combined evaluation outcome for an RCA hypothesis."""

    evidence_coverage: float = Field(ge=0.0, le=1.0)
    grounding_score: float = Field(ge=0.0, le=1.0)
    consistency: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    blocked: bool = False
    block_reason: str = ""

    @classmethod
    def from_component_scores(
        cls,
        evidence_coverage: float,
        grounding_score: float,
        consistency: float,
        *,
        blocked: bool = False,
        block_reason: str = "",
    ) -> "EvalResult":
        """
        Build an eval result with confidence derived from component scores.

        Args:
            evidence_coverage: Evidence coverage score in ``[0.0, 1.0]``.
            grounding_score: Grounding score in ``[0.0, 1.0]``.
            consistency: Consistency score in ``[0.0, 1.0]``.
            blocked: Whether the RCA was blocked from surfacing.
            block_reason: Human-readable reason when blocked.

        Returns:
            ``EvalResult`` with computed confidence.
        """
        confidence = compute_confidence(
            evidence_coverage,
            grounding_score,
            consistency,
        )
        return cls(
            evidence_coverage=evidence_coverage,
            grounding_score=grounding_score,
            consistency=consistency,
            confidence=confidence,
            blocked=blocked,
            block_reason=block_reason,
        )
