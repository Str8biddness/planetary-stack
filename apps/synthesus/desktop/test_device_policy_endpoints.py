"""Permission and evidence enforcement at the HTTP boundary.

The policy store has its own unit tests; these prove the controller actually
CONSULTS it — that a job is refused when the device is not permitted, and that
an unverified result is refused when the owner asked for enforcement.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json

import httpx
import pytest

import synthesusd
from device_policy import DevicePolicyStore
from test_synthesusd import _settings

WORKER = "node:test:worker"
BUNDLE = base64.b64encode(b"canonical manifest bytes").decode()


def _enrollment_record(node_id):
    """One record in the mesh's own wire shape. No real mesh is contacted."""
    digest = hashlib.sha256(node_id.encode("utf-8")).hexdigest()
    return {
        "schema": "planetary.unisync.mesh_enrollment_record.v1",
        "account_id": "account:test:home",
        "node_id": node_id,
        "sans": ["worker.mesh"],
        "certificate_sha256": digest,
        "public_key_sha256": digest[::-1],
        "serial_hex": "18a6e72395e56464a52c5e795a5d1975b995bbbd",
        "issuer": "CN=Unisync Mesh CA test",
        "not_before": "2026-07-20T18:36:12Z",
        # Far enough out that these tests do not start failing on a calendar
        # boundary; expiry behaviour itself is covered in test_mesh_discovery.
        "not_after": "2036-07-27T18:41:12Z",
        "status": "active",
        "revocation_reason": None,
        "enrolled_at": "2026-07-20T18:41:12Z",
        "revoked_at": None,
    }


