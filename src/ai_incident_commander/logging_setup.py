"""Application-wide structlog configuration."""

import logging
import sys

import structlog


def configure_logging(log_level: str = "info") -> None:
    """
    Configure structlog for the main application process.

    Logs go to stderr so stdout stays free for MCP stdio subprocesses and tools.

    Args:
        log_level: Minimum log level name (e.g. ``info``, ``debug``).
    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        stream=sys.stderr,
        format="%(message)s",
        force=True,
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
