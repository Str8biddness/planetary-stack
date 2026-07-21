#!/usr/bin/env python3
"""Authenticated loopback controller for the Synthesus desktop.

The desktop shell talks to this daemon instead of reaching the cognitive
runtime or PTY backend directly. Runtime HTTP requests require the private
per-install API key. Browser terminal traffic requires a separate per-launch
token, then crosses a user-only Unix socket to the PTY backend.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hmac
import logging
import os
import subprocess
import sys
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
# Base64 expansion of the 8 MiB pipeline bundle limit, with headroom.
_MAX_JOB_BUNDLE_BASE64_CHARS = 12 * 1024 * 1024
_LOOPBACK_BIND_HOSTS = {"127.0.0.1", "localhost", "::1"}
_KNOWN_DEFAULT_API_KEY = "dev-key-change-me"
from device_policy import (  # noqa: E402
    ALL_CAPABILITIES,
    ROLES,
    DevicePolicyError,
    DevicePolicyStore,
)
from mesh_discovery import (  # noqa: E402
    discover_enrolled_nodes,
    registry_path_from_environment,
)

log = logging.getLogger("synthesusd")


@dataclass(frozen=True)
class ControllerSettings:
    api_key: str
    terminal_token: str
    session_id: str
    runtime_url: str
    terminal_socket: Path
    allowed_origins: tuple[str, ...]
    parent_pid: int | None = None
    bind_host: str = "127.0.0.1"

    @classmethod
    def from_environment(cls) -> "ControllerSettings":
        api_key = os.environ.get("SYNTHESUS_API_KEY", "").strip()
        if not api_key or hmac.compare_digest(api_key, _KNOWN_DEFAULT_API_KEY):
            raise RuntimeError(
                "SYNTHESUS_API_KEY must be a unique per-install secret; "
                "run install.sh or set it explicitly"
            )
        bind_host = os.environ.get(
            "SYNTHESUS_CONTROLLER_HOST",
            "127.0.0.1",
        ).strip()
        if bind_host not in _LOOPBACK_BIND_HOSTS:
            raise RuntimeError(
                f"synthesusd refuses non-loopback binding: {bind_host!r}"
            )
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
            api_key=api_key,
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
            bind_host=bind_host,
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
        except PermissionError as exc:
            log.warning(
                "cannot monitor parent pid %s; controller watchdog disabled: %s",
                parent_pid,
                exc,
            )
            return


_REPO_ROOT = Path(__file__).resolve().parents[3]
_DESKTOP_MESH_SAN = "desktop.mesh"


def _pinned_ssh_argv(config: Any, remote_command: str) -> list[str]:
    """Hardened, host-key-pinned ssh argv for one worker command."""

    return [
        "ssh", "-T",
        "-o", "BatchMode=yes",
        "-o", "PasswordAuthentication=no",
        "-o", "StrictHostKeyChecking=yes",
        "-o", f"UserKnownHostsFile={config.known_hosts}",
        "-o", "GlobalKnownHostsFile=/dev/null",
        "-o", "IdentitiesOnly=yes",
        "-i", str(config.ssh_identity),
        "-o", "HostKeyAlgorithms=ssh-ed25519",
        "-o", "ConnectTimeout=10",
        config.target.ssh_alias, remote_command,
    ]


def _resolve_worker_listen_ip(alias: str) -> str | None:
    """Resolve the worker's LAN address from the ssh config (bind target)."""

    try:
        out = subprocess.run(
            ["ssh", "-G", alias], capture_output=True, text=True, timeout=10, check=False
        )
    except Exception:
        return None
    if out.returncode != 0:
        return None
    for line in out.stdout.splitlines():
        key, _, value = line.partition(" ")
        if key == "hostname" and value.strip():
            return value.strip()
    return None


