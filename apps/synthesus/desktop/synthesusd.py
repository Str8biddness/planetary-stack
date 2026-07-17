#!/usr/bin/env python3
"""Authenticated loopback controller for the Synthesus desktop.

The desktop shell talks to this daemon instead of reaching the cognitive
runtime or PTY backend directly. Runtime HTTP requests require the private
per-install API key. Browser terminal traffic requires a separate per-launch
token, then crosses a user-only Unix socket to the PTY backend.
"""

from __future__ import annotations

import asyncio
import hmac
import os
import re
import signal
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import uvicorn
import websockets
from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response


_REQUEST_HEADERS = {
    "accept",
    "authorization",
    "content-type",
    "x-api-key",
    "x-synthesus-human-session",
    "x-synthesus-token",
}
_RESPONSE_HEADERS = {
    "cache-control",
    "content-disposition",
    "content-type",
    "etag",
}
_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")


@dataclass(frozen=True)
class ControllerSettings:
    api_key: str
    terminal_token: str
    session_id: str
    runtime_url: str
    terminal_socket: Path
    allowed_origins: tuple[str, ...]
    parent_pid: int | None = None

    @classmethod
    def from_environment(cls) -> "ControllerSettings":
        shell_port = int(os.environ.get("SYNTHESUS_SHELL_PORT", "8081"))
        allowed = os.environ.get("SYNTHESUS_CONTROLLER_ALLOWED_ORIGINS", "").strip()
        origins = tuple(
            origin.strip()
            for origin in allowed.split(",")
            if origin.strip()
        ) or (
            f"http://127.0.0.1:{shell_port}",
            f"http://localhost:{shell_port}",
        )
        parent = os.environ.get("SYNTHESUS_CONTROLLER_PARENT_PID", "").strip()
        return cls(
            api_key=os.environ.get("SYNTHESUS_API_KEY", "dev-key-change-me"),
            terminal_token=os.environ.get("SYNTHESUS_TERMINAL_TOKEN", ""),
            session_id=os.environ.get("SYNTHESUS_CONTROLLER_SESSION_ID", ""),
            runtime_url=os.environ.get(
                "SYNTHESUS_RUNTIME_UPSTREAM_URL",
                "http://127.0.0.1:5010",
            ).rstrip("/"),
            terminal_socket=Path(
                os.environ.get(
                    "SYNTHESUS_TERMINAL_SOCKET",
                    "~/.synthesus/ipc/terminal.sock",
                )
            ).expanduser(),
            allowed_origins=origins,
            parent_pid=int(parent) if parent else None,
        )

    def validate_for_production(self) -> None:
        """Raise SystemExit for any config that is unsafe to run in production.

        Called from the lifespan startup hook so the check fires regardless of
        how uvicorn was invoked (direct script *or* ``uvicorn synthesusd:app``).
        """
        _KEY_PLACEHOLDER = "dev-key-change-me"
        if not self.api_key or self.api_key == _KEY_PLACEHOLDER:
            raise SystemExit(
                "SYNTHESUS_API_KEY is not set or equals the insecure placeholder. "
                "Run install.sh or set SYNTHESUS_API_KEY to a strong random value."
            )
        host = os.environ.get("SYNTHESUS_CONTROLLER_HOST", "127.0.0.1")
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise SystemExit(
                f"synthesusd refuses non-loopback binding: {host!r}. "
                "Set SYNTHESUS_CONTROLLER_HOST to 127.0.0.1 or localhost."
            )


def _constant_time_match(provided: str | None, expected: str) -> bool:
    return bool(provided and expected and hmac.compare_digest(provided, expected))


def _runtime_authorized(request: Request, settings: ControllerSettings) -> bool:
    return _constant_time_match(request.headers.get("x-api-key"), settings.api_key)


def _terminal_authorized(provided: str | None, settings: ControllerSettings) -> bool:
    return _constant_time_match(provided, settings.terminal_token)


def _origin_allowed(origin: str | None, settings: ControllerSettings) -> bool:
    return bool(origin and origin in settings.allowed_origins)