def _write_registry(tmp_path, records):
    path = tmp_path / "enrollments.json"
    path.write_text(
        json.dumps(
            {
                "schema": "planetary.unisync.mesh_enrollment_registry.v1",
                "records": records,
            }
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


class _StubPipeline:
    """Pipeline that completes a job and reports a settable provenance state."""

    def __init__(self, evidence_status="verified"):
        class _Backend:
            last_evidence_status = evidence_status

        self._backend = _Backend()

    def submit(self, *, bundle, workload_kind):
        class _Record:
            def to_wire(self):
                return {"job_id": "job:stub:001", "state": "completed", "outputs": []}

        return _Record()

    def status(self, job_id):
        return None

    def result(self, job_id, output_sha256):
        return (b'{"label":"positive"}', "application/json")

    def cancel(self, job_id):
        return None


def _app(
    tmp_path,
    *,
    store=None,
    pipeline=None,
    worker_node_id=WORKER,
    mesh_registry_path=None,
):
    terminal_socket = tmp_path / "terminal.sock"
    terminal_socket.touch()
    return synthesusd.create_app(
        _settings(terminal_socket),
        job_pipeline=pipeline if pipeline is not None else _StubPipeline(),
        device_policy=store or DevicePolicyStore(tmp_path / "p" / "policy.json"),
        worker_node_id=worker_node_id,
        # Injected so no test depends on a mesh registry existing on the machine
        # running it. Defaults to a path that does not exist.
        mesh_registry_path=mesh_registry_path or (tmp_path / "no-such-registry.json"),
    )


def _run(app, coro_factory):
    async def go():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://controller.test"
        ) as client:
            return await coro_factory(client)

    return asyncio.run(go())


@pytest.fixture
def auth(tmp_path):
    """Auth headers matching the settings helper the other desktop tests use."""
    terminal_socket = tmp_path / "auth.sock"
    terminal_socket.touch()
    settings = _settings(terminal_socket)
    return {"X-API-Key": settings.api_key}


def test_job_is_refused_when_the_device_is_not_permitted(tmp_path, auth):
    """Default-deny: an un-permitted worker cannot be given work."""
    app = _app(tmp_path)

    async def call(client):
        return await client.post("/api/jobs", headers=auth, json={"bundle_base64": BUNDLE})

    response = _run(app, call)
    assert response.status_code == 403
    body = response.json()
    assert body["error"] == "device_not_permitted"
    assert body["capability"] == "run_inference"


def test_job_is_accepted_once_the_device_is_permitted(tmp_path, auth):
    store = DevicePolicyStore(tmp_path / "p" / "policy.json")
    store.add_device(device_id=WORKER, display_name="Worker", role="peer")
    store.set_capabilities(WORKER, {"run_inference": True})
    app = _app(tmp_path, store=store)

    async def call(client):
        return await client.post("/api/jobs", headers=auth, json={"bundle_base64": BUNDLE})

    assert _run(app, call).status_code == 200


def test_unverified_result_is_refused_while_enforcement_is_on(tmp_path, auth):
    store = DevicePolicyStore(tmp_path / "p" / "policy.json")
    store.add_device(device_id=WORKER, display_name="Worker", role="peer")
    store.set_capabilities(WORKER, {"run_inference": True, "return_results": True})
    app = _app(tmp_path, store=store, pipeline=_StubPipeline("invalid:bad signature"))

    async def call(client):
        return await client.get(
            f"/api/jobs/job:stub:001/results/{'0' * 64}", headers=auth
        )

    response = _run(app, call)
    assert response.status_code == 409
    assert response.json()["evidence_status"] == "invalid:bad signature"


def test_unverified_result_is_served_but_badged_when_enforcement_is_off(tmp_path, auth):
    """Turning enforcement off must not make the difference invisible."""
    store = DevicePolicyStore(tmp_path / "p" / "policy.json")
    store.add_device(device_id=WORKER, display_name="Worker", role="peer")
    store.set_capabilities(WORKER, {"run_inference": True, "return_results": True})
    store.set_require_verified_evidence(False)
    app = _app(tmp_path, store=store, pipeline=_StubPipeline("unsigned"))

    async def call(client):
        return await client.get(
            f"/api/jobs/job:stub:001/results/{'0' * 64}", headers=auth
        )

    response = _run(app, call)
    assert response.status_code == 200
    assert response.headers["X-Synthesus-Evidence-Status"] == "unsigned"


def test_verified_result_carries_a_verified_badge(tmp_path, auth):
    store = DevicePolicyStore(tmp_path / "p" / "policy.json")
    store.add_device(device_id=WORKER, display_name="Worker", role="peer")
    store.set_capabilities(WORKER, {"run_inference": True, "return_results": True})
    app = _app(tmp_path, store=store, pipeline=_StubPipeline("verified"))

    async def call(client):
        return await client.get(
            f"/api/jobs/job:stub:001/results/{'0' * 64}", headers=auth
        )

    response = _run(app, call)
    assert response.status_code == 200
    assert response.headers["X-Synthesus-Evidence-Status"] == "verified"


def test_result_is_refused_without_the_return_results_capability(tmp_path, auth):
    """Running work and returning its bytes are separate permissions."""
    store = DevicePolicyStore(tmp_path / "p" / "policy.json")
    store.add_device(device_id=WORKER, display_name="Worker", role="peer")
    store.set_capabilities(WORKER, {"run_inference": True})
    app = _app(tmp_path, store=store)

    async def call(client):
        return await client.get(
            f"/api/jobs/job:stub:001/results/{'0' * 64}", headers=auth
        )

    response = _run(app, call)
    assert response.status_code == 403
    assert response.json()["capability"] == "return_results"


def test_a_source_device_cannot_be_granted_execution_over_the_api(tmp_path, auth):
    """The camera boundary holds at the HTTP layer too."""
    store = DevicePolicyStore(tmp_path / "p" / "policy.json")
    store.add_device(
        device_id="device:camera:front", display_name="Camera", role="source"
    )
    app = _app(tmp_path, store=store)

    async def call(client):
        return await client.put(
            "/api/devices/device:camera:front/capabilities",
            headers=auth,
            json={"capabilities": {"run_inference": True}},
        )

    response = _run(app, call)
    assert response.status_code == 400
    assert "cannot be granted" in response.json()["error"]


def test_device_crud_round_trip(tmp_path, auth):
    app = _app(tmp_path)

    async def call(client):
        created = await client.post(
            "/api/devices",
            headers=auth,
            json={"device_id": WORKER, "display_name": "Worker", "role": "peer"},
        )
        listed = await client.get("/api/devices", headers=auth)
        toggled = await client.put(
            f"/api/devices/{WORKER}/capabilities",
            headers=auth,
            json={"capabilities": {"run_inference": True}},
        )
        removed = await client.delete(f"/api/devices/{WORKER}", headers=auth)
        after = await client.get("/api/devices", headers=auth)
        return created, listed, toggled, removed, after

    created, listed, toggled, removed, after = _run(app, call)
    assert created.status_code == 200
    assert created.json()["capabilities"] == {
        "run_inference": False,
        "return_results": False,
    }
    assert [d["device_id"] for d in listed.json()["devices"]] == [WORKER]
    assert toggled.json()["capabilities"]["run_inference"] is True
    assert removed.status_code == 200
    assert after.json()["devices"] == []


def test_discovered_nodes_are_offered_but_grant_nothing(tmp_path, auth):
    """THE property of discovery: enrollment is not consent.

    A node discovered from the mesh registry must be able to do nothing at all
    until the owner switches a capability on, exactly like a hand-typed row.
    """
    registry = _write_registry(tmp_path, [_enrollment_record(WORKER)])
    store = DevicePolicyStore(tmp_path / "p" / "policy.json")
    app = _app(tmp_path, store=store, mesh_registry_path=registry)

    async def call(client):
        discovered = await client.get("/api/devices/discovered", headers=auth)
        candidate = discovered.json()["candidates"][0]
        added = await client.post(
            "/api/devices",
            headers=auth,
            json={
                "device_id": candidate["node_id"],
                "display_name": candidate["suggested_display_name"],
                "role": "peer",
            },
        )
        # And the controller still refuses it work, because nothing was granted.
        job = await client.post("/api/jobs", headers=auth, json={"bundle_base64": BUNDLE})
        return discovered, candidate, added, job

    discovered, candidate, added, job = _run(app, call)
    assert discovered.status_code == 200
    assert candidate["node_id"] == WORKER
    assert added.status_code == 200
    assert added.json()["capabilities"] == {
        "run_inference": False,
        "return_results": False,
    }
    assert store.is_allowed(WORKER, "run_inference") is False
    assert store.is_allowed(WORKER, "return_results") is False
    assert job.status_code == 403
    assert job.json()["error"] == "device_not_permitted"


def test_discovery_does_not_write_to_the_policy(tmp_path, auth):
    """Reading the candidate list must not create device rows by itself."""
    registry = _write_registry(tmp_path, [_enrollment_record(WORKER)])
    store = DevicePolicyStore(tmp_path / "p" / "policy.json")
    app = _app(tmp_path, store=store, mesh_registry_path=registry)

    async def call(client):
        await client.get("/api/devices/discovered", headers=auth)
        return await client.get("/api/devices", headers=auth)

    assert _run(app, call).json()["devices"] == []
    assert store.devices() == []


def test_an_added_node_stops_being_offered(tmp_path, auth):
    registry = _write_registry(tmp_path, [_enrollment_record(WORKER)])
    store = DevicePolicyStore(tmp_path / "p" / "policy.json")
    store.add_device(device_id=WORKER, display_name="Worker", role="peer")
    app = _app(tmp_path, store=store, mesh_registry_path=registry)

    async def call(client):
        return await client.get("/api/devices/discovered", headers=auth)

    body = _run(app, call).json()
    assert body["candidates"] == []
    assert body["reason"] == "all_enrolled_nodes_already_listed"


def test_a_missing_registry_returns_an_empty_list_not_an_error(tmp_path, auth):
    """The permissions window must still open on a machine with no mesh state."""
    app = _app(tmp_path)

    async def call(client):
        return await client.get("/api/devices/discovered", headers=auth)

    response = _run(app, call)
    assert response.status_code == 200
    body = response.json()
    assert body["candidates"] == []
    assert body["reason"] == "registry_missing"


def test_discovery_requires_auth(tmp_path):
    app = _app(tmp_path)

    async def call(client):
        return await client.get("/api/devices/discovered")

    assert _run(app, call).status_code == 401


def test_settings_endpoints_require_auth(tmp_path):
    app = _app(tmp_path)

    async def call(client):
        return (
            await client.get("/api/settings"),
            await client.get("/api/devices"),
            await client.put("/api/settings/evidence", json={"enabled": False}),
        )

    for response in _run(app, call):
        assert response.status_code == 401


def test_evidence_toggle_persists_through_the_api(tmp_path, auth):
    store = DevicePolicyStore(tmp_path / "p" / "policy.json")
    app = _app(tmp_path, store=store)

    async def call(client):
        before = await client.get("/api/settings", headers=auth)
        changed = await client.put(
            "/api/settings/evidence", headers=auth, json={"enabled": False}
        )
        after = await client.get("/api/settings", headers=auth)
        return before, changed, after

    before, changed, after = _run(app, call)
    assert before.json()["require_verified_evidence"] is True
    assert changed.status_code == 200
    assert after.json()["require_verified_evidence"] is False
    assert store.require_verified_evidence() is False