def _build_pull_result_loader(config: Any):
    """Construct the desktop-initiated pull result_loader, or None (best effort).

    Firewall-free result return: the desktop dials the worker and pulls a
    completed result over lease-bound mTLS. Any construction problem returns
    None so result bytes are simply unavailable (404) rather than breaking the
    pipeline.
    """

    import json
    import secrets

    from services.result_transfer import build_pull_result_loader
    from services.unisync.mesh_smoke import HybridMeshCarrier

    listen_ip = _resolve_worker_listen_ip(config.target.ssh_alias)
    if listen_ip is None:
        log.warning("could not resolve worker listen address; result pull unavailable")
        return None
    target = config.target

    def _ssh(remote_command: str) -> tuple[int, str]:
        proc = subprocess.run(
            _pinned_ssh_argv(config, remote_command),
            capture_output=True, text=True, timeout=90, check=False,
        )
        return proc.returncode, proc.stdout

    def stage_on_worker(digest: str, source_state_dir: str):
        stage_job = json.dumps(
            {
                "schema": "planetary.private_mesh.stage_result.v1",
                "account_id": config.account_id,
                "node_id": target.node_id,
                "result_sha256": digest,
            }
        )
        command = (
            f"set -e; mkdir -m 0700 -p {source_state_dir}/aivm/results; "
            f"cp {target.remote_state_dir}/aivm/results/{digest} "
            f"{source_state_dir}/aivm/results/{digest}; "
            f"printf %s {json.dumps(stage_job)} | env PYTHONPATH={target.remote_repo} "
            f"{target.remote_python} -m services.private_mesh.worker_cli "
            f"stage-result --state-dir {source_state_dir}; chmod 0700 {source_state_dir}"
        )
        rc, out = _ssh(command)
        if rc != 0:
            return None
        for line in out.splitlines():
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if obj.get("object_sha256") == digest:
                return int(obj["byte_length"])
        return None

    def worker_source_dir_factory() -> str:
        return f"{target.remote_state_dir}-pull-{secrets.token_hex(6)}"

    def cleanup_worker_dir(path: str) -> None:
        _ssh(f"rm -rf {path}")

    workspace = Path("~/.synthesus/result-pull").expanduser()
    return build_pull_result_loader(
        stage_on_worker=stage_on_worker,
        worker_source_dir_factory=worker_source_dir_factory,
        cleanup_worker_dir=cleanup_worker_dir,
        carrier=HybridMeshCarrier(
            known_hosts=config.known_hosts,
            identity_file=config.ssh_identity,
            timeout_seconds=60,
        ),
        workspace=workspace,
        account_id=config.account_id,
        subject_id=config.subject_id,
        worker_node_id=target.node_id,
        worker_python=target.remote_python,
        worker_repo=target.remote_repo,
        worker_ssh_alias=target.ssh_alias,
        worker_ssh_fingerprint=target.ssh_host_fingerprint,
        worker_listen_ip=listen_ip,
        desktop_node_id="node:desktop:001",
        desktop_python=sys.executable,
        desktop_repo=str(_REPO_ROOT),
        desktop_san=_DESKTOP_MESH_SAN,
    )


def _build_job_pipeline(settings: ControllerSettings) -> Any:
    """Build the job pipeline the controller serves, or None if unavailable.

    Reads a strictly-validated remote-worker configuration and constructs a
    real, fully-signed desktop->worker pipeline (persistent owner-only
    controller identity, real worker enrollment, real signed control plane).
    Returns None when no worker is configured or the worker cannot be reached
    (fail closed). No placeholder keys or signatures are ever constructed.

    Result bytes return to the desktop via a firewall-free desktop-initiated
    pull (the desktop dials the worker over lease-bound mTLS); when that loader
    cannot be constructed, result bytes are simply unavailable, not fatal.
    """

    from datetime import UTC, datetime

    from services.remote_pipeline import RemotePipelineError, build_remote_pipeline
    from services.remote_worker_config import (
        RemoteWorkerConfigError,
        load_remote_worker_config,
    )

    try:
        config = load_remote_worker_config(os.environ)
    except RemoteWorkerConfigError as exc:
        log.warning("remote worker config invalid; remote jobs unavailable: %s", exc)
        return None
    if config is None:
        return None

    try:
        result_loader = _build_pull_result_loader(config)
    except Exception as exc:  # never let result-return wiring break job submission
        log.warning("result pull loader unavailable: %s", exc)
        result_loader = None

    state_dir = Path("~/.synthesus/remote-authority").expanduser()
    try:
        return build_remote_pipeline(
            config,
            state_dir=state_dir,
            clock=lambda: datetime.now(UTC).replace(microsecond=0),
            result_loader=result_loader,
        )
    except RemotePipelineError as exc:
        log.warning("remote pipeline state error; remote jobs unavailable: %s", exc)
        return None


DEVICE_POLICY_PATH = "~/.synthesus/device-policy.json"


def _worker_node_id() -> str | None:
    """Node id of the configured worker, or None when none is configured."""
    try:
        from services.remote_worker_config import load_remote_worker_config

        config = load_remote_worker_config(os.environ)
    except Exception:
        return None
    return None if config is None else config.target.node_id


def _evidence_status(job_pipeline: Any) -> str:
    """Provenance state of the most recent execution on this pipeline.

    Returns "unavailable" rather than guessing when the backend cannot report
    one — an unknown provenance is never reported as a verified one.
    """
    backend = getattr(job_pipeline, "_backend", None)
    status = getattr(backend, "last_evidence_status", None)
    return status if isinstance(status, str) and status else "unavailable"


