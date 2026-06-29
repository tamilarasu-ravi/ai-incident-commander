"""Dedicated investigation worker process for Redis-backed queues."""

from __future__ import annotations

import signal
import threading
import time

import structlog

from ai_incident_commander.config import get_settings
from ai_incident_commander.db.url import resolve_database_url
from ai_incident_commander.integrations.credentials import validate_startup_credentials
from ai_incident_commander.logging_setup import configure_logging
from ai_incident_commander.ops.investigation_queue import (
    configure_investigation_runner,
    start_investigation_workers,
    stop_investigation_workers,
)
from ai_incident_commander.slack.investigation_runner import execute_investigation_job
from ai_incident_commander.store.investigations import configure_investigation_store

logger = structlog.get_logger(__name__)
_shutdown = threading.Event()


def _handle_shutdown(_signum: int, _frame: object | None) -> None:
    """Signal handler that requests a graceful worker shutdown."""
    _shutdown.set()


def main() -> None:
    """
    Start a Redis investigation worker that consumes queued jobs.

    Raises:
        RuntimeError: When Redis is not configured for worker mode.
    """
    settings = get_settings()
    configure_logging(settings.log_level)
    validate_startup_credentials(settings)

    if not settings.redis_url:
        msg = "REDIS_URL is required for the investigation worker process"
        raise RuntimeError(msg)

    if settings.is_database_configured:
        configure_investigation_store(
            use_postgres=True,
            database_url=resolve_database_url(settings.database_url),
        )
    else:
        configure_investigation_store(use_postgres=False)

    configure_investigation_runner(
        lambda job: execute_investigation_job(job, settings),
    )
    start_investigation_workers()

    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    logger.info(
        "investigation_worker_running",
        redis_url_configured=True,
        max_concurrent=settings.max_concurrent_investigations,
    )

    while not _shutdown.is_set():
        time.sleep(1)

    stop_investigation_workers()
    logger.info("investigation_worker_stopped")


if __name__ == "__main__":
    main()
