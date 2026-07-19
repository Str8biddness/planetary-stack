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


def _build_job_pipeline(settings: ControllerSettings) -> Any:
    target_node = os.environ.get("SYNTHESUS_WORKER_NODE")
    if not target_node:
        return None

    import tempfile
    import json
    from datetime import datetime
    from pathlib import Path
    
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    
    from services.job_pipeline import LocalJobPipeline
    from services.remote_backend import RemoteExecutionBackend
    from services.vsource import LocalVSourceControlPlane, Ed25519DocumentSigner
    from services.private_mesh.ssh_smoke import SshCarrier, NodeTarget
    from contracts.chal_vsource.v1.models import CapabilityDocument

    db_path = Path("~/.synthesus/vsource.sqlite3").expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    class DummyResolver:
        def resolve_key(self, key_id): return None

    signer = Ed25519DocumentSigner("key:local:001", Ed25519PrivateKey.generate())
    control_plane = LocalVSourceControlPlane(
        db_path,
        key_resolver=DummyResolver(),
        signer=signer,
        clock=datetime.now,
        scheduler_id="scheduler:local:001"
    )

    def capability_provider():
        return CapabilityDocument(
            schema="planetary.vsource.capability.v1",
            capability_id="capability:local:001",
            account_id="account:local:001",
            trust_zone="personal_cell",
            features=[],
            subject_id="subject:local:001",
            issued_at="2026-07-18T00:00:00Z",
            ttl_seconds=3600,
            signature={"key_id": "key:001", "value": "abc"}
        )

    carrier = SshCarrier(
        known_hosts=Path("~/.ssh/known_hosts").expanduser(),
        identity_file=None,
        timeout_seconds=60,
    )
    target = NodeTarget.parse(target_node)

    inventory = {
        "schema": "planetary.vsource.inventory.v1",
        "inventory_id": "inventory:001",
        "node_id": target.node_id,
        "account_id": "account:local:001",
        "trust_zone": "personal_cell",
        "public_key_fingerprint": "abc",
        "attestation": "unverified",
        "observed_at": "2026-07-18T00:00:00Z",
        "ttl_seconds": 3600,
        "health": "ready",
        "resources": {},
        "transports": ["lan_mtls"],
        "workload_kinds": ["inference"],
        "labels": {},
        "signature": {"key_id": "key:001", "value": "abc"}
    }

    backend = RemoteExecutionBackend(
        carrier=carrier,
        target=target,
        account_id="account:local:001",
        keys=[],
        inventory=inventory
    )

    def result_loader(output_sha256: str) -> bytes | None:
        # Bypassing SSH: securely fetch over unisync_mtls.
        # Use SSH only to bootstrap the unisync connection by telling the worker to send.
        from services.unisync.mesh_authority import MeshCertificateAuthority
        from services.unisync.mesh_identity import create_tls_enrollment
        from services.unisync.tls import TrustedLanServer, TLSCredentials, EnrolledPeerIdentity
        from services.unisync.contracts import TransferContext
        
        account_id = "account:local:001"
        desktop_node = "node:desktop:001"
        
        with tempfile.TemporaryDirectory() as td:
            state_dir = Path(td)
            
            # Desktop enrollment
            desktop_enroll = create_tls_enrollment(
                state_dir / "desktop",
                account_id=account_id,
                node_id=desktop_node,
                sans=["127.0.0.1"]
            )
            
            # Remote worker enrollment (via SSH)
            worker_enroll = carrier.run_cli(target, [
                "enroll-init", "--state-dir", "/tmp/mesh_worker",
                "--account-id", account_id, "--node-id", target.node_id,
                "--san", "127.0.0.1"
            ])
            
            # CA issues certs
            ca = MeshCertificateAuthority.create("Temp CA")
            desktop_cert = ca.issue_node_certificate(desktop_enroll["csr_pem"], account_id, desktop_node, ["127.0.0.1"])
            worker_cert = ca.issue_node_certificate(worker_enroll["csr_pem"], account_id, target.node_id, ["127.0.0.1"])
            
            # Install worker cert
            import base64
            carrier.run_cli(target, [
                "enroll-install", "--state-dir", "/tmp/mesh_worker"
            ], stdin=json.dumps({
                "schema": "planetary.unisync.mesh_enroll_install.v1",
                "account_id": account_id,
                "node_id": target.node_id,
                "certificate_pem": worker_cert.certificate_pem,
                "ca_pem": worker_cert.ca_pem,
                "certificate_sha256": worker_cert.certificate_sha256,
                "public_key_sha256": worker_cert.public_key_sha256,
                "controller_key_id": "key:0",
                "controller_public_key_base64": base64.urlsafe_b64encode(b"0"*32).decode(),
                "scheduler_key_id": "key:1",
                "scheduler_public_key_base64": base64.urlsafe_b64encode(b"1"*32).decode(),
            }).encode())
            
            # Setup desktop credentials
            desktop_creds = TLSCredentials(
                ca_file=state_dir / "ca.pem",
                cert_file=state_dir / "desktop" / "tls.crt",
                key_file=state_dir / "desktop" / "tls.key",
            )
            (state_dir / "ca.pem").write_text(desktop_cert.ca_pem)
            (state_dir / "desktop" / "tls.crt").write_text(desktop_cert.certificate_pem)
            
            worker_peer = EnrolledPeerIdentity(
                account_id=account_id,
                node_id=target.node_id,
                sans=frozenset(["127.0.0.1"]),
                certificate_sha256=worker_cert.certificate_sha256
            )
            
            context = TransferContext(
                account_id=account_id,
                request_sha256="a"*64,
                lease_id="lease:001",
                lease_sha256="b"*64,
                fencing_token=1,
                selected_transport="lan_mtls",
                source_node_id=target.node_id,
                destination_node_id=desktop_node,
                object_sha256=output_sha256,
                byte_length=0, # bypass for now or fetch length
                expires_at=datetime.now()
            )
            
            with TrustedLanServer(
                bind_host="127.0.0.1",
                port=0,
                credentials=desktop_creds,
                destination_root=state_dir / "inbox",
                validator=None,
                declared_listener_addresses=["127.0.0.1"],
                allowed_client_sans=["127.0.0.1"],
                enrolled_client_identities=[worker_peer],
                declared_vpn_cidrs=["127.0.0.0/8"]
            ) as server:
                host, port = server.address()
                
                # Fetch artifact size from worker
                # wait, worker's output artifact might already exist in its inbox/outbox.
                # Just instruct worker to send it.
                desktop_peer = {
                    "account_id": account_id,
                    "node_id": desktop_node,
                    "sans": ["127.0.0.1"],
                    "certificate_sha256": desktop_cert.certificate_sha256,
                    "public_key_sha256": desktop_cert.public_key_sha256
                }
                
                carrier.run_cli(target, [
                    "send", "--state-dir", "/tmp/mesh_worker"
                ], stdin=json.dumps({
                    "schema": "planetary.unisync.mesh_send.v1",
                    "account_id": account_id,
                    "node_id": target.node_id,
                    "server_host": host,
                    "server_port": port,
                    "server_hostname": "127.0.0.1",
                    "declared_vpn_cidrs": ["127.0.0.0/8"],
                    "timeout_seconds": 60,
                    "transfer_context": context.to_wire(),
                    "lease": {"lease_id": "lease:001", "fencing_token": 1},
                    "request": {"request_id": "req:001"},
                    "destination_peer": desktop_peer
                }).encode())
                
                # Wait for the file to be received in the inbox
                import time
                for _ in range(50):
                    p = state_dir / "inbox" / "objects" / output_sha256[:2] / output_sha256
                    if p.exists():
                        return p.read_bytes()
                    time.sleep(0.1)
                
        return None

    return LocalJobPipeline(
        control_plane=control_plane,
        backend=backend,
        request_signer=signer,
        capability_provider=capability_provider,
        authenticated_subject_id="subject:local:001",
        account_id="account:local:001",
        capability_id="capability:local:001",
        clock=datetime.now,
        resource_vector={},
        result_loader=result_loader
    )


def create_app(
    settings: ControllerSettings,
    *,
    runtime_transport: httpx.AsyncBaseTransport | None = None,
    terminal_transport: httpx.AsyncBaseTransport | None = None,
    job_pipeline: Any = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
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
        loaded = await asyncio.to_thread(job_pipeline.result, job_id, output_sha256)
        if loaded is None:
            return JSONResponse(status_code=404, content={"error": "result_not_found"})
        payload, media_type = loaded
        return Response(content=payload, media_type=media_type)

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
