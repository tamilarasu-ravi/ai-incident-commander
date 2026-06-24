"""Logging configuration safe for MCP stdio servers.

MCP uses stdout exclusively for JSON-RPC. Any log lines on stdout break the
client protocol, so MCP server subprocesses must log to stderr only.
"""

import logging
import sys

import structlog


def configure_mcp_stdio_logging() -> None:
    """Route structlog output to stderr for MCP server subprocesses."""
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )
