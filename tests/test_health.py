"""Smoke tests for the HTTP API."""

from fastapi.testclient import TestClient

from ai_incident_commander.server.main import api


def test_health_returns_ok() -> None:
    """GET /health returns 200 with operational status fields."""
    client = TestClient(api)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db"] in {"pickle", "postgresql"}
    assert body["socket_mode"] in {"not_configured", "connected", "disconnected"}
    assert body["pagerduty"] in {"configured", "not_configured"}
