"""Slack Real-Time Search and channel history fallback for prior incidents."""

import asyncio
import re
from datetime import UTC, datetime, timedelta

import structlog
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from ai_incident_commander.config import Settings
from ai_incident_commander.constants import RTS_LOOKBACK_DAYS
from ai_incident_commander.models.evidence import PriorIncidentEvidence
from ai_incident_commander.slack.client import create_slack_web_client

logger = structlog.get_logger(__name__)

INCIDENT_ID_PATTERN = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "for",
        "in",
        "on",
        "or",
        "the",
        "to",
        "with",
    }
)


class RtsClientError(Exception):
    """Raised when Slack search APIs return an error response."""


class RtsClient:
    """Search Slack incident channel history for prior incident references."""

    def __init__(self, settings: Settings, slack_client: WebClient | None = None) -> None:
        """
        Initialize the client with Slack credentials and optional WebClient.

        Args:
            settings: Application settings with bot token and incidents channel ID.
            slack_client: Optional pre-built Slack WebClient for testing or reuse.
        """
        self._settings = settings
        self._channel_id = settings.incidents_channel_id
        self._client = slack_client

    @property
    def is_configured(self) -> bool:
        """Return True when bot token and incidents channel ID are set."""
        return bool(self._settings.slack_bot_token and self._channel_id)

    async def search_incident_context(
        self,
        service: str,
        description: str,
        limit: int = 5,
    ) -> list[PriorIncidentEvidence]:
        """
        Search Slack for prior incident context related to the service and alert.

        Tries ``assistant.search.context`` first, then falls back to
        ``conversations.history`` scoped to the incidents channel.

        Args:
            service: Affected service name.
            description: Free-text incident description for keyword matching.
            limit: Maximum number of prior incidents to return.

        Returns:
            Deduplicated list of ``PriorIncidentEvidence`` parsed from messages.

        Raises:
            ValueError: If required Slack configuration is missing.
        """
        if not self.is_configured:
            raise ValueError("RTS client is not fully configured")

        query = _build_search_query(service, description)
        log = logger.bind(service=service, channel_id=self._channel_id)
        log.info("rts_search_started", query=query)

        try:
            results = await asyncio.to_thread(self._search_via_rts_api, query, service, limit)
            if results:
                log.info(
                    "rts_search_completed",
                    source="assistant.search.context",
                    count=len(results),
                )
                return results
        except (SlackApiError, RtsClientError) as error:
            log.warning("rts_api_failed", error=str(error))

        results = await asyncio.to_thread(
            self._search_channel_history,
            service,
            description,
            limit,
        )
        log.info("rts_search_completed", source="conversations.history", count=len(results))
        return results

    def _get_client(self) -> WebClient:
        """Return the injected or lazily created Slack WebClient."""
        if self._client is None:
            self._client = create_slack_web_client(self._settings.slack_bot_token)
        return self._client

    def _search_via_rts_api(
        self,
        query: str,
        service: str,
        limit: int,
    ) -> list[PriorIncidentEvidence]:
        """
        Search Slack via the Real-Time Search API.

        Args:
            query: RTS query string.
            service: Affected service name for evidence mapping.
            limit: Maximum incidents to return.

        Returns:
            Parsed prior incidents from RTS message hits.

        Raises:
            RtsClientError: If the RTS API response is not successful.
            SlackApiError: If the Slack API call fails.
        """
        client = self._get_client()
        response = client.api_call(
            api_method="assistant.search.context",
            json={
                "query": query,
                "context_channel_id": self._channel_id,
                "channel_types": ["public_channel"],
                "content_types": ["messages"],
                "limit": limit,
            },
        )
        if not response.get("ok"):
            raise RtsClientError(response.get("error", "assistant.search.context failed"))

        messages = _extract_messages_from_rts_response(response.data)
        return _parse_messages_to_incidents(messages, service, limit)

    def _search_channel_history(
        self,
        service: str,
        description: str,
        limit: int,
    ) -> list[PriorIncidentEvidence]:
        """
        Search channel history locally when RTS is unavailable.

        Args:
            service: Affected service name.
            description: Incident description used for keyword matching.
            limit: Maximum incidents to return.

        Returns:
            Parsed prior incidents from matching channel messages.
        """
        client = self._get_client()
        oldest = str((datetime.now(UTC) - timedelta(days=RTS_LOOKBACK_DAYS)).timestamp())
        response = client.conversations_history(
            channel=self._channel_id,
            oldest=oldest,
            limit=200,
        )
        if not response.get("ok"):
            raise RtsClientError(response.get("error", "conversations.history failed"))

        keywords = _extract_keywords(service, description)
        matched_messages: list[str] = []
        for message in response.get("messages", []):
            text = message.get("text") or ""
            if _message_matches(text, service, keywords):
                matched_messages.append(text)

        return _parse_messages_to_incidents(matched_messages, service, limit)


