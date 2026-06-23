"""Orchestrates parallel evidence collection from external integrations."""

import asyncio

import structlog

from ai_incident_commander.config import Settings
from ai_incident_commander.constants import INTEGRATION_FETCH_TIMEOUT_SECONDS
from ai_incident_commander.fixtures.mock_evidence import get_fixture_evidence
from ai_incident_commander.integrations.datadog import DatadogClient
from ai_incident_commander.integrations.github import GitHubClient
from ai_incident_commander.models.evidence import EvidenceBundle

logger = structlog.get_logger(__name__)


async def collect_live_evidence(service: str, settings: Settings) -> EvidenceBundle:
    """
    Collect evidence from GitHub and Datadog in parallel with fixture supplements.

    Live clients populate commits and log clusters. Prior incidents and deployments
    remain fixture-backed until Day 4 (Jira + RTS).

    Args:
        service: Affected service name from the incident trigger.
        settings: Application settings with integration credentials.

    Returns:
        Merged ``EvidenceBundle`` with live and supplemental evidence.

    Raises:
        ValueError: If no evidence could be collected from any source.
    """
    github_client = GitHubClient(settings)
    datadog_client = DatadogClient(settings)
    fixture = get_fixture_evidence(service)

    commits: list = []
    log_clusters: list = []
    prior_incidents = fixture.prior_incidents if fixture else []
    deployments = fixture.deployments if fixture else []

    tasks: dict[str, asyncio.Task] = {}
    if github_client.is_configured:
        tasks["github"] = asyncio.create_task(
            _fetch_with_timeout(github_client.get_recent_commits(service), "github")
        )
    if datadog_client.is_configured:
        tasks["datadog"] = asyncio.create_task(
            _fetch_with_timeout(datadog_client.get_log_clusters(service), "datadog")
        )

    if tasks:
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for source, result in zip(tasks.keys(), results, strict=True):
            if isinstance(result, Exception):
                logger.warning(
                    "evidence_source_failed",
                    source=source,
                    service=service,
                    error=str(result),
                )
                continue
            if source == "github":
                commits = result
            elif source == "datadog":
                log_clusters = result

    if not commits and fixture:
        commits = fixture.commits
        logger.info("evidence_github_fixture_fallback", service=service)

    if not log_clusters and fixture:
        log_clusters = fixture.log_clusters
        logger.info("evidence_datadog_fixture_fallback", service=service)

    bundle = EvidenceBundle(
        commits=commits,
        log_clusters=log_clusters,
        prior_incidents=prior_incidents,
        deployments=deployments,
    )

    if not bundle.has_commit() and not bundle.has_log_cluster():
        raise ValueError(
            f"No evidence collected for service '{service}'. "
            "Configure GitHub and Datadog credentials or use checkout-service demo fixtures."
        )

    return bundle


async def _fetch_with_timeout(coro, source: str):
    """
    Await an integration coroutine with a configured timeout.

    Args:
        coro: Awaitable integration fetch coroutine.
        source: Integration name for timeout error messages.

    Returns:
        Result of the coroutine.

    Raises:
        TimeoutError: If the fetch exceeds ``INTEGRATION_FETCH_TIMEOUT_SECONDS``.
    """
    try:
        return await asyncio.wait_for(coro, timeout=INTEGRATION_FETCH_TIMEOUT_SECONDS)
    except TimeoutError as error:
        raise TimeoutError(f"{source} evidence fetch timed out") from error
