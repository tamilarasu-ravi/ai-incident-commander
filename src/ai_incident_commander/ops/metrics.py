"""In-process operational metrics for health checks and scaling visibility."""

from __future__ import annotations

import statistics
import threading
import time
from collections import deque
from typing import Any

_lock = threading.Lock()
_investigations_started = 0
_investigations_completed = 0
_investigations_failed = 0
_llm_rate_limit_errors = 0
_active_investigations = 0
_duration_samples: deque[float] = deque(maxlen=200)


def record_investigation_started() -> None:
    """Increment counters when an investigation job begins execution."""
    global _investigations_started, _active_investigations
    with _lock:
        _investigations_started += 1
        _active_investigations += 1


def record_investigation_completed(duration_seconds: float) -> None:
    """
    Record a successful investigation completion and its duration.

    Args:
        duration_seconds: Wall-clock runtime for the investigation graph.
    """
    global _investigations_completed, _active_investigations
    with _lock:
        _investigations_completed += 1
        _active_investigations = max(0, _active_investigations - 1)
        _duration_samples.append(duration_seconds)


def record_investigation_failed() -> None:
    """Increment failure counter when an investigation job errors."""
    global _investigations_failed, _active_investigations
    with _lock:
        _investigations_failed += 1
        _active_investigations = max(0, _active_investigations - 1)


def record_llm_rate_limit_error() -> None:
    """Increment counter when an LLM provider returns a rate-limit style error."""
    global _llm_rate_limit_errors
    with _lock:
        _llm_rate_limit_errors += 1


def is_rate_limit_error(error: BaseException) -> bool:
    """
    Return True when an exception looks like an LLM provider rate limit.

    Args:
        error: Exception raised by an LLM client call.

    Returns:
        Whether the error should be counted as a rate-limit event.
    """
    message = str(error).lower()
    markers = ("429", "rate limit", "rate_limit", "too many requests", "quota")
    return any(marker in message for marker in markers)


def get_metrics_snapshot() -> dict[str, Any]:
    """
    Return a JSON-serializable metrics snapshot for health endpoints.

    Returns:
        Dictionary with investigation and LLM counters plus duration percentiles.
    """
    with _lock:
        durations = list(_duration_samples)
        snapshot = {
            "investigations_started": _investigations_started,
            "investigations_completed": _investigations_completed,
            "investigations_failed": _investigations_failed,
            "investigations_active": _active_investigations,
            "llm_rate_limit_errors": _llm_rate_limit_errors,
            "investigation_duration_p50_seconds": _percentile(durations, 50),
            "investigation_duration_p95_seconds": _percentile(durations, 95),
            "captured_at_unix": time.time(),
        }
    return snapshot


def _percentile(samples: list[float], percentile: int) -> float | None:
    """
    Compute a percentile from duration samples.

    Args:
        samples: Recent investigation durations in seconds.
        percentile: Percentile value such as 50 or 95.

    Returns:
        Percentile value rounded to three decimals, or ``None`` when empty.
    """
    if not samples:
        return None
    if len(samples) == 1:
        return round(samples[0], 3)
    return round(statistics.quantiles(samples, n=100)[percentile - 1], 3)
