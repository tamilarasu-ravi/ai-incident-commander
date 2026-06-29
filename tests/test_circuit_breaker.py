"""Tests for integration circuit breaker behavior."""

import pytest

from ai_incident_commander.integrations.circuit_breaker import (
    CircuitOpenError,
    call_with_circuit_breaker,
    preflight_integration,
    record_integration_failure,
    reset_circuit_breakers,
)


def test_circuit_opens_after_failure_threshold(monkeypatch) -> None:
    """Repeated failures open the circuit and block further calls."""
    monkeypatch.setenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "2")
    from ai_incident_commander.config import get_settings

    get_settings.cache_clear()
    reset_circuit_breakers()

    def _failing_call() -> str:
        raise RuntimeError("upstream unavailable")

    with pytest.raises(RuntimeError):
        call_with_circuit_breaker("github", _failing_call)
    with pytest.raises(RuntimeError):
        call_with_circuit_breaker("github", _failing_call)

    with pytest.raises(CircuitOpenError):
        preflight_integration("github")

    get_settings.cache_clear()


def test_circuit_resets_after_success(monkeypatch) -> None:
    """A successful call closes the circuit after failures."""
    reset_circuit_breakers()
    record_integration_failure("datadog")
    call_with_circuit_breaker("datadog", lambda: "ok")
    preflight_integration("datadog")
