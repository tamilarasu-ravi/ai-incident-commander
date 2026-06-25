"""Tests for Datadog integration client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_incident_commander.config import Settings
from ai_incident_commander.integrations.datadog import DatadogClient, DatadogClientError
from tests.conftest import TEST_DATADOG_API_KEY, TEST_DATADOG_APP_KEY


@pytest.fixture
def datadog_settings(make_settings):
    """Settings with Datadog credentials configured for AP1."""
    return make_settings(
        datadog_api_key=TEST_DATADOG_API_KEY,
        datadog_app_key=TEST_DATADOG_APP_KEY,
        datadog_site="ap1.datadoghq.com",
    )


def test_datadog_client_api_base_url(datadog_settings: Settings) -> None:
    """AP1 site resolves to the correct Datadog API host."""
    client = DatadogClient(datadog_settings)
    assert client.api_base_url == "https://api.ap1.datadoghq.com"


def test_datadog_client_is_configured(datadog_settings: Settings) -> None:
    """Client reports configured when both keys are present."""
    assert DatadogClient(datadog_settings).is_configured is True


async def test_get_log_clusters_aggregates_messages(datadog_settings: Settings) -> None:
    """Datadog log events are grouped into clusters by message."""
    api_payload = {
        "data": [
            {"attributes": {"message": "Redis connection pool exhausted", "status": "error"}},
            {"attributes": {"message": "Redis connection pool exhausted", "status": "error"}},
            {"attributes": {"message": "Timeout waiting for Redis connection", "status": "error"}},
        ]
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = api_payload

    mock_http = AsyncMock()
    mock_http.post.return_value = mock_response
    mock_http.__aenter__.return_value = mock_http
    mock_http.__aexit__.return_value = None

    with patch("ai_incident_commander.integrations.datadog.httpx.AsyncClient", return_value=mock_http):
        clusters = await DatadogClient(datadog_settings).get_log_clusters("checkout-service")

    assert len(clusters) == 2
    assert clusters[0].message == "Redis connection pool exhausted"
    assert clusters[0].count == 2
    assert clusters[0].service == "checkout-service"


async def test_get_log_clusters_escapes_service_in_query(datadog_settings: Settings) -> None:
    """Service names with quotes are escaped in the Datadog log query."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": []}

    mock_http = AsyncMock()
    mock_http.post.return_value = mock_response
    mock_http.__aenter__.return_value = mock_http
    mock_http.__aexit__.return_value = None

    malicious_service = 'evil" OR service:admin'

    with patch("ai_incident_commander.integrations.datadog.httpx.AsyncClient", return_value=mock_http):
        await DatadogClient(datadog_settings).get_log_clusters(malicious_service)

    query = mock_http.post.call_args.kwargs["json"]["filter"]["query"]
    assert query == 'service:"evil\\" OR service:admin" status:error'


async def test_get_log_clusters_raises_on_api_error(datadog_settings: Settings) -> None:
    """Non-200 Datadog responses raise DatadogClientError."""
    mock_response = MagicMock()
    mock_response.status_code = 403

    mock_http = AsyncMock()
    mock_http.post.return_value = mock_response
    mock_http.__aenter__.return_value = mock_http
    mock_http.__aexit__.return_value = None

    with patch("ai_incident_commander.integrations.datadog.httpx.AsyncClient", return_value=mock_http):
        with pytest.raises(DatadogClientError):
            await DatadogClient(datadog_settings).get_log_clusters("checkout-service")
