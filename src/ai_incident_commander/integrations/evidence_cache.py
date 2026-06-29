"""Short-lived evidence cache to reduce duplicate upstream calls."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any

import structlog

from ai_incident_commander.config import get_settings

logger = structlog.get_logger(__name__)

_memory_cache: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()
EVIDENCE_CACHE_PREFIX = "evidence_cache:"


def build_evidence_cache_key(service: str, description: str) -> str:
    """
    Build a stable cache key for collected evidence.

    Args:
        service: Affected service name.
        description: Incident description text.

    Returns:
        SHA-256 hex digest used as cache key suffix.
    """
    normalized = f"{service.strip().lower()}|{description.strip().lower()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def get_cached_evidence(service: str, description: str) -> Any | None:
    """
    Return cached evidence when present and not expired.

    Args:
        service: Affected service name.
        description: Incident description text.

    Returns:
        Cached evidence payload, or ``None`` on miss/expiry.
    """
    settings = get_settings()
    if not settings.evidence_cache_enabled:
        return None

    cache_key = build_evidence_cache_key(service, description)
    redis_value = _get_redis_cache(cache_key)
    if redis_value is not None:
        return redis_value

    return _get_memory_cache(cache_key, settings.evidence_cache_ttl_seconds)


def set_cached_evidence(service: str, description: str, evidence: Any) -> None:
    """
    Store evidence in cache with configured TTL.

    Args:
        service: Affected service name.
        description: Incident description text.
        evidence: Evidence payload to cache.
    """
    settings = get_settings()
    if not settings.evidence_cache_enabled:
        return

    cache_key = build_evidence_cache_key(service, description)
    if settings.redis_url:
        _set_redis_cache(cache_key, evidence, settings.evidence_cache_ttl_seconds)
        return

    expires_at = time.time() + settings.evidence_cache_ttl_seconds
    with _lock:
        _memory_cache[cache_key] = (expires_at, evidence)


def clear_evidence_cache() -> None:
    """Clear in-memory evidence cache — intended for tests."""
    with _lock:
        _memory_cache.clear()


def _get_memory_cache(cache_key: str, ttl_seconds: int) -> Any | None:
    """
    Read evidence from the in-memory cache.

    Args:
        cache_key: Stable evidence cache key.
        ttl_seconds: TTL used only for sanity checks on expiry timestamps.

    Returns:
        Cached evidence or ``None``.
    """
    now = time.time()
    with _lock:
        entry = _memory_cache.get(cache_key)
        if entry is None:
            return None
        expires_at, payload = entry
        if expires_at < now:
            _memory_cache.pop(cache_key, None)
            return None
    logger.info("evidence_cache_hit", cache_key=cache_key[:12], backend="memory", ttl_seconds=ttl_seconds)
    return payload


def _get_redis_cache(cache_key: str) -> Any | None:
    """
    Read evidence from Redis cache.

    Args:
        cache_key: Stable evidence cache key.

    Returns:
        Cached evidence or ``None``.
    """
    from ai_incident_commander.cache.redis_client import get_redis_client

    client = get_redis_client()
    if client is None:
        return None

    raw = client.get(f"{EVIDENCE_CACHE_PREFIX}{cache_key}")
    if raw is None:
        return None

    logger.info("evidence_cache_hit", cache_key=cache_key[:12], backend="redis")
    return json.loads(raw)


def _set_redis_cache(cache_key: str, evidence: Any, ttl_seconds: int) -> None:
    """
    Write evidence to Redis cache.

    Args:
        cache_key: Stable evidence cache key.
        evidence: Evidence payload.
        ttl_seconds: Expiration interval.
    """
    from ai_incident_commander.cache.redis_client import get_redis_client

    client = get_redis_client()
    if client is None:
        return
    client.setex(
        f"{EVIDENCE_CACHE_PREFIX}{cache_key}",
        ttl_seconds,
        json.dumps(evidence, default=str),
    )
