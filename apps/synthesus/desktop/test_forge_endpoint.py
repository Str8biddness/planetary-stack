"""Server-side forge rendering.

Why this endpoint exists: the WebGL path is unavailable on surfaces without
WebGL2 — the GTK/WebKit shell is one — so without it the forge cannot render at
all there. It uses the same pinned CPU engine as the distributed renderer, so
what a browser receives is identical to what a mesh node would produce, rather
than a different and prettier fallback.

The tests that matter are the refusals: unauthenticated access, absurd sizes,
malformed recipes, and — the important one — refusing a large frame when the
native core is missing instead of hanging the controller for a minute.
"""

from __future__ import annotations

import asyncio
import struct

import httpx

import synthesusd
from test_synthesusd import _settings


def _app(tmp_path):
    socket_path = tmp_path / "terminal.sock"
    socket_path.touch()
    settings = _settings(socket_path)
    return synthesusd.create_app(settings), {"X-API-Key": settings.api_key}


def _run(app, call):
    async def go():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://controller.test"
        ) as client:
            return await call(client)

    return asyncio.run(go())


def _png_dimensions(data: bytes) -> tuple[int, int]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "response is not a PNG"
    return struct.unpack(">II", data[16:24])


def test_renders_a_png_from_a_recipe_code(tmp_path):
    app, auth = _app(tmp_path)

    def call(client):
        return client.post(
            "/api/forge/render",
            headers=auth,
            json={"code": "SF1.0.6.35.285.60.0.42", "width": 64, "height": 64, "quality": 16},
        )

    response = _run(app, call)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/png"
    assert _png_dimensions(response.content) == (64, 64)
    # The recipe actually rendered is echoed back, so a caller can reproduce it.
    assert response.headers["X-Forge-Recipe"] == "SF1.0.6.35.285.60.0.42"


def test_renders_from_explicit_fields(tmp_path):
    app, auth = _app(tmp_path)

    def call(client):
        return client.post(
            "/api/forge/render",
            headers=auth,
            json={"mode": 0, "hue": 285, "width": 48, "height": 48, "quality": 12},
        )

    response = _run(app, call)
    assert response.status_code == 200
    assert _png_dimensions(response.content) == (48, 48)


def test_requires_authentication(tmp_path):
    app, _ = _app(tmp_path)

    def call(client):
        return client.post("/api/forge/render", json={"width": 32, "height": 32})

    assert _run(app, call).status_code == 401


def test_absurd_sizes_are_refused(tmp_path):
    app, auth = _app(tmp_path)

    for payload in ({"width": 9000, "height": 9000}, {"width": 4, "height": 4}):
        def call(client, payload=payload):
            return client.post("/api/forge/render", headers=auth, json=payload)

        response = _run(app, call)
        assert response.status_code == 400
        assert response.json()["error"] == "size_out_of_range"


def test_absurd_quality_is_refused(tmp_path):
    app, auth = _app(tmp_path)

    def call(client):
        return client.post(
            "/api/forge/render", headers=auth,
            json={"width": 32, "height": 32, "quality": 100000},
        )

    response = _run(app, call)
    assert response.status_code == 400
    assert response.json()["error"] == "quality_out_of_range"


def test_malformed_recipe_is_refused_not_rendered(tmp_path):
    app, auth = _app(tmp_path)

    def call(client):
        return client.post(
            "/api/forge/render", headers=auth,
            json={"code": "not-a-recipe", "width": 32, "height": 32},
        )

    response = _run(app, call)
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_recipe"


def test_reports_whether_the_native_core_served_the_render(tmp_path):
    """Callers are told which engine ran, rather than having to infer it."""
    app, auth = _app(tmp_path)

    def call(client):
        return client.post(
            "/api/forge/render", headers=auth,
            json={"width": 32, "height": 32, "quality": 12},
        )

    response = _run(app, call)
    assert response.status_code == 200
    assert response.headers["X-Forge-Native"] in {"0", "1"}


def test_large_frame_is_refused_when_the_native_core_is_missing(tmp_path, monkeypatch):
    """A pure-Python render of a large frame takes tens of seconds. Refusing
    beats hanging the controller and looking like a crash."""
    import services.forge_render.engine as engine

    monkeypatch.setattr(engine, "_NATIVE", None)
    monkeypatch.setattr(engine, "_NATIVE_TRIED", True)

    app, auth = _app(tmp_path)

    def call(client):
        return client.post(
            "/api/forge/render", headers=auth,
            json={"width": 1024, "height": 1024, "quality": 48},
        )

    response = _run(app, call)
    assert response.status_code == 503
    assert response.json()["error"] == "native_core_missing"
