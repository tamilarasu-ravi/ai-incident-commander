"""FastMCP server exposing GitHub commit evidence tools."""

from ai_incident_commander.mcp.stdio_logging import configure_mcp_stdio_logging

# MCP uses stdout for JSON-RPC — configure logging before any app imports.
configure_mcp_stdio_logging()

import json

from mcp.server.fastmcp import FastMCP

from ai_incident_commander.config import get_settings
from ai_incident_commander.integrations.github import fetch_recent_commits_http

mcp = FastMCP("ai-incident-commander-github")


@mcp.tool()
async def list_recent_commits(service: str) -> str:
    """
    List recent commits for the configured repository.

    Args:
        service: Affected service name for logging context.

    Returns:
        JSON array of ``CommitEvidence`` objects.
    """
    settings = get_settings()
    commits = await fetch_recent_commits_http(settings, service)
    return json.dumps([commit.model_dump() for commit in commits], ensure_ascii=False)


def main() -> None:
    """Run the GitHub MCP server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
