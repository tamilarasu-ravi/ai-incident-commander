"""Investigation queue with in-process workers and optional Redis offload."""

from __future__ import annotations

import queue
import threading
import time
from typing import Any, Callable

import structlog

from ai_incident_commander.config import get_settings
from ai_incident_commander.models.investigation_job import (
    InvestigationJob,
    derive_investigation_id,
)
from ai_incident_commander.ops.metrics import (
    record_investigation_completed,
    record_investigation_failed,
    record_investigation_started,
)

logger = structlog.get_logger(__name__)

INVESTIGATION_QUEUE_KEY = "investigation_jobs"

_job_queue: queue.Queue[InvestigationJob | None] | None = None
_worker_threads: list[threading.Thread] = []
_stop_event = threading.Event()
_semaphore: threading.Semaphore | None = None
_run_job: Callable[[InvestigationJob], None] | None = None
_redis_consumer_thread: threading.Thread | None = None


def configure_investigation_runner(run_job: Callable[[InvestigationJob], None]) -> None:
    """
    Register the callable that executes a queued investigation job.

    Args:
        run_job: Function invoked by worker threads for each dequeued job.
    """
    global _run_job
    _run_job = run_job


def enqueue_investigation(
    *,
    service: str,
    description: str,
    channel_id: str,
    idempotency_key: str | None = None,
    action_token: str | None = None,
    assistant_thread: tuple[str, str] | None = None,
    investigation_id: str | None = None,
) -> str:
    """
    Enqueue an investigation for asynchronous execution.

    Args:
        service: Affected service name.
        description: Human-readable incident description.
        channel_id: Slack channel ID for surfacing results.
        idempotency_key: Optional stable key for deduplicated investigation IDs.
        action_token: Optional Slack RTS action token.
        assistant_thread: Optional Assistant thread coordinates ``(channel_id, thread_ts)``.
        investigation_id: Optional explicit ID; otherwise derived from idempotency key.

    Returns:
        Investigation ID assigned to the queued job.

    Raises:
        RuntimeError: When workers were not started or the in-process queue is full.
    """
    settings = get_settings()
    resolved_id = investigation_id or derive_investigation_id(idempotency_key)
    job = InvestigationJob(
        investigation_id=resolved_id,
        service=service,
        description=description,
        channel_id=channel_id,
        idempotency_key=idempotency_key,
        action_token=action_token,
        assistant_thread=assistant_thread,
    )

    if settings.redis_url:
        _enqueue_redis(job)
        logger.info(
            "investigation_enqueued_redis",
            investigation_id=resolved_id,
            service=service,
        )
        return resolved_id

    if _job_queue is None:
        msg = "Investigation workers are not started"
        raise RuntimeError(msg)

    try:
        _job_queue.put(job, block=False)
    except queue.Full as exc:
        msg = "Investigation queue is full"
        raise RuntimeError(msg) from exc

    logger.info(
        "investigation_enqueued",
        investigation_id=resolved_id,
        service=service,
        queue_depth=_job_queue.qsize(),
    )
    return resolved_id


def start_investigation_workers() -> None:
    """Start in-process workers and optional Redis consumer threads."""
    global _job_queue, _semaphore, _redis_consumer_thread

    settings = get_settings()
    if _run_job is None:
        msg = "Investigation runner is not configured"
        raise RuntimeError(msg)

    if settings.redis_url:
        if settings.investigation_worker_enabled:
            if _redis_consumer_thread is None or not _redis_consumer_thread.is_alive():
                _redis_consumer_thread = threading.Thread(
                    target=_redis_consumer_loop,
                    name="investigation-redis-consumer",
                    daemon=True,
                )
                _redis_consumer_thread.start()
            logger.info(
                "investigation_workers_started",
                mode="redis",
                max_concurrent=settings.max_concurrent_investigations,
            )
        else:
            logger.info(
                "investigation_workers_started",
                mode="redis_producer_only",
                hint="Set INVESTIGATION_WORKER_ENABLED=true on a worker process",
            )
        return

    if _job_queue is not None:
        return

    _job_queue = queue.Queue(maxsize=settings.investigation_queue_max_size)
    _semaphore = threading.Semaphore(settings.max_concurrent_investigations)

    for index in range(settings.investigation_worker_threads):
        thread = threading.Thread(
            target=_worker_loop,
            name=f"investigation-worker-{index}",
            daemon=True,
        )
        thread.start()
        _worker_threads.append(thread)

    logger.info(
        "investigation_workers_started",
        mode="in_process",
        worker_threads=settings.investigation_worker_threads,
        max_concurrent=settings.max_concurrent_investigations,
        queue_max_size=settings.investigation_queue_max_size,
    )


