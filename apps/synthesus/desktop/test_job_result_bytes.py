"""Byte-exactness proof for GET /api/jobs/{job_id}/results/{output_sha256}.

The Web Desktop shows a "verified bytes" indicator only because this endpoint
returns exactly the payload the pipeline yields for a digest, unchanged, with
its declared media type. These tests pin that contract:

  * an authorized GET returns 200 with the EXACT bytes and media type,
  * a pipeline `.result(...) -> None` surfaces as 404 `result_not_found`,
  * an unauthenticated GET is rejected with 401.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

import synthesusd


# Real text-classification result schema, canonical bytes as stored by the
# pipeline. We assert the response body is identical to this, byte for byte.
_RESULT_BYTES = (
    b'{"document_sha256":"'
    b'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
    b'","feature_dims":256,"label":"positive","model_sha256":"'
    b'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
    b'","schema":"planetary.aivm.result.text-classification.v1",'
    b'"scores":{"negative":0.414381,"positive":0.585619}}'
)

_KNOWN_JOB = "job:mesh:42"
_KNOWN_SHA = "c" * 64


def _settings(socket_path: Path) -> synthesusd.ControllerSettings:
    return synthesusd.ControllerSettings(
        api_key="install-secret",
        terminal_token="launch-secret",
        session_id="session-1",
        runtime_url="http://runtime.test",
        terminal_socket=socket_path,
        allowed_origins=("http://127.0.0.1:8081",),
    )


class _FakeResultPipeline:
    """Returns byte-exact payload for one (job, sha); None for everything else."""

    def __init__(self):
        self.calls = []

    def result(self, job_id, output_sha256):
        self.calls.append((job_id, output_sha256))
        if job_id == _KNOWN_JOB and output_sha256 == _KNOWN_SHA:
            return _RESULT_BYTES, "application/json"
        return None

    # The endpoint only touches `.result`; the rest of the pipeline surface is
    # unused here but present so create_app wiring stays realistic.
    def submit(self, *, bundle, workload_kind):  # pragma: no cover - unused
        raise AssertionError("submit not exercised by result tests")

    def status(self, job_id):  # pragma: no cover - unused
        return None

    def cancel(self, job_id):  # pragma: no cover - unused
        return None


def _permissive_policy(tmp_path, node_id="node:test:worker"):
    """Policy store granting the test worker both peer capabilities.

    Job submission and result return are default-deny, so a test that wants to
    exercise the happy path must grant permission explicitly — the same as a
    real owner would.
    """
    from device_policy import DevicePolicyStore

    store = DevicePolicyStore(tmp_path / "policy" / "device-policy.json")
    store.add_device(device_id=node_id, display_name="Test worker", role="peer")
    store.set_capabilities(
        node_id, {"run_inference": True, "return_results": True}
    )
    # These tests exercise job/result plumbing, not provenance. Evidence
    # enforcement is ON by default and would refuse a stub pipeline that
    # reports no provenance at all; that behaviour has its own tests in
    # test_device_policy_endpoints.py.
    store.set_require_verified_evidence(False)
    return store


def test_result_endpoint_returns_exact_bytes_missing_and_unauthorized(tmp_path):
    terminal_socket = tmp_path / "terminal.sock"
    terminal_socket.touch()
    pipeline = _FakeResultPipeline()
    app = synthesusd.create_app(
        _settings(terminal_socket),
        job_pipeline=pipeline,
        device_policy=_permissive_policy(tmp_path),
        worker_node_id="node:test:worker",
    )

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://controller.test",
        ) as client:
            headers = {"X-API-Key": "install-secret"}

            # Authorized GET for the known digest: 200, exact bytes + media type.
            ok = await client.get(
                "/api/jobs/" + _KNOWN_JOB + "/results/" + _KNOWN_SHA,
                headers=headers,
            )
            assert ok.status_code == 200
            assert ok.headers["content-type"].startswith("application/json")
            # Byte-for-byte identity is the whole point of "verified bytes".
            assert ok.content == _RESULT_BYTES
            assert ok.json()["label"] == "positive"
            assert ok.json()["scores"] == {
                "negative": 0.414381,
                "positive": 0.585619,
            }

            # Pipeline returns None (unknown sha) -> honest 404 result_not_found.
            missing = await client.get(
                "/api/jobs/" + _KNOWN_JOB + "/results/" + ("d" * 64),
                headers=headers,
            )
            assert missing.status_code == 404
            assert missing.json()["error"] == "result_not_found"

            # Pipeline returns None (unknown job) -> also 404 result_not_found.
            missing_job = await client.get(
                "/api/jobs/job:mesh:404/results/" + _KNOWN_SHA,
                headers=headers,
            )
            assert missing_job.status_code == 404
            assert missing_job.json()["error"] == "result_not_found"

            # Unauthenticated GET is rejected before any pipeline call.
            denied = await client.get(
                "/api/jobs/" + _KNOWN_JOB + "/results/" + _KNOWN_SHA
            )
            assert denied.status_code == 401
            assert denied.json()["error"] == "unauthorized"

    asyncio.run(exercise())

    # The unauthorized request must not have reached the pipeline.
    assert (_KNOWN_JOB, _KNOWN_SHA) in pipeline.calls
    assert pipeline.calls.count((_KNOWN_JOB, _KNOWN_SHA)) == 1
