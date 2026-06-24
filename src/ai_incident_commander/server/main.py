"""FastAPI application entrypoint for local development and deployment."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from slack_bolt.adapter.fastapi import SlackRequestHandler

from ai_incident_commander.config import get_settings
from ai_incident_commander.logging_setup import configure_logging
from ai_incident_commander.server.routes.pagerduty import router as pagerduty_router
from ai_incident_commander.slack.app import get_slack_app, start_socket_mode, stop_socket_mode

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
    start_socket_mode()
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
