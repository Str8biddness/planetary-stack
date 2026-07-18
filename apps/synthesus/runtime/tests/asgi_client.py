"""ASGI test client that does not require a cross-thread event-loop portal."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any, Mapping

import httpx


class MainThreadASGIClient:
    """Small synchronous facade that executes each request on the caller thread."""

    def __init__(
        self,
        app: Any,
        *,
        base_url: str = "http://127.0.0.1",
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self._app = app
        self._base_url = base_url
        self._headers = dict(headers or {})

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        async def send() -> httpx.Response:
            transport = httpx.ASGITransport(app=self._app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url=self._base_url,
                headers=self._headers,
            ) as client:
                # Restricted sandboxes may not wake an event-loop selector when
                # AnyIO completes a synchronous endpoint on a worker thread.
                # Keep a short timer pending so callbacks are observed without
                # relying on the cross-thread wakeup file descriptor.
                async def keep_loop_awake() -> None:
                    while True:
                        await asyncio.sleep(0.001)

                ticker = asyncio.create_task(keep_loop_awake())
                try:
                    return await client.request(method, url, **kwargs)
                finally:
                    ticker.cancel()
                    with suppress(asyncio.CancelledError):
                        await ticker

        return asyncio.run(send())

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def close(self) -> None:
        """Match the closeable interface of HTTPX and Starlette clients."""
