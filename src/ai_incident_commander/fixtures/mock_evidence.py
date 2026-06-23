"""Mock evidence fixtures for Day 2 development and demo runs."""

from ai_incident_commander.models.eval_result import EvalResult
from ai_incident_commander.models.evidence import (
    CommitEvidence,
    DeploymentEvidence,
    EvidenceBundle,
    LogClusterEvidence,
    PriorIncidentEvidence,
)

DEMO_SERVICE_NAME = "checkout-service"
NULL_DEPLOY_SERVICE_NAME = "payment-service"
FLAKY_TEST_SERVICE_NAME = "auth-service"

REDIS_POOL_EXHAUSTION_BUNDLE = EvidenceBundle(
    commits=[
        CommitEvidence(
            sha="abc123",
            message="fix: increase redis max connections for checkout-service",
            author="dev@example.com",
            age_minutes=14,
            url="https://github.com/example/checkout-service/commit/abc123",
        ),
        CommitEvidence(
            sha="def456",
            message="chore: bump checkout-service dependency versions",
            author="dev@example.com",
            age_minutes=45,
        ),
        CommitEvidence(
            sha="ghi789",
            message="feat: add retry logic to payment gateway client",
            author="dev@example.com",
            age_minutes=72,
        ),
        CommitEvidence(
            sha="jkl012",
            message="docs: update checkout-service runbook",
            author="dev@example.com",
            age_minutes=110,
        ),
    ],
    log_clusters=[
        LogClusterEvidence(
            message="Redis connection pool exhausted: max connections reached",
            count=847,
            service=DEMO_SERVICE_NAME,
        ),
        LogClusterEvidence(
            message="Timeout waiting for Redis connection from pool",
            count=312,
            service=DEMO_SERVICE_NAME,
        ),
        LogClusterEvidence(
            message="checkout-service latency p99 exceeded 2000ms threshold",
            count=156,
            service=DEMO_SERVICE_NAME,
        ),
    ],
    prior_incidents=[
        PriorIncidentEvidence(
            incident_id="SCRUM-1",
            summary="Redis connection pool exhaustion on checkout-service",
            service=DEMO_SERVICE_NAME,
        ),
    ],
    deployments=[
        DeploymentEvidence(
            deployment_id="deploy-8821",
            environment="production",
            service=DEMO_SERVICE_NAME,
            deployed_at_minutes_ago=18,
        ),
    ],
)

NULL_DEPLOY_BUNDLE = EvidenceBundle(
    commits=[
        CommitEvidence(
            sha="null01",
            message="chore: empty deploy artifact for payment-service",
            author="dev@example.com",
            age_minutes=22,
        ),
        CommitEvidence(
            sha="null02",
            message="ci: retry failed payment-service pipeline",
            author="dev@example.com",
            age_minutes=40,
        ),
    ],
)

FLAKY_TEST_BUNDLE = EvidenceBundle(
    commits=[
        CommitEvidence(
            sha="flk001",
            message="test: mark auth integration suite as flaky",
            author="dev@example.com",
            age_minutes=30,
        ),
    ],
    log_clusters=[
        LogClusterEvidence(
            message="auth-service integration test failed: expected 200 got 500",
            count=12,
            service=FLAKY_TEST_SERVICE_NAME,
        ),
        LogClusterEvidence(
            message="auth-service test retry passed on second attempt",
            count=11,
            service=FLAKY_TEST_SERVICE_NAME,
        ),
    ],
)

REDIS_POOL_STUB_EVAL = EvalResult.from_component_scores(
    evidence_coverage=0.85,
    grounding_score=0.85,
    consistency=0.95,
)

_FIXTURES_BY_SERVICE = {
    DEMO_SERVICE_NAME: REDIS_POOL_EXHAUSTION_BUNDLE,
    NULL_DEPLOY_SERVICE_NAME: NULL_DEPLOY_BUNDLE,
    FLAKY_TEST_SERVICE_NAME: FLAKY_TEST_BUNDLE,
}


def get_fixture_evidence(service: str) -> EvidenceBundle | None:
    """
    Return mock evidence for a known demo service name.

    Args:
        service: Affected service from the slash command or webhook.

    Returns:
        ``EvidenceBundle`` when a fixture exists, otherwise ``None``.
    """
    return _FIXTURES_BY_SERVICE.get(service.strip().lower())


def get_stub_eval_result(service: str) -> EvalResult | None:
    """
    Return stub eval scores for a known demo service name.

    Args:
        service: Affected service from the slash command or webhook.

    Returns:
        ``EvalResult`` when a fixture exists, otherwise ``None``.
    """
    if service.strip().lower() == DEMO_SERVICE_NAME:
        return REDIS_POOL_STUB_EVAL
    return None
