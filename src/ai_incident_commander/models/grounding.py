"""Grounding validation result models."""

from pydantic import BaseModel, Field


class GroundingVerdict(BaseModel):
    """Structured grounding verdict from the hallucination validator."""

    grounded: bool
    grounding_score: float = Field(ge=0.0, le=1.0)
    citation: str = ""
