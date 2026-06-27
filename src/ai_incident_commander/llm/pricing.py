"""Approximate LLM pricing for usage-cost estimates in structured logs."""

from __future__ import annotations

# USD per 1M tokens: (input, output). Rates are approximate — verify against provider pricing pages.
MODEL_PRICING_USD_PER_MILLION: dict[str, tuple[float, float]] = {
    "gpt-4.1": (2.0, 8.0),
    "gpt-4.1-mini": (0.4, 1.6),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "gemini-2.0-flash": (0.1, 0.4),
    "gemini-2.0-flash-lite": (0.075, 0.3),
}

DEFAULT_INPUT_COST_PER_MILLION_USD = 2.0
DEFAULT_OUTPUT_COST_PER_MILLION_USD = 8.0


def estimate_cost_usd(
    usage_by_model: dict[str, dict[str, int]],
) -> float:
    """
    Estimate USD cost from per-model token usage metadata.

    Args:
        usage_by_model: LangChain usage metadata keyed by model name.

    Returns:
        Estimated cost in USD rounded to six decimal places.
    """
    total_cost = 0.0

    for model_name, usage in usage_by_model.items():
        input_tokens = int(usage.get("input_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)
        input_rate, output_rate = _resolve_model_pricing(model_name)

        total_cost += (input_tokens / 1_000_000) * input_rate
        total_cost += (output_tokens / 1_000_000) * output_rate

    return round(total_cost, 6)


def _resolve_model_pricing(model_name: str) -> tuple[float, float]:
    """
    Resolve per-million token pricing for a provider model name.

    Args:
        model_name: Model identifier from LangChain usage metadata.

    Returns:
        Tuple of input and output USD rates per 1M tokens.
    """
    normalized = model_name.lower()
    for known_model, rates in sorted(
        MODEL_PRICING_USD_PER_MILLION.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if known_model in normalized:
            return rates
    return DEFAULT_INPUT_COST_PER_MILLION_USD, DEFAULT_OUTPUT_COST_PER_MILLION_USD
