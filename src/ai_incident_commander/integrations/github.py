"""GitHub API client for commit evidence collection."""

from datetime import UTC, datetime, timedelta

import httpx
import structlog

from ai_incident_commander.config import Settings
from ai_incident_commander.models.evidence import CommitEvidence

logger = structlog.get_logger(__name__)

GITHUB_API_BASE_URL = "https://api.github.com"


class GitHubClientError(Exception):
    """Raised when the GitHub API returns an error response."""


class GitHubClient:
    """Fetch recent commits from a GitHub repository."""

    def __init__(self, settings: Settings) -> None:
        """
        Initialize the client with GitHub credentials and repo coordinates.

        Args:
            settings: Application settings containing token and repository fields.
        """
        self._token = settings.github_token
        self._owner = settings.github_repo_owner
        self._repo = settings.github_repo_name
        self._lookback_hours = settings.evidence_lookback_hours

    @property
    def is_configured(self) -> bool:
        """Return True when token and repository coordinates are set."""
        return bool(self._token and self._owner and self._repo)

    async def get_recent_commits(self, service: str) -> list[CommitEvidence]:
        """
        Fetch commits from the configured repo within the lookback window.

        Args:
            service: Affected service name (logged for context; not used in query).

        Returns:
            List of ``CommitEvidence`` ordered newest-first.

        Raises:
            GitHubClientError: If the GitHub API request fails.
            ValueError: If required configuration is missing.
        """
        if not self.is_configured:
            raise ValueError("GitHub client is not fully configured")

        since = datetime.now(UTC) - timedelta(hours=self._lookback_hours)
        since_iso = since.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        url = f"{GITHUB_API_BASE_URL}/repos/{self._owner}/{self._repo}/commits"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        params = {"since": since_iso, "per_page": "20"}

        log = logger.bind(service=service, owner=self._owner, repo=self._repo)
        log.info("github_fetch_commits_started")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=params)

        if response.status_code != 200:
            log.error("github_fetch_commits_failed", status_code=response.status_code)
            raise GitHubClientError(
                f"GitHub API returned {response.status_code} for {self._owner}/{self._repo}"
            )

        payload = response.json()
        commits = [_map_commit(item, self._owner, self._repo) for item in payload]
        log.info("github_fetch_commits_completed", count=len(commits))
        return commits


def _map_commit(item: dict, owner: str, repo: str) -> CommitEvidence:
    """
    Map a GitHub commits API payload item to ``CommitEvidence``.

    Args:
        item: Single commit object from the GitHub API.
        owner: Repository owner for building commit URLs.
        repo: Repository name for building commit URLs.

    Returns:
        Normalized ``CommitEvidence`` instance.
    """
    sha = item.get("sha", "")
    commit = item.get("commit", {})
    message = (commit.get("message") or "").split("\n", maxsplit=1)[0]
    author_info = commit.get("author") or {}
    author = author_info.get("email") or author_info.get("name") or "unknown"
    committed_at = author_info.get("date")
    age_minutes = _minutes_since(committed_at)
    short_sha = sha[:7] if sha else ""
    url = f"https://github.com/{owner}/{repo}/commit/{sha}" if sha else ""

    return CommitEvidence(
        sha=short_sha,
        message=message,
        author=author,
        age_minutes=age_minutes,
        url=url,
    )


def _minutes_since(iso_timestamp: str | None) -> int:
    """
    Compute whole minutes elapsed since an ISO-8601 timestamp.

    Args:
        iso_timestamp: Git commit author date string, or ``None``.

    Returns:
        Minutes since the timestamp, or ``0`` when parsing fails.
    """
    if not iso_timestamp:
        return 0

    normalized = iso_timestamp.replace("Z", "+00:00")
    try:
        committed = datetime.fromisoformat(normalized)
    except ValueError:
        return 0

    if committed.tzinfo is None:
        committed = committed.replace(tzinfo=UTC)

    delta = datetime.now(UTC) - committed.astimezone(UTC)
    return max(int(delta.total_seconds() // 60), 0)
