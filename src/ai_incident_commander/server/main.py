"""FastAPI application entrypoint for local development and deployment."""

from fastapi import FastAPI

api = FastAPI(
    title="AI Incident Commander",
    description="Slack-native RCA investigation agent",
    version="0.1.0",
)


@api.get("/health")
def health_check() -> dict[str, str]:
    """Return service health for Docker and load balancer probes."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "ai_incident_commander.server.main:api",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
