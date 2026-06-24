"""Fetch GitHub commits via the in-repo MCP server."""

import structlog

from ai_incident_commander.config import Settings
from ai_incident_commander.mcp.client import McpClientError, call_stdio_tool
from ai_incident_commander.models.evidence import CommitEvidence

logger = structlog.get_logger(__name__)

GITHUB_MCP_MODULE = "ai_incident_commander.mcp.github_server"
GITHUB_MCP_TOOL = "list_recent_commits"


async def fetch_recent_commits_mcp(settings: Settings, service: str) -> list[CommitEvidence]:
    """
    Fetch recent commits by calling the GitHub FastMCP tool over stdio.

    Args:
        settings: Application settings with GitHub credentials.
        service: Affected service name passed to the MCP tool.

    Returns:
        List of ``CommitEvidence`` from the MCP server response.

    Raises:
        McpClientError: If the MCP tool call fails.
        ValueError: If GitHub is not configured.
    """
    if not settings.is_github_configured:
        raise ValueError("GitHub client is not fully configured")

    env = {
        "GITHUB_TOKEN": settings.github_token,
        "GITHUB_REPO_OWNER": settings.github_repo_owner,
        "GITHUB_REPO_NAME": settings.github_repo_name,
        "EVIDENCE_LOOKBACK_HOURS": str(settings.evidence_lookback_hours),
        "PYTHONIOENCODING": "utf-8",
        "AI_INCIDENT_COMMANDER_MCP_SERVER": "1",
    }
    log = logger.bind(service=service, tool=GITHUB_MCP_TOOL)
    log.info("github_mcp_fetch_started")

    payload = await call_stdio_tool(
        module=GITHUB_MCP_MODULE,
        tool_name=GITHUB_MCP_TOOL,
        arguments={"service": service},
        env=env,
    )
    commits = [CommitEvidence.model_validate(item) for item in payload]
    log.info("github_mcp_fetch_completed", count=len(commits))
    return commits
