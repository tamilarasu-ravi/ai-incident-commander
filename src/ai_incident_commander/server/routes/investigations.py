"""Read API for investigation status."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ai_incident_commander.store.investigations import get_investigation_store

router = APIRouter(prefix="/investigations", tags=["investigations"])


class InvestigationReadResponse(BaseModel):
    """Public read model for a stored investigation."""

    investigation_id: str
    status: str
    service: str
    description: str
    approval_status: str
    confidence: float | None = None
    block_reason: str | None = None
    channel_id: str | None = None
    message_ts: str | None = None
    jira_issue_key: str | None = None


@router.get("/{investigation_id}", response_model=InvestigationReadResponse)
def get_investigation(investigation_id: str) -> InvestigationReadResponse:
    """
    Return the current status of a stored investigation.

    Args:
        investigation_id: Unique investigation identifier.

    Returns:
        Investigation summary suitable for dashboards and polling clients.

    Raises:
        HTTPException: When the investigation ID is not found in the store.
    """
    store = get_investigation_store()
    record = store.get(investigation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Investigation not found")

    state = record.state
    eval_result = state.get("eval_result")
    confidence = eval_result.confidence if eval_result is not None else None

    return InvestigationReadResponse(
        investigation_id=investigation_id,
        status=str(state.get("status") or "unknown"),
        service=str(state.get("service") or ""),
        description=str(state.get("description") or ""),
        approval_status=record.approval_status,
        confidence=confidence,
        block_reason=state.get("block_reason"),
        channel_id=record.channel_id or None,
        message_ts=record.message_ts or None,
        jira_issue_key=record.jira_issue_key,
    )
