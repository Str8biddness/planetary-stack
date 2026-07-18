from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

import synthesusd
import terminal_server


def _settings(socket_path: Path) -> synthesusd.ControllerSettings:
    return synthesusd.ControllerSettings(
        api_key="install-secret",
        terminal_token="launch-secret",
        session_id="session-1",
        runtime_url="http://runtime.test",
        terminal_socket=socket_path,
        allowed_origins=("http://127.0.0.1:8081",),
    )


def test_runtime_proxy_requires_install_key_and_forwards_real_response(tmp_path):
    terminal_socket = tmp_path / "terminal.sock"
    terminal_socket.touch()

    async def runtime_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path in {"/api/v1/health", "/api/v1/query"}
        assert request.headers["x-api-key"] == "install-secret"
        return httpx.Response(
            200,
            json={
                "status": "online",
                "path": request.url.path,
                "query": request.url.query.decode(),
            },
        )

    async def terminal_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/terminal/health"
        return httpx.Response(200, json={"ok": True})

    app = synthesusd.create_app(
        _settings(terminal_socket),
        runtime_transport=httpx.MockTransport(runtime_handler),
        terminal_transport=httpx.MockTransport(terminal_handler),
    )

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://controller.test",
        ) as client:
            denied = await client.post(
                "/runtime/api/v1/query",
                json={"query": "hello"},
            )
            assert denied.status_code == 401
            denied_ready = await client.get("/ready")
            assert denied_ready.status_code == 401

            allowed = await client.post(
                "/runtime/api/v1/query?mode=chal",
                headers={
                    "X-API-Key": "install-secret",
                    "Content-Type": "application/json",
                },
                json={"query": "hello"},
            )
            assert allowed.status_code == 200
            assert allowed.json()["path"] == "/api/v1/query"
            assert allowed.json()["query"] == "mode=chal"

            ready = await client.get(
                "/ready",
                headers={"X-API-Key": "install-secret"},
            )
            assert ready.status_code == 200
            assert ready.json()["session_id"] == "session-1"

            health = await client.get(
                "/health",
                headers={"X-API-Key": "install-secret"},
            )
            assert health.status_code == 200
            assert health.json()["status"] == "online"
            assert health.json()["session_id"] == "session-1"

    asyncio.run(exercise())


def test_terminal_proxy_uses_separate_launch_token(tmp_path):
    terminal_socket = tmp_path / "terminal.sock"
    terminal_socket.touch()

    async def terminal_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/terminal/resize"
        return httpx.Response(200, json={"ok": True})

    app = synthesusd.create_app(
        _settings(terminal_socket),
        runtime_transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"status": "online"})
        ),
        terminal_transport=httpx.MockTransport(terminal_handler),
    )

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://controller.test",
        ) as client:
            denied = await client.post(
                "/terminal/api/terminal/resize",
                json={"session_id": "s1", "cols": 80, "rows": 24},
            )
            assert denied.status_code == 401

            allowed = await client.post(
                "/terminal/api/terminal/resize",
                headers={"X-Synthesus-IPC-Token": "launch-secret"},
                json={"session_id": "s1", "cols": 80, "rows": 24},
            )
            assert allowed.status_code == 200
            assert allowed.json() == {"ok": True}

    asyncio.run(exercise())


def test_terminal_token_and_browser_origin_are_both_required(tmp_path):
    settings = _settings(tmp_path / "terminal.sock")
    assert synthesusd._terminal_authorized("launch-secret", settings)
    assert not synthesusd._terminal_authorized("wrong", settings)
    assert synthesusd._origin_allowed("http://127.0.0.1:8081", settings)
    assert not synthesusd._origin_allowed("https://attacker.invalid", settings)
    assert synthesusd._valid_session_id("sess-1_abc.2")
    assert not synthesusd._valid_session_id("../escape")
    assert (
        synthesusd._terminal_token_from_protocol_header(
            "synthesus-terminal, launch-secret"
        )
        == "launch-secret"
    )
    assert synthesusd._terminal_token_from_protocol_header("launch-secret") is None


def test_terminal_backend_has_no_tcp_listener():
    source = Path(__file__).with_name("terminal_server.py").read_text(
        encoding="utf-8"
    )
    assert "uvicorn.run(app, uds=SOCKET_PATH" in source
    assert "uvicorn.run(app, host=" not in source


