"""Thread-safe in-process cache for Slack assistant action tokens.

Action tokens are captured from ``assistant_thread_started`` and
``assistant_thread_context_changed`` events and keyed by channel ID.
They are passed to the RTS ``assistant.search.context`` API so that
background investigations can use the primary search path instead of
falling back to ``conversations.history``.

Tokens are short-lived (minutes) and are not persisted across restarts.
"""

from __future__ import annotations

import threading
from collections import OrderedDict

_lock = threading.Lock()
_tokens: OrderedDict[str, str] = OrderedDict()
_latest_token: str | None = None
_MAX_TOKENS = 200


def set_action_token(channel_id: str, action_token: str) -> None:
    """
    Cache an action token for a channel.

    Args:
        channel_id: Slack channel ID from the assistant thread event.
        action_token: Short-lived RTS action token.
    """
    if not channel_id or not action_token:
        return
    with _lock:
        global _latest_token
        _tokens[channel_id] = action_token
        _latest_token = action_token
        while len(_tokens) > _MAX_TOKENS:
            _tokens.popitem(last=False)


def get_action_token(channel_id: str) -> str | None:
    """
    Return the most recent action token for a channel, or ``None``.

    Args:
        channel_id: Slack channel ID to look up.

    Returns:
        Cached action token string, or ``None`` when absent.
    """
    with _lock:
        return _tokens.get(channel_id)


def get_most_recent_action_token() -> str | None:
    """
    Return the most recently cached RTS action token, regardless of channel.

    Returns:
        Latest action token from an Assistant thread event, or ``None``.
    """
    with _lock:
        return _latest_token


def clear() -> None:
    """Remove all cached tokens (used in tests)."""
    global _latest_token
    with _lock:
        _tokens.clear()
        _latest_token = None
