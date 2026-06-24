"""Tests for MCP stdio client helpers."""

import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_incident_commander.mcp.client import McpClientError, call_stdio_tool
from mcp.types import TextContent


async def test_call_stdio_tool_returns_parsed_json() -> None:
    """Successful MCP tool calls return parsed JSON from text content."""
    mock_result = MagicMock()
    mock_result.isError = False
    mock_result.content = [TextContent(type="text", text=json.dumps([{"sha": "abc1234"}]))]

    mock_session = AsyncMock()
    mock_session.initialize = AsyncMock()
    mock_session.call_tool = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    mock_read = MagicMock()
    mock_write = MagicMock()

    @asynccontextmanager
    async def fake_stdio_client(_params):
        yield mock_read, mock_write

    with patch(
        "ai_incident_commander.mcp.client.stdio_client",
        side_effect=fake_stdio_client,
    ), patch(
        "ai_incident_commander.mcp.client.ClientSession",
        return_value=mock_session,
    ):
        payload = await call_stdio_tool(
            module="ai_incident_commander.mcp.github_server",
            tool_name="list_recent_commits",
            arguments={"service": "checkout-service"},
        )

    assert payload == [{"sha": "abc1234"}]
    mock_session.initialize.assert_awaited_once()
    mock_session.call_tool.assert_awaited_once_with(
        "list_recent_commits",
        {"service": "checkout-service"},
    )


async def test_call_stdio_tool_raises_on_error_flag() -> None:
    """MCP tool results with isError raise McpClientError."""
    mock_result = MagicMock()
    mock_result.isError = True
    mock_result.content = []

    mock_session = AsyncMock()
    mock_session.initialize = AsyncMock()
    mock_session.call_tool = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    mock_read = MagicMock()
    mock_write = MagicMock()

    @asynccontextmanager
    async def fake_stdio_client(_params):
        yield mock_read, mock_write

    with patch(
        "ai_incident_commander.mcp.client.stdio_client",
        side_effect=fake_stdio_client,
    ), patch(
        "ai_incident_commander.mcp.client.ClientSession",
        return_value=mock_session,
    ):
        with pytest.raises(McpClientError, match="returned an error"):
            await call_stdio_tool(
                module="ai_incident_commander.mcp.github_server",
                tool_name="list_recent_commits",
                arguments={"service": "checkout-service"},
            )
