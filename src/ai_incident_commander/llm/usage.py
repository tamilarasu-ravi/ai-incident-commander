"""LLM token usage logging and per-investigation aggregation."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Generator

import structlog
from langchain_core.callbacks import get_usage_metadata_callback

logger = structlog.get_logger(__name__)

_investigation_usage_records: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "investigation_llm_usage_records",
    default=None,
)


def summarize_usage_metadata(
    usage_by_model: dict[str, dict[str, int]],
) -> dict[str, int | str]:
    """
    Sum token usage across one or more model calls.

    Args:
        usage_by_model: LangChain usage metadata keyed by model name.

    Returns:
        Aggregated input, output, and total token counts plus model list.
    """
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    model_names: list[str] = []

    for model_name, usage in usage_by_model.items():
        model_names.append(model_name)
        input_tokens += int(usage.get("input_tokens", 0) or 0)
        output_tokens += int(usage.get("output_tokens", 0) or 0)
        total_tokens += int(usage.get("total_tokens", 0) or 0)

    if total_tokens == 0 and (input_tokens or output_tokens):
        total_tokens = input_tokens + output_tokens

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "models": ",".join(model_names),
    }


def log_llm_usage(
    *,
    operation: str,
    usage_by_model: dict[str, dict[str, int]],
    service: str | None = None,
) -> dict[str, int | str]:
    """
    Emit structured logs for a single LLM operation and record investigation totals.

    Args:
        operation: Logical call name such as ``rca_synthesis``.
        usage_by_model: LangChain usage metadata keyed by model name.
        service: Optional affected service for log correlation.

    Returns:
        Summarized token usage for the operation.
    """
    summary = summarize_usage_metadata(usage_by_model)
    log = logger.bind(operation=operation)
    if service:
        log = log.bind(service=service)

    if summary["total_tokens"]:
        log.info("llm_usage_recorded", **summary)
    else:
        log.info(
            "llm_usage_unavailable",
            hint="Provider did not return usage metadata for this call",
        )

    records = _investigation_usage_records.get()
    if records is not None:
        records.append(
            {
                "operation": operation,
                **{key: summary[key] for key in ("input_tokens", "output_tokens", "total_tokens")},
                "models": summary["models"],
            }
        )

    return summary


@contextmanager
def track_investigation_llm_usage(
    *,
    service: str | None = None,
    investigation_id: str | None = None,
) -> Generator[None, None, None]:
    """
    Track and log total LLM usage for one investigation run.

    Args:
        service: Affected service name for summary logs.
        investigation_id: Investigation identifier for summary logs.

    Yields:
        Control while LLM calls within the investigation execute.
    """
    token = _investigation_usage_records.set([])
    try:
        yield
    finally:
        records = _investigation_usage_records.get() or []
        _investigation_usage_records.reset(token)

        if records:
            total_input = sum(int(record["input_tokens"]) for record in records)
            total_output = sum(int(record["output_tokens"]) for record in records)
            total_tokens = sum(int(record["total_tokens"]) for record in records)
            operations = [str(record["operation"]) for record in records]

            log = logger.bind(service=service, investigation_id=investigation_id)
            log.info(
                "investigation_llm_usage_total",
                llm_calls=len(records),
                operations=operations,
                input_tokens=total_input,
                output_tokens=total_output,
                total_tokens=total_tokens,
            )


async def ainvoke_with_usage_logging(
    runnable: Any,
    messages: list[Any],
    *,
    operation: str,
    service: str | None = None,
) -> tuple[Any, dict[str, int | str]]:
    """
    Invoke a LangChain runnable and log token usage from provider metadata.

    Args:
        runnable: LangChain runnable such as a structured-output chat model.
        messages: Chat messages passed to ``ainvoke``.
        operation: Logical call name for structured logs.
        service: Optional affected service for log correlation.

    Returns:
        Tuple of invoke result and summarized usage metadata.
    """
    with get_usage_metadata_callback() as usage_callback:
        result = await runnable.ainvoke(
            messages,
            config={"callbacks": [usage_callback]},
        )

    usage_summary = log_llm_usage(
        operation=operation,
        usage_by_model=usage_callback.usage_metadata,
        service=service,
    )
    return result, usage_summary
