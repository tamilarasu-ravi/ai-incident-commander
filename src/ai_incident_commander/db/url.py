"""Database URL helpers for host vs Docker Compose runtimes."""

import os
from pathlib import Path
from urllib.parse import urlparse, urlunparse


def is_running_in_docker() -> bool:
    """Return True when the app process is running inside a container."""
    return Path("/.dockerenv").exists() or os.environ.get("RUNNING_IN_DOCKER") == "1"


def resolve_database_url(database_url: str) -> str:
    """
    Normalize ``DATABASE_URL`` for the current runtime.

    Docker Compose uses the hostname ``db`` on the internal network. When uvicorn
    or Alembic run on the host machine, rewrite that host to ``localhost``.

    Args:
        database_url: Raw database URL from settings or environment.

    Returns:
        URL suitable for the current runtime.
    """
    if not database_url or is_running_in_docker():
        return database_url

    parsed = urlparse(database_url)
    if parsed.hostname != "db":
        return database_url

    username = parsed.username or ""
    password = parsed.password or ""
    auth = ""
    if username and password:
        auth = f"{username}:{password}@"
    elif username:
        auth = f"{username}@"

    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{auth}localhost{port}"
    return urlunparse(parsed._replace(netloc=netloc))


def database_connection_hint(database_url: str) -> str:
    """
    Return a short hint when database connections fail.

    Args:
        database_url: Database URL that failed to connect.

    Returns:
        Human-readable troubleshooting hint.
    """
    parsed = urlparse(database_url)
    if parsed.hostname == "db" and not is_running_in_docker():
        return (
            "DATABASE_URL uses host 'db', which only resolves inside Docker Compose. "
            "Use 'localhost' when running uvicorn on your machine, or run "
            "'docker compose up app' instead."
        )
    if parsed.hostname == "localhost":
        return "Start PostgreSQL with 'docker compose up -d db' and retry."
    return "Check DATABASE_URL and ensure PostgreSQL is reachable."
