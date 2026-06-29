"""Integration circuit breaker for upstream dependency protection."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, TypeVar

import structlog

from ai_incident_commander.config import get_settings

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class CircuitState(str, Enum):
    """Circuit breaker lifecycle states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class _CircuitRecord:
    """Mutable breaker state for a single integration."""

    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    opened_at: float | None = None


_lock = threading.Lock()
_circuits: dict[str, _CircuitRecord] = {}


class CircuitOpenError(RuntimeError):
    """Raised when a circuit breaker is open and calls are blocked."""


def preflight_integration(integration_name: str) -> None:
    """
    Raise when an integration circuit is open before making a request.

    Args:
        integration_name: Stable integration identifier such as ``github``.

    Raises:
        CircuitOpenError: When the circuit is open and recovery has not elapsed.
    """
    settings = get_settings()
    if not settings.circuit_breaker_enabled:
        return

    record = _get_or_create_record(integration_name)
    _maybe_transition_to_half_open(record, settings.circuit_breaker_recovery_seconds)
    if record.state == CircuitState.OPEN:
        raise CircuitOpenError(f"Circuit open for integration: {integration_name}")


def record_integration_success(integration_name: str) -> None:
    """
    Reset breaker state after a successful integration call.

    Args:
        integration_name: Stable integration identifier such as ``github``.
    """
    settings = get_settings()
    if not settings.circuit_breaker_enabled:
        return
    record = _get_or_create_record(integration_name)
    _record_success(record)


def record_integration_failure(integration_name: str) -> None:
    """
    Record a failed integration call and open the circuit when threshold is reached.

    Args:
        integration_name: Stable integration identifier such as ``github``.
    """
    settings = get_settings()
    if not settings.circuit_breaker_enabled:
        return
    record = _get_or_create_record(integration_name)
    _record_failure(
        integration_name,
        record,
        settings.circuit_breaker_failure_threshold,
    )


def call_with_circuit_breaker(
    integration_name: str,
    operation: Callable[[], T],
) -> T:
    """
    Execute an integration call behind a simple circuit breaker.

    Args:
        integration_name: Stable integration identifier such as ``github``.
        operation: Callable that performs the upstream request.

    Returns:
        Result from ``operation`` when the circuit allows the call.

    Raises:
        CircuitOpenError: When the circuit is open and recovery timeout has not elapsed.
        Exception: Re-raises exceptions from ``operation`` after recording failures.
    """
    settings = get_settings()
    if not settings.circuit_breaker_enabled:
        return operation()

    record = _get_or_create_record(integration_name)
    _maybe_transition_to_half_open(record, settings.circuit_breaker_recovery_seconds)

    if record.state == CircuitState.OPEN:
        raise CircuitOpenError(f"Circuit open for integration: {integration_name}")

    try:
        result = operation()
    except Exception:
        _record_failure(integration_name, record, settings.circuit_breaker_failure_threshold)
        raise

    _record_success(record)
    return result


def get_circuit_states() -> dict[str, str]:
    """
    Return current circuit breaker states for health reporting.

    Returns:
        Mapping of integration name to circuit state value.
    """
    with _lock:
        return {name: record.state.value for name, record in _circuits.items()}


def reset_circuit_breakers() -> None:
    """Clear all circuit breaker state — intended for tests."""
    with _lock:
        _circuits.clear()


def _get_or_create_record(integration_name: str) -> _CircuitRecord:
    """
    Fetch or initialize breaker state for an integration.

    Args:
        integration_name: Integration identifier.

    Returns:
        Mutable circuit record.
    """
    with _lock:
        return _circuits.setdefault(integration_name, _CircuitRecord())


def _maybe_transition_to_half_open(record: _CircuitRecord, recovery_seconds: int) -> None:
    """
    Transition an open circuit to half-open after the recovery timeout.

    Args:
        record: Circuit record to inspect.
        recovery_seconds: Seconds to wait before allowing a probe call.
    """
    if record.state != CircuitState.OPEN or record.opened_at is None:
        return
    if time.time() - record.opened_at >= recovery_seconds:
        record.state = CircuitState.HALF_OPEN


def _record_failure(
    integration_name: str,
    record: _CircuitRecord,
    failure_threshold: int,
) -> None:
    """
    Record a failed integration call and open the circuit when threshold is reached.

    Args:
        integration_name: Integration identifier for logging.
        record: Circuit record to mutate.
        failure_threshold: Consecutive failures required to open the circuit.
    """
    with _lock:
        record.failure_count += 1
        if record.failure_count >= failure_threshold:
            record.state = CircuitState.OPEN
            record.opened_at = time.time()
            logger.warning(
                "circuit_breaker_opened",
                integration=integration_name,
                failure_count=record.failure_count,
            )


def _record_success(record: _CircuitRecord) -> None:
    """
    Reset breaker state after a successful call.

    Args:
        record: Circuit record to mutate.
    """
    with _lock:
        record.failure_count = 0
        record.state = CircuitState.CLOSED
        record.opened_at = None