def _valid_session_id(session_id: str) -> bool:
    return bool(_SESSION_ID_PATTERN.fullmatch(session_id))


def _terminal_token_from_protocol_header(header: str | None) -> str | None:
    protocols = [
        protocol.strip()
        for protocol in (header or "").split(",")
        if protocol.strip()
    ]
    if len(protocols) == 2 and protocols[0] == "synthesus-terminal":
        return protocols[1]
    return None


def _filtered_request_headers(request: Request) -> dict[str, str]:
    return {
        name: value
        for name, value in request.headers.items()
        if name.lower() in _REQUEST_HEADERS
    }


def _filtered_response_headers(response: httpx.Response) -> dict[str, str]:
    return {
        name: value
        for name, value in response.headers.items()
        if name.lower() in _RESPONSE_HEADERS
    }


async def _parent_watchdog(parent_pid: int | None) -> None:
    if not parent_pid:
        return
    while True:
        await asyncio.sleep(1)
        try:
            os.kill(parent_pid, 0)
        except ProcessLookupError:
            os.kill(os.getpid(), signal.SIGTERM)
            return
        except PermissionError:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "_parent_watchdog: PermissionError probing pid %d — watchdog disabled",
                parent_pid,
            )
            return


def create_app(
    settings: ControllerSettings,
    *,
    runtime_transport: httpx.AsyncBaseTransport | None = None,
    terminal_transport: httpx.AsyncBaseTransport | None = None,
    validate: bool = False,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if validate:
            settings.validate_for_production()
        watchdog = asyncio.create_task(_parent_watchdog(settings.parent_pid))
        try:
            yield
        finally:
            watchdog.cancel()
            await asyncio.gather(watchdog, return_exceptions=True)

    app = FastAPI(title="synthesusd", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Key", "X-Synthesus-IPC-Token"],
    )

    async def probe_runtime() -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                transport=runtime_transport,
                timeout=3.0,
            ) as client:
                response = await client.get(
                    f"{settings.runtime_url}/api/v1/health",
                    headers={"X-API-Key": settings.api_key},
                )
            return {
                "status": "online" if response.status_code == 200 else "degraded",
                "http_status": response.status_code,
            }
        except Exception as exc:
            return {"status": "degraded", "error": str(exc)}

    async def probe_terminal() -> dict[str, Any]:
        if not settings.terminal_socket.exists():
            return {
                "status": "degraded",
                "error": f"terminal socket missing: {settings.terminal_socket}",
            }
        try:
            transport = terminal_transport or httpx.AsyncHTTPTransport(
                uds=str(settings.terminal_socket)
            )
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://synthesus-terminal",
                timeout=3.0,
            ) as client:
                response = await client.get("/api/terminal/health")
            return {
                "status": "online" if response.status_code == 200 else "degraded",
                "http_status": response.status_code,
            }
        except Exception as exc:
            return {"status": "degraded", "error": str(exc)}

    @app.get("/health")
    async def health(request: Request):
        if not _runtime_authorized(request, settings):
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
        runtime, terminal = await asyncio.gather(
            probe_runtime(),
            probe_terminal(),
        )
        status = (
            "online"
            if runtime.get("status") == terminal.get("status") == "online"
            else "degraded"
        )
        return {
            "status": status,
            "controller": "synthesusd",
            "session_id": settings.session_id,
            "runtime": runtime,
            "terminal": terminal,
            "terminal_transport": "unix_socket",
        }

    @app.get("/ready")
    async def ready(request: Request):
        if not _runtime_authorized(request, settings):
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
        return {
            "status": "ready",
            "controller": "synthesusd",
            "session_id": settings.session_id,
        }

    @app.api_route(
        "/runtime/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    )
    async def runtime_proxy(path: str, request: Request):
        if not _runtime_authorized(request, settings):
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
        try:
            async with httpx.AsyncClient(
                transport=runtime_transport,
                timeout=httpx.Timeout(650.0, connect=5.0),
                follow_redirects=False,
            ) as client:
                upstream = await client.request(
                    request.method,
                    f"{settings.runtime_url}/{path.lstrip('/')}",
                    params=request.query_params,
                    content=await request.body(),
                    headers=_filtered_request_headers(request),
                )
            return Response(
                content=upstream.content,
                status_code=upstream.status_code,
                headers=_filtered_response_headers(upstream),
            )
        except Exception as exc:
            return JSONResponse(
                status_code=502,
                content={
                    "error": "runtime_unavailable",
                    "message": str(exc),
                    "controller": "synthesusd",
                },
            )

    @app.api_route(
        "/terminal/{path:path}",
        methods=["GET", "POST"],
    )
    async def terminal_http_proxy(path: str, request: Request):
        token = request.headers.get("x-synthesus-ipc-token")
        if not _terminal_authorized(token, settings):
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
        if not settings.terminal_socket.exists():
            return JSONResponse(
                status_code=503,
                content={"error": "terminal_unavailable"},
            )
        try:
            transport = terminal_transport or httpx.AsyncHTTPTransport(
                uds=str(settings.terminal_socket)
            )
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://synthesus-terminal",
                timeout=10.0,
            ) as client:
                upstream = await client.request(
                    request.method,
                    f"/{path.lstrip('/')}",
                    params=request.query_params,
                    content=await request.body(),
                    headers={
                        "content-type": request.headers.get(
                            "content-type",
                            "application/json",
                        )
                    },
                )
            return Response(
                content=upstream.content,
                status_code=upstream.status_code,
                headers=_filtered_response_headers(upstream),
            )
        except Exception as exc:
            return JSONResponse(
                status_code=503,
                content={"error": "terminal_unavailable", "message": str(exc)},
            )

    @app.websocket("/ws/terminal/{session_id}")
    async def terminal_websocket(websocket: WebSocket, session_id: str):
        token = _terminal_token_from_protocol_header(
            websocket.headers.get("sec-websocket-protocol")
        )
        origin = websocket.headers.get("origin")
        if (
            not _terminal_authorized(token, settings)
            or not _origin_allowed(origin, settings)
        ):
            await websocket.close(code=4401)
            return
        if not _valid_session_id(session_id):
            await websocket.close(code=4400)
            return
        if not settings.terminal_socket.exists():
            await websocket.close(code=1011, reason="terminal unavailable")
            return

        await websocket.accept(subprotocol="synthesus-terminal")
        try:
            async with websockets.unix_connect(
                str(settings.terminal_socket),
                uri=f"ws://synthesus-terminal/ws/pty/user/{session_id}",
                open_timeout=5,
            ) as upstream:
                async def browser_to_terminal() -> None:
                    while True:
                        message = await websocket.receive()
                        if message["type"] == "websocket.disconnect":
                            return
                        if message.get("text") is not None:
                            await upstream.send(message["text"])
                        elif message.get("bytes") is not None:
                            await upstream.send(message["bytes"])

                async def terminal_to_browser() -> None:
                    async for message in upstream:
                        if isinstance(message, bytes):
                            await websocket.send_bytes(message)
                        else:
                            await websocket.send_text(message)

                tasks = {
                    asyncio.create_task(browser_to_terminal()),
                    asyncio.create_task(terminal_to_browser()),
                }
                done, pending = await asyncio.wait(
                    tasks,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                await asyncio.gather(*done, *pending, return_exceptions=True)
        except Exception:
            try:
                await websocket.close(code=1011, reason="terminal proxy failure")
            except Exception:
                pass

    return app


SETTINGS = ControllerSettings.from_environment()
# validate=True ensures the loopback + key guards fire at startup regardless
# of whether uvicorn imports this module directly (``uvicorn synthesusd:app``)
# or the file is run as a script.
app = create_app(SETTINGS, validate=True)


if __name__ == "__main__":
    host = os.environ.get("SYNTHESUS_CONTROLLER_HOST", "127.0.0.1")
    port = int(os.environ.get("SYNTHESUS_CONTROLLER_PORT", "5011"))
    uvicorn.run(app, host=host, port=port, log_level="info")
