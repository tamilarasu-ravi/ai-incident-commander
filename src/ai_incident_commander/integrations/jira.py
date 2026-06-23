"""Jira API client for prior incident search."""

import base64

import httpx
import structlog

from ai_incident_commander.config import Settings
from ai_incident_commander.models.evidence import PriorIncidentEvidence

logger = structlog.get_logger(__name__)


class JiraClientError(Exception):
    """Raised when the Jira API returns an error response."""


class JiraClient:
    """Search historical incident tickets in Jira."""

    def __init__(self, settings: Settings) -> None:
        """
        Initialize the client with Jira credentials and project configuration.

        Args:
            settings: Application settings containing Jira API credentials.
        """
        self._token = settings.jira_api_token
        self._email = settings.jira_email
        self._base_url = settings.jira_base_url.rstrip("/")
        self._project_key = settings.jira_project_key

    @property
    def is_configured(self) -> bool:
        """Return True when token, email, and base URL are set."""
        return bool(self._token and self._email and self._base_url)

    async def get_prior_incidents(self, service: str, limit: int = 5) -> list[PriorIncidentEvidence]:
        """
        Search Jira for resolved incidents related to the affected service.

        Args:
            service: Affected service name used in JQL text search.
            limit: Maximum number of issues to return.

        Returns:
            List of ``PriorIncidentEvidence`` ordered by Jira search relevance.

        Raises:
            JiraClientError: If the Jira search API fails.
            ValueError: If required configuration is missing.
        """
        if not self.is_configured:
            raise ValueError("Jira client is not fully configured")

        jql = (
            f'project = {self._project_key} AND '
            f'(summary ~ "{service}" OR description ~ "{service}") '
            f"ORDER BY updated DESC"
        )
        url = f"{self._base_url}/rest/api/3/search"
        headers = {
            **_auth_headers(self._email, self._token),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        body = {
            "jql": jql,
            "maxResults": limit,
            "fields": ["summary", "status", "resolution"],
        }

        log = logger.bind(service=service, project=self._project_key)
        log.info("jira_search_incidents_started")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=body)

        if response.status_code != 200:
            log.error("jira_search_incidents_failed", status_code=response.status_code)
            raise JiraClientError(
                f"Jira search returned {response.status_code} for project {self._project_key}"
            )

        payload = response.json()
        incidents = [_map_issue(item, service) for item in payload.get("issues", [])]
        log.info("jira_search_incidents_completed", count=len(incidents))
        return incidents


def _auth_headers(email: str, api_token: str) -> dict[str, str]:
    """
    Build HTTP Basic auth headers for Jira Cloud API token authentication.

    Args:
        email: Atlassian account email.
        api_token: Jira API token.

    Returns:
        Authorization header dict.
    """
    credentials = f"{email}:{api_token}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


def _map_issue(item: dict, service: str) -> PriorIncidentEvidence:
    """
    Map a Jira search issue payload to ``PriorIncidentEvidence``.

    Args:
        item: Single issue object from the Jira search API.
        service: Affected service name attached to the evidence record.

    Returns:
        Normalized ``PriorIncidentEvidence`` instance.
    """
    fields = item.get("fields", {})
    status = fields.get("status") or {}
    status_category = status.get("statusCategory") or {}
    resolution = fields.get("resolution")
    resolved = resolution is not None or status_category.get("key") == "done"

    return PriorIncidentEvidence(
        incident_id=item.get("key", ""),
        summary=fields.get("summary") or "",
        service=service,
        resolved=resolved,
    )
