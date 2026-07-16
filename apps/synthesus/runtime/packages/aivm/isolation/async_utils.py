"""Async isolation helpers shared by AIVM-backed runtime components."""

from __future__ import annotations

import asyncio
import contextvars
import queue
import threading
from typing import Any, Callable


async def run_sync_isolated(operation: Callable[[], Any]) -> Any:
    """Run blocking code without registering the loop's default executor.

    Python cannot safely terminate a timed-out thread. The worker is therefore
    daemonized so an abandoned device call cannot stall event-loop or interpreter
    shutdown. Request context is copied for tracing and policy propagation.
    """
    context = contextvars.copy_context()
    result_queue: queue.SimpleQueue[tuple[bool, Any]] = queue.SimpleQueue()

    def worker() -> None:
        try:
            result = context.run(operation)
        except Exception as exc:
            result_queue.put((False, exc))
        except BaseException as exc:
            result_queue.put((False, RuntimeError(f"isolated worker aborted: {type(exc).__name__}")))
        else:
            result_queue.put((True, result))

    threading.Thread(
        target=worker,
        name="aivm-isolated-worker",
        daemon=True,
    ).start()

    # Polling avoids depending on ``loop.call_soon_threadsafe``. Some restricted
    # runtimes cannot wake the event-loop selector from a worker thread, which
    # otherwise leaves a completed operation pending forever.
    while True:
        try:
            succeeded, value = result_queue.get_nowait()
            break
        except queue.Empty:
            await asyncio.sleep(0.001)

    if succeeded:
        return value
    raise value
