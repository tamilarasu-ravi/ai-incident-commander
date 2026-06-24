"""Tests for PagerDuty webhook parsing, security, and route."""

import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from ai_incident_commander.server.main import api
from ai_incident_commander.server.pagerduty_security import (
    PAGERDUTY_SIGNATURE_HEADER,
    extract_pagerduty_event_id,
    is_duplicate_pagerduty_event,
    reset_pagerduty_dedup_cache,
    verify_pagerduty_signature,
)
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


def test_verify_pagerduty_signature_accepts_valid_hmac() -> None:
    """Valid v1 signatures pass verification."""
    body = b'{"event":{"id":"evt-1"}}'
    secret = "pagerduty-secret"
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    assert verify_pagerduty_signature(body, secret, f"v1={digest}") is True


def test_verify_pagerduty_signature_rejects_invalid_hmac() -> None:
    """Invalid signatures are rejected."""
    body = b'{"event":{"id":"evt-1"}}'
    assert verify_pagerduty_signature(body, "pagerduty-secret", "v1=deadbeef") is False


def test_extract_pagerduty_event_id_reads_nested_event() -> None:
    """Event IDs are read from nested PagerDuty payloads."""
    assert extract_pagerduty_event_id({"event": {"id": "evt-123"}}) == "evt-123"


def test_is_duplicate_pagerduty_event_tracks_ids() -> None:
    """Duplicate event IDs are detected in-process."""
    reset_pagerduty_dedup_cache()
    assert is_duplicate_pagerduty_event("evt-dup") is False
    assert is_duplicate_pagerduty_event("evt-dup") is True


def test_pagerduty_webhook_accepts_valid_payload(make_settings) -> None:
    """POST /webhooks/pagerduty returns accepted response."""
    settings = make_settings(incidents_channel_id="C123INCIDENT", slack_bot_token="xoxb-test")
    payload = {
        "event": {
            "id": "evt-accepted",
            "data": {
                "title": "checkout-service latency spike",
                "custom_details": {
                    "service": "checkout-service",
                    "description": "latency spike",
                },
            },
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


def test_pagerduty_webhook_rejects_invalid_signature(make_settings) -> None:
    """Unsigned requests are rejected when a webhook secret is configured."""
    settings = make_settings(
        incidents_channel_id="C123INCIDENT",
        pagerduty_webhook_secret="pagerduty-secret",
    )
    payload = {
        "event": {
            "id": "evt-signed",
            "data": {
                "title": "checkout-service latency spike",
                "custom_details": {
                    "service": "checkout-service",
                    "description": "latency spike",
                },
            },
        }
    }
    body = json.dumps(payload).encode("utf-8")

    with patch("ai_incident_commander.server.routes.pagerduty.get_settings", return_value=settings):
        client = TestClient(api)
        response = client.post(
            "/webhooks/pagerduty",
            content=body,
            headers={PAGERDUTY_SIGNATURE_HEADER: "v1=invalid"},
        )

    assert response.status_code == 401


def test_pagerduty_webhook_deduplicates_retries(make_settings) -> None:
    """Duplicate PagerDuty event IDs return duplicate status without re-running."""
    reset_pagerduty_dedup_cache()
    settings = make_settings(incidents_channel_id="C123INCIDENT", slack_bot_token="xoxb-test")
    payload = {
        "event": {
            "id": "evt-retry",
            "data": {
                "title": "checkout-service latency spike",
                "custom_details": {
                    "service": "checkout-service",
                    "description": "latency spike",
                },
            },
        }
    }

    with (
        patch("ai_incident_commander.server.routes.pagerduty.get_settings", return_value=settings),
        patch(
            "ai_incident_commander.server.routes.pagerduty._run_pagerduty_investigation",
            MagicMock(),
        ) as investigation_mock,
    ):
        client = TestClient(api)
        first = client.post("/webhooks/pagerduty", json=payload)
        second = client.post("/webhooks/pagerduty", json=payload)

    assert first.status_code == 200
    assert first.json()["status"] == "accepted"
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"
    investigation_mock.assert_called_once()
