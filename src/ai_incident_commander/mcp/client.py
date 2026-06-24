"""Shared MCP client helpers for stdio tool calls."""

import json
import os
import sys
from typing import Any

import structlog
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent

logger = structlog.get_logger(__name__)


class McpClientError(Exception):
    """Raised when an MCP tool call fails."""


async def call_stdio_tool(
    *,
    module: str,
    tool_name: str,
    arguments: dict[str, Any],
    env: dict[str, str] | None = None,
) -> Any:
    """
    Spawn an MCP server module over stdio and call a named tool.

    Args:
        module: Python module path for the MCP server (``python -m <module>``).
        tool_name: MCP tool name exposed by the server.
        arguments: Tool argument payload.
        env: Optional environment variables for the subprocess.

    Returns:
        Parsed JSON payload when the tool returns JSON text content.

    Raises:
        McpClientError: If the MCP session or tool call fails.
    """
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", module],
        env=merged_env,
    )
    log = logger.bind(module=module, tool_name=tool_name)
    log.info("mcp_tool_call_started")

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
    except Exception as error:
        log.error("mcp_tool_call_failed", error=str(error))
        raise McpClientError(str(error)) from error

    if result.isError:
        detail = _extract_tool_error_text(result)
        message = f"MCP tool {tool_name} returned an error"
        if detail:
            message = f"{message}: {detail}"
        raise McpClientError(message)

    for block in result.content:
        if isinstance(block, TextContent):
            return json.loads(block.text)

    raise McpClientError(f"MCP tool {tool_name} returned no JSON text content")


def _extract_tool_error_text(result: Any) -> str:
    """Return human-readable text from a failed MCP tool result."""
    parts: list[str] = []
    for block in result.content:
        if isinstance(block, TextContent) and block.text.strip():
            parts.append(block.text.strip())
    return " | ".join(parts)
