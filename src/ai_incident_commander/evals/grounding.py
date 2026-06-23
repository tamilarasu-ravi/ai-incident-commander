"""Eval 2 — LLM grounding validation."""

from ai_incident_commander.config import Settings
from ai_incident_commander.llm.adapter import validate_rca_grounding
from ai_incident_commander.models.evidence import EvidenceBundle
from ai_incident_commander.models.grounding import GroundingVerdict
from ai_incident_commander.models.rca import RcaHypothesis


async def check_grounding(
    evidence: EvidenceBundle,
    rca: RcaHypothesis,
    settings: Settings | None = None,
) -> GroundingVerdict:
    """
    Validate that the RCA root cause is grounded in collected evidence.

    Args:
        evidence: Raw evidence bundle shown to the validator.
        rca: RCA hypothesis to validate.
        settings: Optional settings override for LLM configuration.

    Returns:
        Grounding verdict with score ``1.0`` (grounded) or ``0.0`` (ungrounded).
    """
    return await validate_rca_grounding(
        evidence=evidence,
        rca=rca,
        settings=settings,
    )


__all__ = ["GroundingVerdict", "check_grounding"]
