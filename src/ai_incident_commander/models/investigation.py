"""Investigation state model for LangGraph pipeline."""

from typing import Literal

from typing_extensions import TypedDict

from ai_incident_commander.models.eval_result import EvalResult
from ai_incident_commander.models.evidence import EvidenceBundle
from ai_incident_commander.models.rca import RcaHypothesis

InvestigationStatus = Literal[
    "pending",
    "collecting",
    "synthesizing",
    "evaluating",
    "surfaced",
    "blocked",
    "error",
]


class InvestigationState(TypedDict, total=False):
    """LangGraph state for a single incident investigation."""

    investigation_id: str
    service: str
    description: str
    evidence: EvidenceBundle | None
    rca: RcaHypothesis | None
    eval_result: EvalResult | None
    status: InvestigationStatus
    block_reason: str | None
    error_message: str | None
