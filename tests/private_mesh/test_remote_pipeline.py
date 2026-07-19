"""build_remote_pipeline constructs a real-signature desktop→worker pipeline.

Uses the in-process worker CLI (real execute_job) behind a delivering local
carrier plus a fake Podman runner, so a job submitted through LocalJobPipeline
is really placed, admitted, and executed with real signed documents — no live
worker, no fabricated signatures.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

_RUNTIME_PACKAGES = (
    Path(__file__).resolve().parents[2] / "apps" / "synthesus" / "runtime" / "packages"
)
if str(_RUNTIME_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_PACKAGES))

import aivm.execution as aivm_execution
from contracts.aivm.v1 import AIVMWorkloadManifest, canonical_document_bytes
from services.job_pipeline import JobState
from services.private_mesh.ssh_smoke import NodeTarget
from services.remote_pipeline import build_remote_pipeline
from services.remote_worker_config import RemoteWorkerConfig
from services.unisync.storage import ContentAddressedStore
from tests.private_mesh.test_execution_wiring import (
    DOCUMENT_ARTIFACT_ID,
    DOCUMENT_PAYLOAD,
    FakeModelRunner,
    IMAGE_DIGEST,
    IMMUTABLE_IMAGE,
    MODEL_ARTIFACT_ID,
    MODEL_PAYLOAD,
    OUTPUT_ID,
    RESULT_DOCUMENT,
    _workload_manifest,
)
from tests.private_mesh.test_worker_cli import LocalCarrier

ACCOUNT = "account:owner:001"
SUBJECT = "node-agent:001"
NODE = "node:owner:a"


def _clock() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


class _DeliveringCarrier(LocalCarrier):
    def deliver_objects(self, target, objects):
        store = ContentAddressedStore(Path(target.remote_state_dir) / "inbox")
        for digest, payload in objects:
            assert store.put_bytes(payload) == digest


def _config(tmp_path: Path) -> RemoteWorkerConfig:
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text("dummy\n")
    identity = tmp_path / "id_ed25519"
    identity.write_text("dummy\n")
    target = NodeTarget(
        NODE,
        "worker",
        "SHA256:" + "a" * 43,
        "/usr/bin/python",
        "/repo",
        str(tmp_path / "worker-state"),
    )
    return RemoteWorkerConfig(
        target=target,
        account_id=ACCOUNT,
        subject_id=SUBJECT,
        image_ref=IMMUTABLE_IMAGE,
        image_digest=IMAGE_DIGEST,
        known_hosts=known_hosts,
        ssh_identity=identity,
    )


def _bundle() -> bytes:
    now = _clock()
    wire = _workload_manifest().model_dump(mode="json", by_alias=True)
    wire["account_id"] = ACCOUNT
    wire["issued_at"] = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    wire["expires_at"] = (now + timedelta(minutes=25)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for artifact in wire["artifacts"]:
        artifact["created_at"] = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = AIVMWorkloadManifest.model_validate_json(json.dumps(wire, separators=(",", ":")))
    return canonical_document_bytes(manifest)


def test_build_remote_pipeline_runs_a_real_signed_job(tmp_path, monkeypatch):
    real_executor = aivm_execution.PodmanExecutor

    class RunnerInjectingExecutor(real_executor):
        def __init__(self, policy, *, authority_verifier, runner=None, **kwargs):
            super().__init__(
                policy,
                authority_verifier=authority_verifier,
                runner=FakeModelRunner(),
                **kwargs,
            )

    monkeypatch.setattr(aivm_execution, "PodmanExecutor", RunnerInjectingExecutor)

    config = _config(tmp_path)
    carrier = _DeliveringCarrier()

    pipeline = build_remote_pipeline(
        config,
        state_dir=tmp_path / "authority",
        clock=_clock,
        carrier=carrier,
    )
    assert pipeline is not None

    # Deliver the model + document into the worker's mesh inbox.
    carrier.deliver_objects(
        config.target,
        (
            (hashlib.sha256(DOCUMENT_PAYLOAD).hexdigest(), DOCUMENT_PAYLOAD),
            (hashlib.sha256(MODEL_PAYLOAD).hexdigest(), MODEL_PAYLOAD),
        ),
    )

    record = pipeline.submit(bundle=_bundle(), workload_kind="evaluation")

    assert record.state is JobState.COMPLETED, record.reason
    result_sha = hashlib.sha256(RESULT_DOCUMENT).hexdigest()
    assert record.outputs[0]["sha256"] == result_sha
    assert record.outputs[0]["uri"] == f"artifact://aivm/result/{result_sha}"


def test_authority_keys_persist_across_construction(tmp_path):
    config = _config(tmp_path)
    carrier = _DeliveringCarrier()
    auth = tmp_path / "authority"

    p1 = build_remote_pipeline(config, state_dir=auth, clock=_clock, carrier=carrier)
    assert p1 is not None
    controller_key = (auth / "controller.key").read_bytes()
    scheduler_key = (auth / "scheduler.key").read_bytes()

    # Second construction reuses the same persistent owner-only identity.
    p2 = build_remote_pipeline(config, state_dir=auth, clock=_clock, carrier=carrier)
    assert p2 is not None
    assert (auth / "controller.key").read_bytes() == controller_key
    assert (auth / "scheduler.key").read_bytes() == scheduler_key
    assert oct((auth / "controller.key").stat().st_mode)[-3:] == "600"


def test_unreachable_worker_fails_closed(tmp_path):
    config = _config(tmp_path)

    class _DeadCarrier(LocalCarrier):
        def enroll(self, *args, **kwargs):
            raise OSError("worker unreachable")

    pipeline = build_remote_pipeline(
        config, state_dir=tmp_path / "authority", clock=_clock, carrier=_DeadCarrier()
    )
    assert pipeline is None
