from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

import synthesusd


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


def test_from_environment_rejects_non_loopback_host(monkeypatch):
    monkeypatch.setenv("SYNTHESUS_CONTROLLER_HOST", "0.0.0.0")
    monkeypatch.setenv("SYNTHESUS_API_KEY", "strong-random-key-x7z")
    import pytest
    settings = synthesusd.ControllerSettings.from_environment()
    with pytest.raises(SystemExit, match="non-loopback"):
        settings.validate_for_production()


def test_from_environment_rejects_placeholder_api_key(monkeypatch):
    monkeypatch.setenv("SYNTHESUS_CONTROLLER_HOST", "127.0.0.1")
    monkeypatch.setenv("SYNTHESUS_API_KEY", "dev-key-change-me")
    import pytest
    settings = synthesusd.ControllerSettings.from_environment()
    with pytest.raises(SystemExit, match="SYNTHESUS_API_KEY"):
        settings.validate_for_production()


def test_from_environment_rejects_missing_api_key(monkeypatch):
    monkeypatch.setenv("SYNTHESUS_CONTROLLER_HOST", "127.0.0.1")
    monkeypatch.delenv("SYNTHESUS_API_KEY", raising=False)
    import pytest
    settings = synthesusd.ControllerSettings.from_environment()
    with pytest.raises(SystemExit, match="SYNTHESUS_API_KEY"):
        settings.validate_for_production()
