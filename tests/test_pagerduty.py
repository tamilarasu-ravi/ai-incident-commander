"""Tests for PagerDuty webhook parsing and route."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from ai_incident_commander.server.main import api
from ai_incident_commander.server.routes.pagerduty import parse_pagerduty_payload


def test_parse_pagerduty_payload_reads_custom_details() -> None:
    """PagerDuty custom details provide service and description."""
    payload = {
        "event": {
            "data": {
                "title": "checkout-service latency spike",
                "service": {"summary": "checkout-service"},
                "custom_details": {
                    "service": "checkout-service",
                    "description": "latency spike on payment API",
                },
            }
        }
    }
    service, description = parse_pagerduty_payload(payload)
    assert service == "checkout-service"
    assert description == "latency spike on payment API"


def test_parse_pagerduty_payload_falls_back_to_title() -> None:
    """PagerDuty title is used when custom description is absent."""
    service, description = parse_pagerduty_payload(
        {
            "event": {
                "data": {
                    "title": "checkout-service latency spike",
                    "service": {"summary": "checkout-service"},
                }
            }
        }
    )
    assert service == "checkout-service"
    assert description == "checkout-service latency spike"


def test_pagerduty_webhook_accepts_valid_payload(make_settings) -> None:
    """POST /webhooks/pagerduty returns accepted response."""
    settings = make_settings(incidents_channel_id="C123INCIDENT", slack_bot_token="xoxb-test")
    payload = {
        "event": {
            "data": {
                "title": "checkout-service latency spike",
                "custom_details": {
                    "service": "checkout-service",
                    "description": "latency spike",
                },
            }
        }
    }

    with (
        patch("ai_incident_commander.server.routes.pagerduty.get_settings", return_value=settings),
        patch(
            "ai_incident_commander.server.routes.pagerduty._run_pagerduty_investigation",
            MagicMock(),
        ),
    ):
        client = TestClient(api)
        response = client.post("/webhooks/pagerduty", json=payload)

    assert response.status_code == 200
    assert response.json() == {
        "status": "accepted",
        "service": "checkout-service",
        "description": "latency spike",
    }