def _build_search_query(service: str, description: str) -> str:
    """
    Build an RTS query from service name and incident description keywords.

    Args:
        service: Affected service name.
        description: Free-text incident description.

    Returns:
        Space-joined query string for Slack search.
    """
    keywords = _extract_keywords(service, description)
    return " ".join([service, *keywords[:5]])


def _extract_keywords(service: str, description: str) -> list[str]:
    """
    Extract lowercase keywords from service and description for local matching.

    Args:
        service: Affected service name.
        description: Free-text incident description.

    Returns:
        Unique keywords excluding stop words.
    """
    tokens = re.split(r"[^\w-]+", f"{service} {description}".lower())
    seen: set[str] = set()
    keywords: list[str] = []
    for token in tokens:
        if len(token) < 3 or token in STOP_WORDS or token in seen:
            continue
        seen.add(token)
        keywords.append(token)
    return keywords


def _message_matches(text: str, service: str, keywords: list[str]) -> bool:
    """
    Return True when a message mentions the service or enough alert keywords.

    Args:
        text: Slack message text.
        service: Affected service name.
        keywords: Keywords extracted from the incident description.

    Returns:
        Whether the message is relevant to the investigation.
    """
    lowered = text.lower()
    if service.lower() in lowered:
        return True
    return sum(1 for keyword in keywords if keyword in lowered) >= 2


def _extract_messages_from_rts_response(payload: dict) -> list[str]:
    """
    Extract message text snippets from an RTS API response payload.

    Args:
        payload: Slack API response body.

    Returns:
        List of message text strings.
    """
    messages: list[str] = []
    candidates = payload.get("messages") or payload.get("results", {}).get("messages", [])
    for item in candidates:
        if isinstance(item, str):
            messages.append(item)
            continue
        text = item.get("text") or item.get("content") or ""
        if text:
            messages.append(text)
    return messages


def _parse_messages_to_incidents(
    messages: list[str],
    service: str,
    limit: int,
) -> list[PriorIncidentEvidence]:
    """
    Parse Jira-style incident IDs from Slack messages into evidence records.

    Args:
        messages: Slack message bodies to scan.
        service: Affected service name attached to each record.
        limit: Maximum incidents to return.

    Returns:
        Deduplicated prior incidents preserving first-seen order.
    """
    incidents: list[PriorIncidentEvidence] = []
    seen_ids: set[str] = set()

    for text in messages:
        for match in INCIDENT_ID_PATTERN.finditer(text):
            incident_id = match.group(0)
            if incident_id in seen_ids:
                continue
            seen_ids.add(incident_id)
            incidents.append(
                PriorIncidentEvidence(
                    incident_id=incident_id,
                    summary=_summarize_message(text),
                    service=service,
                    resolved=True,
                )
            )
            if len(incidents) >= limit:
                return incidents

    return incidents


def _summarize_message(text: str) -> str:
    """
    Build a short summary from the first meaningful line of a Slack message.

    Args:
        text: Full Slack message body.

    Returns:
        Single-line summary capped at 200 characters.
    """
    for line in text.splitlines():
        cleaned = line.strip()
        if cleaned:
            return cleaned[:200]
    return text.strip()[:200]
