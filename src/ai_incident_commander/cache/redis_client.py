"""Optional Redis client for shared queue and deduplication state."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import structlog

from ai_incident_commander.config import get_settings

if TYPE_CHECKING:
    from redis import Redis

logger = structlog.get_logger(__name__)

_client: "Redis[str] | None" = None
_lock = threading.Lock()


def get_redis_client() -> "Redis[str] | None":
    """
    Return a shared Redis client when ``REDIS_URL`` is configured.

    Returns:
        Redis client instance, or ``None`` when Redis is not configured.
    """
    global _client

    settings = get_settings()
    if not settings.redis_url:
        return None

    with _lock:
        if _client is not None:
            return _client

        try:
            import redis
        except ImportError:
            logger.warning("redis_package_missing")
            return None

        _client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=5,
        )
        try:
            _client.ping()
        except Exception:
            logger.exception("redis_ping_failed")
            _client = None
            return None

        logger.info("redis_client_ready")
        return _client


def reset_redis_client() -> None:
    """Reset the cached Redis client — intended for tests."""
    global _client
    with _lock:
        _client = None
