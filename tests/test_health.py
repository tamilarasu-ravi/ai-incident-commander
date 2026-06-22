"""Smoke tests for the HTTP API."""

from fastapi.testclient import TestClient

from ai_incident_commander.server.main import api


def test_health_returns_ok() -> None:
    """GET /health returns 200 with status ok."""
    client = TestClient(api)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
