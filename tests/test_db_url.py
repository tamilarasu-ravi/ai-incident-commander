"""Tests for database URL resolution."""

from ai_incident_commander.db.url import resolve_database_url


def test_resolve_database_url_rewrites_db_host_on_host_machine(monkeypatch) -> None:
    """Docker Compose hostname db is rewritten to localhost outside containers."""
    monkeypatch.setattr("ai_incident_commander.db.url.is_running_in_docker", lambda: False)

    url = "postgresql+asyncpg://incident:incident@db:5432/incident_commander"
    assert resolve_database_url(url) == (
        "postgresql+asyncpg://incident:incident@localhost:5432/incident_commander"
    )


def test_resolve_database_url_keeps_db_host_inside_docker(monkeypatch) -> None:
    """Container runtime keeps the internal db hostname unchanged."""
    monkeypatch.setattr("ai_incident_commander.db.url.is_running_in_docker", lambda: True)

    url = "postgresql+asyncpg://incident:incident@db:5432/incident_commander"
    assert resolve_database_url(url) == url