def create_app(
    settings: ControllerSettings,
    *,
    runtime_transport: httpx.AsyncBaseTransport | None = None,
    terminal_transport: httpx.AsyncBaseTransport | None = None,
    job_pipeline: Any = None,
    device_policy: Any = None,
    worker_node_id: str | None = None,
    mesh_registry_path: Path | str | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        watchdog = asyncio.create_task(_parent_watchdog(settings.parent_pid))
        try:
            yield
        finally:
            watchdog.cancel()
            await asyncio.gather(watchdog, return_exceptions=True)

    if device_policy is None:
        device_policy = DevicePolicyStore(DEVICE_POLICY_PATH)
    if worker_node_id is None:
        worker_node_id = _worker_node_id()
    if mesh_registry_path is None:
        mesh_registry_path = registry_path_from_environment()

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

    @app.post("/api/jobs")
    async def submit_job(request: Request):
        if not _runtime_authorized(request, settings):
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
        if job_pipeline is None:
            return JSONResponse(status_code=503, content={"error": "jobs_unavailable"})
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(status_code=400, content={"error": "invalid_request"})
        if not isinstance(body, dict):
            return JSONResponse(status_code=400, content={"error": "invalid_request"})
        encoded = body.get("bundle_base64")
        workload_kind = body.get("workload_kind", "inference")
        if (
            not isinstance(encoded, str)
            or not encoded
            or len(encoded) > _MAX_JOB_BUNDLE_BASE64_CHARS
            or not isinstance(workload_kind, str)
        ):
            return JSONResponse(status_code=400, content={"error": "invalid_request"})
        try:
            bundle = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            return JSONResponse(status_code=400, content={"error": "invalid_request"})
        # Permission gate: this desktop will not dispatch work to a device the
        # owner has not explicitly allowed to run it. Default-deny.
        if worker_node_id is None or not await asyncio.to_thread(
            device_policy.is_allowed, worker_node_id, "run_inference"
        ):
            return JSONResponse(
                status_code=403,
                content={
                    "error": "device_not_permitted",
                    "capability": "run_inference",
                    "device_id": worker_node_id,
                },
            )
        try:
            record = await asyncio.to_thread(
                job_pipeline.submit,
                bundle=bundle,
                workload_kind=workload_kind,
            )
        except Exception:
            return JSONResponse(status_code=502, content={"error": "job_submit_failed"})
        return record.to_wire()

    @app.get("/api/jobs/{job_id}")
    async def job_status(job_id: str, request: Request):
        if not _runtime_authorized(request, settings):
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
        if job_pipeline is None:
            return JSONResponse(status_code=503, content={"error": "jobs_unavailable"})
        record = await asyncio.to_thread(job_pipeline.status, job_id)
        if record is None:
            return JSONResponse(status_code=404, content={"error": "job_not_found"})
        return record.to_wire()

    @app.get("/api/jobs/{job_id}/results/{output_sha256}")
    async def job_result(job_id: str, output_sha256: str, request: Request):
        if not _runtime_authorized(request, settings):
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
        if job_pipeline is None:
            return JSONResponse(status_code=503, content={"error": "jobs_unavailable"})
        if worker_node_id is None or not await asyncio.to_thread(
            device_policy.is_allowed, worker_node_id, "return_results"
        ):
            return JSONResponse(
                status_code=403,
                content={
                    "error": "device_not_permitted",
                    "capability": "return_results",
                    "device_id": worker_node_id,
                },
            )
        # Provenance is always evaluated; the policy decides whether an
        # unverified result is refused or merely flagged. Either way the state
        # travels with the bytes so the UI can badge it honestly.
        status = _evidence_status(job_pipeline)
        if status != "verified" and await asyncio.to_thread(
            device_policy.require_verified_evidence
        ):
            return JSONResponse(
                status_code=409,
                content={"error": "evidence_not_verified", "evidence_status": status},
            )
        loaded = await asyncio.to_thread(job_pipeline.result, job_id, output_sha256)
        if loaded is None:
            return JSONResponse(status_code=404, content={"error": "result_not_found"})
        payload, media_type = loaded
        return Response(
            content=payload,
            media_type=media_type,
            headers={"X-Synthesus-Evidence-Status": status},
        )

    @app.post("/api/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str, request: Request):
        if not _runtime_authorized(request, settings):
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
        if job_pipeline is None:
            return JSONResponse(status_code=503, content={"error": "jobs_unavailable"})
        try:
            record = await asyncio.to_thread(job_pipeline.cancel, job_id)
        except Exception:
            return JSONResponse(status_code=502, content={"error": "job_cancel_failed"})
        if record is None:
            return JSONResponse(status_code=404, content={"error": "job_not_found"})
        return record.to_wire()

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


    # ---------------------------------------------------------------- settings

    @app.get("/api/settings")
    async def get_settings(request: Request):
        if not _runtime_authorized(request, settings):
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
        try:
            policy = await asyncio.to_thread(device_policy.load)
        except DevicePolicyError as exc:
            return JSONResponse(
                status_code=500, content={"error": "policy_unreadable", "detail": str(exc)}
            )
        return {
            "require_verified_evidence": policy["require_verified_evidence"],
            "worker_node_id": worker_node_id,
            "capabilities": list(ALL_CAPABILITIES),
            "roles": list(ROLES),
        }

    @app.put("/api/settings/evidence")
    async def set_evidence_policy(request: Request):
        if not _runtime_authorized(request, settings):
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(status_code=400, content={"error": "invalid_request"})
        enabled = body.get("enabled") if isinstance(body, dict) else None
        if not isinstance(enabled, bool):
            return JSONResponse(status_code=400, content={"error": "invalid_request"})
        try:
            policy = await asyncio.to_thread(
                device_policy.set_require_verified_evidence, enabled
            )
        except DevicePolicyError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})
        return {"require_verified_evidence": policy["require_verified_evidence"]}

    # ----------------------------------------------------------------- devices

    @app.get("/api/devices")
    async def list_devices(request: Request):
        if not _runtime_authorized(request, settings):
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
        try:
            rows = await asyncio.to_thread(device_policy.devices)
        except DevicePolicyError as exc:
            return JSONResponse(
                status_code=500, content={"error": "policy_unreadable", "detail": str(exc)}
            )
        return {"devices": rows}

    @app.get("/api/devices/discovered")
    async def list_discovered_devices(request: Request):
        """Enrolled mesh nodes that are not yet device rows.

        READ ONLY, and grants nothing. The response is a list of candidates the
        owner may choose to add; adding still goes through POST /api/devices,
        which creates the row with every capability off. A registry that is
        missing or unreadable returns an empty list plus a reason with HTTP 200,
        because the permissions window has to keep working on a machine with no
        mesh state — the alternative is an error that hides the owner's real
        devices behind a failure about a file they have never heard of.
        """
        if not _runtime_authorized(request, settings):
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
        try:
            rows = await asyncio.to_thread(device_policy.devices)
        except DevicePolicyError as exc:
            # Same failure shape as GET /api/devices: if we cannot read the
            # policy we do not know what is already listed, and we will not
            # guess. Matches the sibling endpoint so the UI handles one case.
            return JSONResponse(
                status_code=500, content={"error": "policy_unreadable", "detail": str(exc)}
            )
        known = [row["device_id"] for row in rows]
        found = await asyncio.to_thread(
            lambda: discover_enrolled_nodes(mesh_registry_path, known_device_ids=known)
        )
        return found

    @app.post("/api/devices")
    async def add_device(request: Request):
        if not _runtime_authorized(request, settings):
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(status_code=400, content={"error": "invalid_request"})
        if not isinstance(body, dict):
            return JSONResponse(status_code=400, content={"error": "invalid_request"})
        try:
            device = await asyncio.to_thread(
                lambda: device_policy.add_device(
                    device_id=body.get("device_id"),
                    display_name=body.get("display_name"),
                    role=body.get("role"),
                )
            )
        except DevicePolicyError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})
        return device

    @app.put("/api/devices/{device_id}/capabilities")
    async def set_device_capabilities(device_id: str, request: Request):
        if not _runtime_authorized(request, settings):
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(status_code=400, content={"error": "invalid_request"})
        capabilities = body.get("capabilities") if isinstance(body, dict) else None
        if not isinstance(capabilities, dict):
            return JSONResponse(status_code=400, content={"error": "invalid_request"})
        try:
            device = await asyncio.to_thread(
                device_policy.set_capabilities, device_id, capabilities
            )
        except DevicePolicyError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})
        return device

    @app.delete("/api/devices/{device_id}")
    async def delete_device(device_id: str, request: Request):
        if not _runtime_authorized(request, settings):
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
        try:
            await asyncio.to_thread(device_policy.remove_device, device_id)
        except DevicePolicyError as exc:
            return JSONResponse(status_code=404, content={"error": str(exc)})
        return {"removed": device_id}

    return app


if __name__ == "__main__":
    try:
        settings = ControllerSettings.from_environment()
    except (RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    port = int(os.environ.get("SYNTHESUS_CONTROLLER_PORT", "5011"))
    
    pipeline = _build_job_pipeline(settings)
    
    uvicorn.run(
        create_app(settings, job_pipeline=pipeline),
        host=settings.bind_host,
        port=port,
        log_level="info",
    )
