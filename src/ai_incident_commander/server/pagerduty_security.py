"""PagerDuty webhook signature verification and deduplication.

Deduplication uses an in-memory OrderedDict that is optionally backed by a JSON
file so that event IDs survive process restarts.  Set ``PAGERDUTY_DEDUP_FILE``
in the environment (or ``.env``) to a writable path to enable persistence; when
the variable is empty the cache is purely in-memory (original behaviour).

File format::

    {"<event_id>": <unix_timestamp_float>, ...}

The file is read lazily on the first dedup check and written after every new
entry is inserted.  Writes are atomic: content is flushed to a temp file first
and then renamed over the target so a crash mid-write leaves the old file intact.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
import threading
import time
from collections import OrderedDict
from pathlib import Path

PAGERDUTY_SIGNATURE_HEADER = "X-PagerDuty-Signature"
PAGERDUTY_SIGNATURE_PREFIX = "v1="
MAX_TRACKED_EVENT_IDS = 1000

_lock = threading.Lock()
_seen_event_ids: OrderedDict[str, float] = OrderedDict()
_loaded_from_disk: bool = False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _dedup_file_path() -> Path | None:
    """Return the configured dedup file path, or None when not set."""
    from ai_incident_commander.config import get_settings  # local import to avoid cycles

    path_str = get_settings().pagerduty_dedup_file
    return Path(path_str) if path_str else None


def _load_from_disk(path: Path) -> None:
    """Load previously seen event IDs from *path* into the in-memory cache.

    Errors (missing file, corrupt JSON) are silently ignored so that a bad
    cache file never prevents the webhook receiver from starting.
    """
    global _seen_event_ids
    try:
        raw = path.read_text(encoding="utf-8")
        data: dict[str, float] = json.loads(raw)
        if not isinstance(data, dict):
            return
        for event_id, ts in data.items():
            _seen_event_ids[str(event_id)] = float(ts)
        # Trim to cap — oldest entries first.
        while len(_seen_event_ids) > MAX_TRACKED_EVENT_IDS:
            _seen_event_ids.popitem(last=False)
    except (FileNotFoundError, json.JSONDecodeError, ValueError, OSError):
        pass


def _save_to_disk(path: Path) -> None:
    """Atomically write the current dedup cache to *path*.

    Errors are silently swallowed — a failed write means we might re-process
    a duplicate after a restart, which is acceptable compared to crashing.
    """
    try:
        data = dict(_seen_event_ids)
        parent = path.parent
        parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp file in the same directory then rename for atomicity.
        fd, tmp_path = tempfile.mkstemp(dir=parent, prefix=".pd_dedup_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh)
        except Exception:
            os.unlink(tmp_path)
            raise
        os.replace(tmp_path, path)
    except OSError:
        pass


def _ensure_loaded() -> None:
    """Load the disk cache on first use (caller must hold ``_lock``)."""
    global _loaded_from_disk
    if _loaded_from_disk:
        return
    _loaded_from_disk = True
    path = _dedup_file_path()
    if path is not None:
        _load_from_disk(path)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def verify_pagerduty_signature(
    payload_body: bytes,
    secret: str,
    signature_header: str,
) -> bool:
    """
    Verify a PagerDuty v3 webhook HMAC-SHA256 signature.

    Args:
        payload_body: Raw request body bytes (unmodified).
        secret: Webhook signing secret from PagerDuty subscription settings.
        signature_header: Value of ``X-PagerDuty-Signature``.

    Returns:
        True when any ``v1=`` signature in the header matches the payload.
    """
    if not secret or not signature_header or not payload_body:
        return False

    computed = hmac.new(secret.encode("utf-8"), payload_body, hashlib.sha256).hexdigest()
    for part in signature_header.split(","):
        candidate = part.strip()
        if not candidate.startswith(PAGERDUTY_SIGNATURE_PREFIX):
            continue
        expected = candidate[len(PAGERDUTY_SIGNATURE_PREFIX):]
        if hmac.compare_digest(computed, expected):
            return True
    return False


def extract_pagerduty_event_id(payload: dict) -> str:
    """
    Extract a stable event identifier from a PagerDuty webhook payload.

    Args:
        payload: Parsed PagerDuty webhook JSON body.

    Returns:
        Event ID string, or empty string when not present.
    """
    event = payload.get("event")
    if isinstance(event, dict):
        event_id = event.get("id")
        if event_id:
            return str(event_id)
        data = event.get("data")
        if isinstance(data, dict) and data.get("id"):
            return str(data["id"])
    top_level_id = payload.get("id")
    return str(top_level_id) if top_level_id else ""


def is_duplicate_pagerduty_event(event_id: str) -> bool:
    """
    Return True when the same PagerDuty event ID was already accepted.

    On the first call the disk cache (``PAGERDUTY_DEDUP_FILE``) is loaded so
    that event IDs from before the last restart are also considered seen.
    When ``REDIS_URL`` is configured, Redis is used for cross-process dedup.

    Args:
        event_id: Stable event identifier from ``extract_pagerduty_event_id``.

    Returns:
        True if this event was seen in-process or in the persisted cache.
    """
    if not event_id:
        return False

    if _is_duplicate_in_redis(event_id):
        return True

    with _lock:
        _ensure_loaded()

        if event_id in _seen_event_ids:
            return True

        _seen_event_ids[event_id] = time.time()
        while len(_seen_event_ids) > MAX_TRACKED_EVENT_IDS:
            _seen_event_ids.popitem(last=False)

        path = _dedup_file_path()
        if path is not None:
            _save_to_disk(path)

    return False


PAGERDUTY_DEDUP_REDIS_PREFIX = "pagerduty:dedup:"


def _is_duplicate_in_redis(event_id: str) -> bool:
    """
    Return True when Redis reports the PagerDuty event ID was already seen.

    Args:
        event_id: Stable PagerDuty event identifier.

    Returns:
        Whether the event is a duplicate according to Redis ``SET NX``.
    """
    from ai_incident_commander.cache.redis_client import get_redis_client

    client = get_redis_client()
    if client is None:
        return False

    key = f"{PAGERDUTY_DEDUP_REDIS_PREFIX}{event_id}"
    was_inserted = client.set(key, "1", nx=True, ex=86_400)
    return not bool(was_inserted)


def reset_pagerduty_dedup_cache() -> None:
    """Clear the deduplication cache and delete the backing file (used in tests)."""
    global _loaded_from_disk
    with _lock:
        _seen_event_ids.clear()
        _loaded_from_disk = False
        path = _dedup_file_path()
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
