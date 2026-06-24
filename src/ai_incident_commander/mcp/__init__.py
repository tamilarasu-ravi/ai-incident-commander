"""MCP integration entrypoints."""

from ai_incident_commander.mcp.client import McpClientError, call_stdio_tool

__all__ = ["McpClientError", "call_stdio_tool"]
