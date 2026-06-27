"""Tests for approximate LLM cost estimation."""

from ai_incident_commander.llm.pricing import estimate_cost_usd


def test_estimate_cost_usd_uses_model_specific_rates() -> None:
    """Known models use configured per-million token pricing."""
    cost = estimate_cost_usd(
        {
            "gpt-4.1-mini": {
                "input_tokens": 1_000_000,
                "output_tokens": 1_000_000,
                "total_tokens": 2_000_000,
            }
        }
    )

    assert cost == 2.0
