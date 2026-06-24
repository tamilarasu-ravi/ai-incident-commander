"""Shared background event loop for sync-to-async bridges (Bolt threads, FastAPI tasks)."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from concurrent.futures import Future
from typing import TypeVar

T = TypeVar("T")

_loop: asyncio.AbstractEventLoop | None = None
_thread: threading.Thread | None = None
_ready = threading.Event()
_start_lock = threading.Lock()


def _start_loop_thread() -> asyncio.AbstractEventLoop:
    """
    Start a daemon thread running a persistent asyncio event loop.

    Returns:
        The background event loop used for ``run_async`` submissions.
    """
    global _loop, _thread

    with _start_lock:
        if _loop is not None:
            return _loop

        def _run_forever() -> None:
            global _loop
            _loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_loop)
            _ready.set()
            _loop.run_forever()

        _thread = threading.Thread(target=_run_forever, name="async-bridge", daemon=True)
        _thread.start()
        _ready.wait()
        assert _loop is not None
        return _loop


def run_async(coro: Coroutine[object, object, T]) -> T:
    """
    Run an async coroutine on the shared background event loop.

    Args:
        coro: Coroutine to execute.

    Returns:
        Coroutine result.

    Raises:
        RuntimeError: If called from inside a running event loop.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        loop = _start_loop_thread()
        future: Future[T] = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result()
    raise RuntimeError("run_async cannot be called from inside a running event loop")
