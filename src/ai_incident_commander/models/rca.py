"""Root-cause analysis hypothesis models."""

from pydantic import BaseModel, Field


class RcaHypothesis(BaseModel):
    """Structured root-cause hypothesis synthesized from evidence."""

    root_cause_candidate: str = Field(
        description="Primary root cause hypothesis grounded in evidence.",
    )
    supporting_commit: str = Field(
        description="Short commit SHA that best supports the hypothesis.",
    )
    commit_age_minutes: int = Field(
        description="Age in minutes of the supporting commit.",
    )
    affected_service: str = Field(
        description="Service name affected by the incident.",
    )
    prior_incident_match: str = Field(
        default="",
        description="Prior incident ID with a similar signature, if any.",
    )
