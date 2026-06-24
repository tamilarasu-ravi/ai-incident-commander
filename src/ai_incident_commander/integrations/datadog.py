"""Datadog API client for log evidence collection."""

from collections import Counter
from datetime import UTC, datetime, timedelta

import httpx
import structlog

from ai_incident_commander.config import Settings
from ai_incident_commander.integrations.query_escape import format_datadog_service_filter
from ai_incident_commander.models.evidence import LogClusterEvidence

logger = structlog.get_logger(__name__)


class DatadogClientError(Exception):
    """Raised when the Datadog API returns an error response."""


class DatadogClient:
    """Search error logs in Datadog for a given service."""

    def __init__(self, settings: Settings) -> None:
        """
        Initialize the client with Datadog credentials and site configuration.

        Args:
            settings: Application settings containing Datadog API keys and site.
        """
        self._api_key = settings.datadog_api_key
        self._app_key = settings.datadog_app_key
        self._site = settings.datadog_site
        self._log_index = settings.datadog_log_index
        self._lookback_hours = settings.evidence_lookback_hours

    @property
    def is_configured(self) -> bool:
        """Return True when API and application keys are set."""
        return bool(self._api_key and self._app_key)

    @property
    def api_base_url(self) -> str:
        """Return the Datadog API base URL for the configured site."""
        if self._site.startswith("http"):
            return self._site.rstrip("/")
        return f"https://api.{self._site}"

    async def get_log_clusters(self, service: str) -> list[LogClusterEvidence]:
        """
        Search error logs for a service and aggregate them into clusters.

        Args:
            service: Affected service name used in the Datadog query.

        Returns:
            List of ``LogClusterEvidence`` sorted by count descending.

        Raises:
            DatadogClientError: If the Datadog logs search API fails.
            ValueError: If required configuration is missing.
        """
        if not self.is_configured:
            raise ValueError("Datadog client is not fully configured")

        now = datetime.now(UTC)
        start = now - timedelta(hours=self._lookback_hours)
        url = f"{self.api_base_url}/api/v2/logs/events/search"
        headers = {
            "DD-API-KEY": self._api_key,
            "DD-APPLICATION-KEY": self._app_key,
            "Content-Type": "application/json",
        }
        body = {
            "filter": {
                "from": start.isoformat(),
                "to": now.isoformat(),
                "query": f"{format_datadog_service_filter(service)} status:error",
                "indexes": [self._log_index],
            },
            "page": {"limit": 50},
        }

        log = logger.bind(service=service, site=self._site, index=self._log_index)
        log.info("datadog_search_logs_started")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=body)

        if response.status_code != 200:
            log.error("datadog_search_logs_failed", status_code=response.status_code)
            raise DatadogClientError(
                f"Datadog logs search returned {response.status_code} for service:{service}"
            )

        payload = response.json()
        clusters = _aggregate_log_clusters(payload, service)
        log.info("datadog_search_logs_completed", cluster_count=len(clusters))
        return clusters


def _aggregate_log_clusters(payload: dict, service: str) -> list[LogClusterEvidence]:
    """
    Aggregate raw Datadog log events into message clusters with counts.

    Args:
        payload: Datadog logs search API response body.
        service: Service name attached to each cluster.

    Returns:
        Top log clusters sorted by descending count.
    """
    messages: list[str] = []
    for item in payload.get("data", []):
        attributes = item.get("attributes", {})
        message = attributes.get("message") or attributes.get("status")
        if message:
            messages.append(str(message).strip())

    counts = Counter(messages)
    clusters = [
        LogClusterEvidence(message=message, count=count, service=service, status="error")
        for message, count in counts.most_common(10)
    ]
    return clusters
