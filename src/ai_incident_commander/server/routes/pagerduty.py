"""PagerDuty webhook route for automatic incident investigation."""

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from ai_incident_commander.config import Settings, get_settings
from ai_incident_commander.constants import INVESTIGATION_ANNOUNCEMENT_TEMPLATE
from ai_incident_commander.slack.client import create_slack_web_client
from ai_incident_commander.slack.investigation_runner import post_investigation_result

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class PagerDutyWebhookResponse(BaseModel):
    """Acknowledgement payload for accepted PagerDuty events."""

    status: str = "accepted"
    service: str
    description: str


def parse_pagerduty_payload(payload: dict) -> tuple[str, str]:
    """
    Extract service name and description from a PagerDuty webhook payload.

    Args:
        payload: Raw PagerDuty webhook JSON body.

    Returns:
        Tuple of ``(service, description)``.

    Raises:
        ValueError: If service or description cannot be determined.
    """
    event = payload.get("event") or payload
    data = event.get("data") if isinstance(event, dict) else {}
    if not isinstance(data, dict):
        data = {}

    title = (
        data.get("title")
        or data.get("summary")
        or payload.get("title")
        or "PagerDuty incident"
    )

    service = "unknown-service"
    service_obj = data.get("service")
    if isinstance(service_obj, dict):
        service = service_obj.get("summary") or service_obj.get("name") or service
    elif isinstance(service_obj, str):
        service = service_obj

    custom_details = data.get("custom_details")
    if not isinstance(custom_details, dict):
        body = data.get("body")
        if isinstance(body, dict):
            custom_details = body.get("details")
    if not isinstance(custom_details, dict):
        custom_details = {}

    service = custom_details.get("service") or custom_details.get("service_name") or service
    description = (
        custom_details.get("description")
        or custom_details.get("message")
        or title
    )

    service = str(service).strip()
    description = str(description).strip()
    if not service:
        raise ValueError("PagerDuty payload is missing a service name")
    if not description:
        raise ValueError("PagerDuty payload is missing an incident description")

    return service, description


def _run_pagerduty_investigation(
    service: str,
    description: str,
    settings: Settings,
) -> None:
    """
    Announce and investigate a PagerDuty incident in the incidents channel.

    Args:
        service: Affected service name.
        description: Incident description from PagerDuty.
        settings: Application settings.
    """
    if not settings.incidents_channel_id or not settings.slack_bot_token:
        return

    client = create_slack_web_client(settings.slack_bot_token)
    announcement = INVESTIGATION_ANNOUNCEMENT_TEMPLATE.format(
        service=service,
        description=description,
    )
    try:
        client.chat_postMessage(
            channel=settings.incidents_channel_id,
            text=announcement,
            mrkdwn=True,
        )
    except Exception:
        return

    post_investigation_result(
        client=client,
        channel_id=settings.incidents_channel_id,
        service=service,
        description=description,
        settings=settings,
    )


@router.post("/pagerduty", response_model=PagerDutyWebhookResponse)
def pagerduty_webhook(
    payload: dict,
    background_tasks: BackgroundTasks,
) -> PagerDutyWebhookResponse:
    """
    Accept a PagerDuty incident webhook and start an investigation.

    Args:
        payload: Raw PagerDuty webhook JSON body.
        background_tasks: FastAPI background task runner.

    Returns:
        Accepted status with parsed service and description.

    Raises:
        HTTPException: If the payload cannot be parsed or Slack is not configured.
    """
    settings = get_settings()
    if not settings.incidents_channel_id:
        raise HTTPException(status_code=503, detail="INCIDENTS_CHANNEL_ID is not configured")

    try:
        service, description = parse_pagerduty_payload(payload)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    background_tasks.add_task(_run_pagerduty_investigation, service, description, settings)
    return PagerDutyWebhookResponse(service=service, description=description)
