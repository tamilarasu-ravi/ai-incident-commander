"""PagerDuty webhook route for automatic incident investigation."""

import json
import threading

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ai_incident_commander.config import Settings, get_settings
from ai_incident_commander.constants import INVESTIGATION_ANNOUNCEMENT_TEMPLATE
from ai_incident_commander.server.pagerduty_security import (
    PAGERDUTY_SIGNATURE_HEADER,
    extract_pagerduty_event_id,
    is_duplicate_pagerduty_event,
    verify_pagerduty_signature,
)
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
async def pagerduty_webhook(request: Request) -> PagerDutyWebhookResponse:
    """
    Accept a PagerDuty incident webhook and start an investigation.

    Args:
        request: Raw HTTP request with PagerDuty JSON body.

    Returns:
        Accepted status with parsed service and description.

    Raises:
        HTTPException: If the payload cannot be parsed, signature fails, or Slack is not configured.
    """
    settings = get_settings()
    if not settings.incidents_channel_id:
        raise HTTPException(status_code=503, detail="INCIDENTS_CHANNEL_ID is not configured")

    raw_body = await request.body()
    if settings.pagerduty_webhook_secret:
        signature_header = request.headers.get(PAGERDUTY_SIGNATURE_HEADER, "")
        if not verify_pagerduty_signature(
            raw_body,
            settings.pagerduty_webhook_secret,
            signature_header,
        ):
            raise HTTPException(status_code=401, detail="Invalid PagerDuty signature")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from error

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="PagerDuty payload must be a JSON object")

    event_id = extract_pagerduty_event_id(payload)
    if is_duplicate_pagerduty_event(event_id):
        try:
            service, description = parse_pagerduty_payload(payload)
        except ValueError:
            service, description = "unknown-service", "duplicate event"
        return PagerDutyWebhookResponse(
            status="duplicate",
            service=service,
            description=description,
        )

    try:
        service, description = parse_pagerduty_payload(payload)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    thread = threading.Thread(
        target=_run_pagerduty_investigation,
        args=(service, description, settings),
        name=f"pagerduty-{event_id or service}",
        daemon=True,
    )
    thread.start()
    return PagerDutyWebhookResponse(service=service, description=description)
