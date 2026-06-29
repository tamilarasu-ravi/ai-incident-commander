"""Shared background event loop for sync-to-async bridges (Bolt threads, FastAPI tasks)."""

from __future__ import annotations

import asyncio
import contextvars
import threading
from collections.abc import Coroutine
from concurrent.futures import Future
from typing import TypeVar

T = TypeVar("T")

_loop: asyncio.AbstractEventLoop | None = None
_thread: threading.Thread | None = None
_ready = threading.Event()
_start_lock = threading.Lock()

from ai_incident_commander.config import get_settings

#: Default seconds to wait for a coroutine result before raising TimeoutError.
DEFAULT_RUN_ASYNC_TIMEOUT_SECONDS = 30


def get_run_async_timeout() -> float:
    """
    Return the configured ``run_async`` timeout in seconds.

    Returns:
        Timeout value from settings, falling back to the module default.
    """
    return float(get_settings().run_async_timeout_seconds)


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

    ContextVar values from the calling thread are propagated into the task so
    that utilities such as ``track_investigation_llm_usage`` work correctly
    across the thread boundary.

    Args:
        coro: Coroutine to execute.

    Returns:
        Coroutine result.

    Raises:
        RuntimeError: If called from inside a running event loop.
        TimeoutError: If the coroutine does not complete within the configured
            ``RUN_ASYNC_TIMEOUT_SECONDS`` window.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        coro.close()
        raise RuntimeError("run_async cannot be called from inside a running event loop")

    loop = _start_loop_thread()
    ctx = contextvars.copy_context()
    result_future: Future[T] = Future()

    async def _run_in_context() -> None:
        try:
            result_future.set_result(await coro)
        except Exception as exc:  # noqa: BLE001
            result_future.set_exception(exc)

    loop.call_soon_threadsafe(
        lambda: loop.create_task(_run_in_context(), context=ctx)
    )
    return result_future.result(timeout=get_run_async_timeout())
