"""FastAPI application entrypoint for local development and deployment."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from ai_incident_commander.server.routes.pagerduty import router as pagerduty_router
from ai_incident_commander.slack.app import start_socket_mode, stop_socket_mode


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