def stop_investigation_workers() -> None:
    """Signal workers to stop and drain the in-process queue."""
    global _job_queue, _worker_threads, _semaphore, _redis_consumer_thread

    _stop_event.set()

    if _job_queue is not None:
        for _ in _worker_threads:
            try:
                _job_queue.put_nowait(None)
            except queue.Full:
                pass

    for thread in _worker_threads:
        thread.join(timeout=2)

    _worker_threads = []
    _job_queue = None
    _semaphore = None
    _redis_consumer_thread = None
    _stop_event.clear()


def get_queue_stats() -> dict[str, Any]:
    """
    Return queue depth and worker configuration for health checks.

    Returns:
        Dictionary with mode, depth, and concurrency settings.
    """
    settings = get_settings()
    stats: dict[str, Any] = {
        "mode": "redis" if settings.redis_url else "in_process",
        "max_concurrent_investigations": settings.max_concurrent_investigations,
        "worker_threads": settings.investigation_worker_threads,
        "queue_max_size": settings.investigation_queue_max_size,
    }

    if settings.redis_url:
        stats["queue_depth"] = _redis_queue_depth()
    elif _job_queue is not None:
        stats["queue_depth"] = _job_queue.qsize()
    else:
        stats["queue_depth"] = 0

    return stats


def _enqueue_redis(job: InvestigationJob) -> None:
    """
    Push a job onto the Redis investigation queue.

    Args:
        job: Investigation work item to enqueue.

    Raises:
        RuntimeError: When Redis is unavailable.
    """
    from ai_incident_commander.cache.redis_client import get_redis_client

    client = get_redis_client()
    if client is None:
        msg = "REDIS_URL is configured but Redis client is unavailable"
        raise RuntimeError(msg)
    client.lpush(INVESTIGATION_QUEUE_KEY, job.to_redis_payload())


def _redis_queue_depth() -> int:
    """
    Return Redis queue length when configured.

    Returns:
        Number of pending jobs, or zero when Redis is unavailable.
    """
    from ai_incident_commander.cache.redis_client import get_redis_client

    client = get_redis_client()
    if client is None:
        return 0
    return int(client.llen(INVESTIGATION_QUEUE_KEY))


def _redis_consumer_loop() -> None:
    """Blocking Redis consumer that executes investigation jobs."""
    from ai_incident_commander.cache.redis_client import get_redis_client

    settings = get_settings()
    client = get_redis_client()
    if client is None or _run_job is None:
        return

    local_semaphore = threading.Semaphore(settings.max_concurrent_investigations)
    logger.info("investigation_redis_consumer_started")

    while not _stop_event.is_set():
        item = client.brpop(INVESTIGATION_QUEUE_KEY, timeout=2)
        if item is None:
            continue

        _, raw_payload = item
        job = InvestigationJob.from_redis_payload(
            raw_payload.decode("utf-8") if isinstance(raw_payload, bytes) else str(raw_payload)
        )

        def _execute(current_job: InvestigationJob) -> None:
            local_semaphore.acquire()
            try:
                _execute_job(current_job)
            finally:
                local_semaphore.release()

        threading.Thread(
            target=_execute,
            args=(job,),
            name=f"investigation-redis-job-{job.investigation_id[:8]}",
            daemon=True,
        ).start()


def _worker_loop() -> None:
    """In-process worker loop that drains the local queue."""
    while not _stop_event.is_set():
        if _job_queue is None or _semaphore is None or _run_job is None:
            return

        try:
            job = _job_queue.get(timeout=1)
        except queue.Empty:
            continue

        if job is None:
            _job_queue.task_done()
            return

        _semaphore.acquire()
        try:
            _execute_job(job)
        finally:
            _semaphore.release()
            _job_queue.task_done()


def _execute_job(job: InvestigationJob) -> None:
    """
    Execute a single investigation job with metrics.

    Args:
        job: Investigation work item to run.
    """
    if _run_job is None:
        return

    started = time.perf_counter()
    record_investigation_started()
    try:
        _run_job(job)
        record_investigation_completed(time.perf_counter() - started)
    except Exception:
        record_investigation_failed()
        logger.exception(
            "investigation_job_failed",
            investigation_id=job.investigation_id,
            service=job.service,
        )