def test_environment_rejects_missing_default_and_non_loopback_controller(monkeypatch):
    monkeypatch.delenv("SYNTHESUS_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="unique per-install secret"):
        synthesusd.ControllerSettings.from_environment()

    monkeypatch.setenv("SYNTHESUS_API_KEY", "dev-key-change-me")
    with pytest.raises(RuntimeError, match="unique per-install secret"):
        synthesusd.ControllerSettings.from_environment()

    monkeypatch.setenv("SYNTHESUS_API_KEY", "syn_test_unique_secret")
    monkeypatch.setenv("SYNTHESUS_CONTROLLER_HOST", "0.0.0.0")
    with pytest.raises(RuntimeError, match="refuses non-loopback"):
        synthesusd.ControllerSettings.from_environment()


def test_module_does_not_export_an_app_for_uvicorn_cli_bypass():
    assert not hasattr(synthesusd, "app")


@pytest.mark.parametrize(
    ("cols", "rows"),
    [(0, 24), (80, 0), (65536, 24), (80, 65536)],
)
def test_terminal_resize_dimensions_are_bounded(cols, rows):
    with pytest.raises(ValidationError):
        terminal_server.ResizeReq(session_id="bounds", cols=cols, rows=rows)


class _StubJobRecord:
    def __init__(self, payload):
        self.payload = payload

    def to_wire(self):
        return dict(self.payload)


class _StubJobPipeline:
    def __init__(self):
        self.submitted = []
        self.cancelled = []

    def submit(self, *, bundle, workload_kind):
        self.submitted.append((bundle, workload_kind))
        return _StubJobRecord(
            {
                "job_id": "job:stub:001",
                "state": "completed",
                "outputs": [{"sha256": "0" * 64}],
            }
        )

    def status(self, job_id):
        if job_id != "job:stub:001":
            return None
        return _StubJobRecord({"job_id": job_id, "state": "completed"})

    def cancel(self, job_id):
        self.cancelled.append(job_id)
        if job_id != "job:stub:001":
            return None
        return _StubJobRecord({"job_id": job_id, "state": "cancelled"})


def test_job_endpoints_require_auth_and_a_configured_pipeline(tmp_path):
    import base64

    terminal_socket = tmp_path / "terminal.sock"
    terminal_socket.touch()
    pipeline = _StubJobPipeline()
    app_without_jobs = synthesusd.create_app(_settings(terminal_socket))
    app_with_jobs = synthesusd.create_app(
        _settings(terminal_socket),
        job_pipeline=pipeline,
    )
    bundle = base64.b64encode(b"canonical manifest bytes").decode()

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_without_jobs),
            base_url="http://controller.test",
        ) as client:
            unauthorized = await client.post(
                "/api/jobs", json={"bundle_base64": bundle}
            )
            assert unauthorized.status_code == 401
            unavailable = await client.post(
                "/api/jobs",
                headers={"X-API-Key": "install-secret"},
                json={"bundle_base64": bundle},
            )
            assert unavailable.status_code == 503

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_jobs),
            base_url="http://controller.test",
        ) as client:
            headers = {"X-API-Key": "install-secret"}
            bad_body = await client.post(
                "/api/jobs", headers=headers, json={"bundle_base64": "@@not-base64@@"}
            )
            assert bad_body.status_code == 400
            missing_bundle = await client.post(
                "/api/jobs", headers=headers, json={}
            )
            assert missing_bundle.status_code == 400

            submitted = await client.post(
                "/api/jobs", headers=headers, json={"bundle_base64": bundle}
            )
            assert submitted.status_code == 200
            assert submitted.json()["job_id"] == "job:stub:001"
            assert pipeline.submitted == [
                (b"canonical manifest bytes", "inference")
            ]

            status = await client.get("/api/jobs/job:stub:001", headers=headers)
            assert status.status_code == 200
            assert status.json()["state"] == "completed"
            unknown = await client.get("/api/jobs/job:stub:404", headers=headers)
            assert unknown.status_code == 404

            cancelled = await client.post(
                "/api/jobs/job:stub:001/cancel", headers=headers
            )
            assert cancelled.status_code == 200
            assert cancelled.json()["state"] == "cancelled"

    asyncio.run(exercise())
