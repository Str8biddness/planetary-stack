import asyncio
import contextvars
import threading
import time

from aivm.isolation.guard import AIVMExecutionGuard


def test_async_device_runs_on_event_loop_without_default_executor():
    guard = AIVMExecutionGuard()
    event_loop_thread = threading.get_ident()

    async def operation():
        await asyncio.sleep(0)
        return threading.get_ident()

    result = asyncio.run(guard.run("chal://test/async", operation, timeout_ms=100.0))

    assert result.ok is True
    assert result.output == event_loop_thread


def test_sync_device_runs_in_worker_with_request_context():
    guard = AIVMExecutionGuard()
    event_loop_thread = threading.get_ident()
    request_id = contextvars.ContextVar("request_id", default="missing")
    request_id.set("trace-123")

    def operation():
        return threading.get_ident(), request_id.get()

    result = asyncio.run(guard.run("chal://test/sync", operation, timeout_ms=100.0))

    assert result.ok is True
    worker_thread, observed_request_id = result.output
    assert worker_thread != event_loop_thread
    assert observed_request_id == "trace-123"


def test_blocking_sync_device_times_out_without_stalling_loop_shutdown():
    guard = AIVMExecutionGuard()
    release_worker = threading.Event()

    def operation():
        release_worker.wait(timeout=1.0)
        return "released"

    async def run_guard():
        result = await guard.run("chal://test/blocking", operation, timeout_ms=20.0)
        release_worker.set()
        return result

    start = time.perf_counter()
    result = asyncio.run(run_guard())
    elapsed = time.perf_counter() - start

    assert result.ok is False
    assert result.status == "timeout"
    assert elapsed < 0.5
