"""PagerDuty webhook signature verification and deduplication."""

from __future__ import annotations

import hashlib
import hmac
import time
from collections import OrderedDict

PAGERDUTY_SIGNATURE_HEADER = "X-PagerDuty-Signature"
PAGERDUTY_SIGNATURE_PREFIX = "v1="
MAX_TRACKED_EVENT_IDS = 1000

_seen_event_ids: OrderedDict[str, float] = OrderedDict()


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
        expected = candidate[len(PAGERDUTY_SIGNATURE_PREFIX) :]
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

    Args:
        event_id: Stable event identifier from ``extract_pagerduty_event_id``.

    Returns:
        True if this event was seen recently in-process.
    """
    if not event_id:
        return False

    if event_id in _seen_event_ids:
        return True

    _seen_event_ids[event_id] = time.time()
    while len(_seen_event_ids) > MAX_TRACKED_EVENT_IDS:
        _seen_event_ids.popitem(last=False)
    return False


def reset_pagerduty_dedup_cache() -> None:
    """Clear the in-memory deduplication cache (used in tests)."""
    _seen_event_ids.clear()
