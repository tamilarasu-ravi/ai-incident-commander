"""FastAPI application entrypoint for local development and deployment."""

from contextlib import asynccontextmanager

from urllib.parse import urlparse

import structlog
from fastapi import FastAPI, Request
from slack_bolt.adapter.fastapi import SlackRequestHandler

from ai_incident_commander.config import get_settings
from ai_incident_commander.db.session import init_database
from ai_incident_commander.db.url import database_connection_hint, resolve_database_url
from ai_incident_commander.integrations.credentials import validate_startup_credentials
from ai_incident_commander.logging_setup import configure_logging
from ai_incident_commander.server.routes.pagerduty import router as pagerduty_router
from ai_incident_commander.slack.app import get_slack_app, start_socket_mode, stop_socket_mode
from ai_incident_commander.store.investigations import configure_investigation_store

configure_logging(get_settings().log_level)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """
    Manage application startup and shutdown hooks.

    Args:
        _: FastAPI application instance (unused).

    Yields:
        Control to the running application between startup and shutdown.
    """
    settings = get_settings()
    validate_startup_credentials(settings)
    start_socket_mode(settings)
    log = structlog.get_logger(__name__)
    if settings.is_database_configured:
        resolved_url = resolve_database_url(settings.database_url)
        try:
            await init_database(resolved_url)
            configure_investigation_store(use_postgres=True, database_url=resolved_url)
            log.info(
                "database_ready",
                backend="postgresql",
                database_host=urlparse(resolved_url).hostname,
                hint="Investigations persist across restarts",
            )
        except Exception as error:
            configure_investigation_store(use_postgres=False)
            log.warning(
                "database_connection_failed",
                error=str(error),
                hint=database_connection_hint(settings.database_url),
                fallback="pickle",
            )
    else:
        configure_investigation_store(use_postgres=False)
    yield
    stop_socket_mode()


api = FastAPI(
    title="AI Incident Commander",
    description="Slack-native RCA investigation agent",
    version="0.1.0",
    lifespan=lifespan,
)
api.include_router(pagerduty_router)


async def _handle_slack_request(request: Request):
    """Dispatch Slack HTTP payloads (interactivity, slash commands, events) to Bolt."""
    settings = get_settings()
    if not settings.slack_signing_secret:
        return {"ok": False, "error": "SLACK_SIGNING_SECRET is not configured"}
    handler = SlackRequestHandler(get_slack_app(settings))
    return await handler.handle(request)


@api.post("/slack/events")
async def slack_events(request: Request):
    """
    Handle Slack interactivity and events over HTTP.

    Point your app's Interactivity Request URL here when not relying solely on
    Socket Mode, or when Slack delivers block_actions to the HTTP endpoint.
    """
    return await _handle_slack_request(request)


@api.post("/slack/commands")
async def slack_commands(request: Request):
    """
    Handle slash commands over HTTP.

    If your Slack app has a Slash Command Request URL set, point it here so
    `/incident` and button clicks use the same server process and store.
    """
    return await _handle_slack_request(request)


@api.get("/health")
def health_check() -> dict[str, str]:
    """
    Return service health for Docker and load balancer probes.

    Returns:
        JSON object with ``status`` set to ``ok``.
    """
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "ai_incident_commander.server.main:api",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
