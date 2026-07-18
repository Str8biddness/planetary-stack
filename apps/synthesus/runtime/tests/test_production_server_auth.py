from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
from fastapi import WebSocketDisconnect
from starlette.requests import Request

from api import production_server as server
from core.cognitive.pattern_engine import _default_global_db_path


def test_install_key_and_loopback_configuration_fail_closed(monkeypatch):
    monkeypatch.delenv("SYNTHESUS_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="unique per-install API key"):
        server._required_install_key()

    for value in ("", "short", "dev-key-change-me"):
        with pytest.raises(RuntimeError, match="unique per-install API key"):
            server._required_install_key(value)

    assert (
        server._required_install_key("syn_unique_runtime_test_key_123456")
        == "syn_unique_runtime_test_key_123456"
    )
    for host in ("0.0.0.0", "192.168.1.8", "runtime.example"):
        with pytest.raises(RuntimeError, match="refuses non-loopback"):
            server._required_runtime_host(host)
    assert server._required_runtime_host("127.0.0.1") == "127.0.0.1"


def test_pattern_database_default_is_install_relative(monkeypatch, tmp_path):
    monkeypatch.delenv("SYNTHESUS_DATA_DIR", raising=False)
    monkeypatch.setenv("SYNTHESUS_HOME", str(tmp_path / "install"))
    assert Path(_default_global_db_path()) == tmp_path / "install" / "data" / "pattern_lm.db"


def test_private_runtime_paths_are_globally_authenticated():
    protected = (
        "/api/v1/health",
        "/api/v1/settings/llm",
        "/api/v1/knowledge/memory",
        "/query",
        "/control/jobs",
        "/parameter-cloud/v2/parameters",
    )

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=server.app),
            base_url="http://runtime.test",
        ) as client:
            for path in protected:
                anonymous = await client.get(path)
                wrong = await client.get(path, headers={"X-API-Key": "wrong-key"})
                assert anonymous.status_code == 401, path
                assert wrong.status_code == 401, path
                assert anonymous.json() == {"error": "runtime_authentication_required"}

            accepted = await client.get(
                "/api/definitely-not-a-route",
                headers={"X-API-Key": server.ADMIN_KEY},
            )
            assert accepted.status_code == 404

            public_static = await client.get("/definitely-not-a-route")
            assert public_static.status_code == 404

    asyncio.run(exercise())


def test_get_auth_rejects_child_or_missing_keys():
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/query",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("127.0.0.1", 5010),
            "scheme": "http",
            "query_string": b"",
        }
    )

    with pytest.raises(Exception) as missing:
        asyncio.run(server.get_auth(request, x_api_key=None))
    assert getattr(missing.value, "status_code", None) == 401

    with pytest.raises(Exception) as child_key:
        asyncio.run(server.get_auth(request, x_api_key="sk-synth-child"))
    assert getattr(child_key.value, "status_code", None) == 401

    assert asyncio.run(server.get_auth(request, x_api_key=server.ADMIN_KEY)) == (
        True,
        "auth:install",
    )


class _FakeWebSocket:
    def __init__(self, key=None):
        self.headers = {} if key is None else {"X-API-Key": key}
        self.accepted = False
        self.close_code = None

    async def accept(self):
        self.accepted = True

    async def close(self, code):
        self.close_code = code

    async def receive_text(self):
        raise WebSocketDisconnect()

    async def send_json(self, _payload):
        raise AssertionError("test websocket should not receive a payload")


@pytest.mark.parametrize(
    "endpoint",
    [server.security_websocket, server.websocket_endpoint],
)
def test_runtime_websockets_authenticate_before_accept(endpoint):
    denied = _FakeWebSocket()
    asyncio.run(endpoint(denied))
    assert denied.close_code == 1008
    assert not denied.accepted

    wrong = _FakeWebSocket("wrong-key")
    asyncio.run(endpoint(wrong))
    assert wrong.close_code == 1008
    assert not wrong.accepted

    allowed = _FakeWebSocket(server.ADMIN_KEY)
    asyncio.run(endpoint(allowed))
    assert allowed.accepted
    assert allowed.close_code is None
