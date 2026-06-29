"""Tests for the in-process investigation queue."""

import time

from ai_incident_commander.config import get_settings
from ai_incident_commander.models.investigation_job import InvestigationJob
from ai_incident_commander.ops.investigation_queue import (
    configure_investigation_runner,
    enqueue_investigation,
    get_queue_stats,
    start_investigation_workers,
    stop_investigation_workers,
)


def test_in_process_queue_executes_job(monkeypatch) -> None:
    """Queued jobs are executed by background worker threads."""
    from ai_incident_commander.cache.redis_client import reset_redis_client

    monkeypatch.setenv("REDIS_URL", "")
    get_settings.cache_clear()
    reset_redis_client()

    completed: list[str] = []

    def _run_job(job: InvestigationJob) -> None:
        completed.append(job.investigation_id)

    configure_investigation_runner(_run_job)
    start_investigation_workers()

    investigation_id = enqueue_investigation(
        service="checkout-service",
        description="latency spike",
        channel_id="C123",
    )

    deadline = time.time() + 3
    while time.time() < deadline and investigation_id not in completed:
        time.sleep(0.05)

    stop_investigation_workers()
    assert investigation_id in completed

    stats = get_queue_stats()
    assert stats["mode"] == "in_process"
    get_settings.cache_clear()
