"""Tests for mock evidence fixtures."""

import pytest

from tests.fixtures import (
    DEMO_SERVICE_NAME,
    REDIS_POOL_EXHAUSTION_BUNDLE,
    REDIS_POOL_STUB_EVAL,
    get_fixture_evidence,
    get_stub_eval_result,
)


def test_redis_fixture_has_required_evidence_types() -> None:
    """Redis demo fixture includes commits, logs, and prior incident."""
    bundle = REDIS_POOL_EXHAUSTION_BUNDLE
    assert bundle.has_commit()
    assert bundle.has_log_cluster()
    assert bundle.has_prior_incident_or_deployment()
    assert len(bundle.commits) == 4
    assert len(bundle.log_clusters) == 3


def test_get_fixture_evidence_returns_checkout_service_bundle() -> None:
    """Known demo service resolves to the Redis exhaustion fixture."""
    bundle = get_fixture_evidence(DEMO_SERVICE_NAME)
    assert bundle is not None
    assert bundle.prior_incidents[0].incident_id == "SCRUM-1"


def test_get_fixture_evidence_returns_none_for_unknown_service() -> None:
    """Unknown services have no Day 2 mock evidence."""
    assert get_fixture_evidence("unknown-service") is None


def test_stub_eval_matches_readme_confidence() -> None:
    """Stub eval produces the readme demo confidence score."""
    assert REDIS_POOL_STUB_EVAL.confidence == pytest.approx(0.87)
    assert get_stub_eval_result(DEMO_SERVICE_NAME) is not None
