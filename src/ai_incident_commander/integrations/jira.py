"""Jira API client for prior incident search."""

import base64

import httpx
import structlog

from ai_incident_commander.config import Settings
from ai_incident_commander.models.evidence import PriorIncidentEvidence
from ai_incident_commander.models.investigation import InvestigationState

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
        self._issue_type = settings.jira_issue_type

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

    async def create_incident_ticket(self, state: InvestigationState) -> str:
        """
        Create a Jira incident ticket from an approved investigation.

        Args:
            state: Surfaced investigation state with RCA and eval results.

        Returns:
            Created Jira issue key such as ``SCRUM-42``.

        Raises:
            JiraClientError: If the Jira create issue API fails.
            ValueError: If required configuration or investigation fields are missing.
        """
        if not self.is_configured:
            raise ValueError("Jira client is not fully configured")

        rca = state.get("rca")
        evidence = state.get("evidence")
        eval_result = state.get("eval_result")
        if rca is None or evidence is None or eval_result is None:
            raise ValueError("Approved investigations require rca, evidence, and eval_result")

        service = state["service"]
        summary = _build_issue_summary(service, rca.root_cause_candidate)
        description = _build_issue_description(state)
        url = f"{self._base_url}/rest/api/3/issue"
        headers = {
            **_auth_headers(self._email, self._token),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        body = {
            "fields": {
                "project": {"key": self._project_key},
                "summary": summary,
                "description": _text_to_adf(description),
                "issuetype": {"name": self._issue_type},
            }
        }

        log = logger.bind(service=service, project=self._project_key)
        log.info("jira_create_issue_started")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=body)

        if response.status_code not in {200, 201}:
            log.error("jira_create_issue_failed", status_code=response.status_code)
            raise JiraClientError(
                f"Jira create issue returned {response.status_code} for project {self._project_key}"
            )

        payload = response.json()
        issue_key = payload.get("key", "")
        log.info("jira_create_issue_completed", issue_key=issue_key)
        return issue_key


def _build_issue_summary(service: str, root_cause: str) -> str:
    """Build a concise Jira issue summary from service and root cause."""
    summary = f"RCA: {root_cause} on {service}"
    return summary[:255]


def _build_issue_description(state: InvestigationState) -> str:
    """Build a plain-text Jira issue description from investigation state."""
    rca = state.get("rca")
    evidence = state.get("evidence")
    eval_result = state.get("eval_result")
    if rca is None or evidence is None or eval_result is None:
        raise ValueError("Approved investigations require rca, evidence, and eval_result")

    lines = [
        f"Service: {state['service']}",
        f"Description: {state['description']}",
        f"Investigation ID: {state.get('investigation_id', 'unknown')}",
        "",
        "Root Cause Candidate:",
        rca.root_cause_candidate,
        "",
        f"Supporting Commit: {rca.supporting_commit} ({rca.commit_age_minutes} min ago)",
        f"Prior Incident Match: {rca.prior_incident_match or 'none'}",
        "",
        "Confidence Breakdown:",
        f"- Evidence coverage: {eval_result.evidence_coverage:.0%}",
        f"- Grounding: {eval_result.grounding_score:.0%}",
        f"- Consistency: {eval_result.consistency:.0%}",
        f"- Overall confidence: {eval_result.confidence:.0%}",
        "",
        "Evidence Summary:",
        f"- Commits: {len(evidence.commits)}",
        f"- Log clusters: {len(evidence.log_clusters)}",
        f"- Prior incidents: {len(evidence.prior_incidents)}",
        f"- Deployments: {len(evidence.deployments)}",
    ]

    for commit in evidence.commits[:5]:
        lines.append(f"  - {commit.sha}: {commit.message}")
    for cluster in evidence.log_clusters[:5]:
        lines.append(f"  - [{cluster.count}x] {cluster.message}")

    return "\n".join(lines)


def _text_to_adf(text: str) -> dict:
    """
    Convert plain text into Atlassian Document Format for Jira Cloud.

    Args:
        text: Multi-line plain-text description.

    Returns:
        ADF document payload.
    """
    paragraphs = []
    for line in text.splitlines():
        if line.strip():
            paragraphs.append(
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": line}],
                }
            )
    if not paragraphs:
        paragraphs.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "No details provided."}],
            }
        )
    return {"type": "doc", "version": 1, "content": paragraphs}


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
