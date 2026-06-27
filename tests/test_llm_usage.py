"""Tests for LLM usage logging and aggregation."""

from unittest.mock import patch

import pytest

from ai_incident_commander.llm.usage import (
    log_llm_usage,
    summarize_usage_metadata,
    track_investigation_llm_usage,
)


def test_summarize_usage_metadata_sums_across_models() -> None:
    """Usage metadata from multiple models is aggregated into one total."""
    summary = summarize_usage_metadata(
        {
            "gpt-4.1": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
            "gemini-2.0-flash": {
                "input_tokens": 50,
                "output_tokens": 10,
                "total_tokens": 60,
            },
        }
    )

    assert summary["input_tokens"] == 150
    assert summary["output_tokens"] == 30
    assert summary["total_tokens"] == 180
    assert summary["models"] == "gpt-4.1,gemini-2.0-flash"


def test_log_llm_usage_emits_structured_event() -> None:
    """Each LLM operation logs token counts when usage metadata is present."""
    with patch("ai_incident_commander.llm.usage.logger") as mock_logger:
        mock_logger.bind.return_value = mock_logger
        summary = log_llm_usage(
            operation="rca_synthesis",
            usage_by_model={
                "gpt-4.1": {"input_tokens": 40, "output_tokens": 10, "total_tokens": 50}
            },
            service="checkout-service",
        )

    mock_logger.info.assert_called_once()
    assert summary["total_tokens"] == 50


def test_log_llm_usage_includes_estimated_cost() -> None:
    """Token usage logs include an approximate USD cost estimate."""
    with patch("ai_incident_commander.llm.usage.logger") as mock_logger:
        mock_logger.bind.return_value = mock_logger
        summary = log_llm_usage(
            operation="rca_synthesis",
            usage_by_model={
                "gpt-4.1": {"input_tokens": 1_000_000, "output_tokens": 0, "total_tokens": 1_000_000}
            },
            service="checkout-service",
        )

    assert summary["estimated_cost_usd"] == 2.0
    mock_logger.info.assert_called_once()
    assert mock_logger.info.call_args.kwargs["estimated_cost_usd"] == 2.0


def test_track_investigation_llm_usage_logs_investigation_total() -> None:
    """Investigation context manager emits one summary after nested LLM calls."""
    with patch("ai_incident_commander.llm.usage.logger") as mock_logger:
        mock_logger.bind.return_value = mock_logger
        with track_investigation_llm_usage(
            service="checkout-service",
            investigation_id="inv-123",
        ):
            log_llm_usage(
                operation="rca_synthesis",
                usage_by_model={
                    "gpt-4.1": {"input_tokens": 30, "output_tokens": 5, "total_tokens": 35}
                },
                service="checkout-service",
            )
            log_llm_usage(
                operation="grounding_validation",
                usage_by_model={
                    "gpt-4.1-mini": {
                        "input_tokens": 10,
                        "output_tokens": 2,
                        "total_tokens": 12,
                    }
                },
                service="checkout-service",
            )

    summary_calls = [
        call
        for call in mock_logger.info.call_args_list
        if call.args and call.args[0] == "investigation_llm_usage_total"
    ]
    assert len(summary_calls) == 1
    kwargs = summary_calls[0].kwargs
    assert kwargs["llm_calls"] == 2
    assert kwargs["total_tokens"] == 47
