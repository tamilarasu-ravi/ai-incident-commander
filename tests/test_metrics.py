"""Tests for scaling metrics helpers."""

from ai_incident_commander.ops.metrics import (
    get_metrics_snapshot,
    is_rate_limit_error,
    record_investigation_completed,
    record_investigation_failed,
    record_investigation_started,
    record_llm_rate_limit_error,
)


def test_rate_limit_error_detection() -> None:
    """Rate-limit style provider errors are recognized."""
    assert is_rate_limit_error(RuntimeError("HTTP 429 Too Many Requests"))
    assert not is_rate_limit_error(RuntimeError("connection reset"))


def test_metrics_snapshot_tracks_counters() -> None:
    """Metrics snapshot exposes investigation and LLM counters."""
    record_investigation_started()
    record_investigation_completed(1.25)
    record_investigation_failed()
    record_llm_rate_limit_error()

    snapshot = get_metrics_snapshot()
    assert snapshot["investigations_started"] >= 1
    assert snapshot["investigations_completed"] >= 1
    assert snapshot["investigations_failed"] >= 1
    assert snapshot["llm_rate_limit_errors"] >= 1
