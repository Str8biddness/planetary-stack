"""Local job pipeline: authenticated desktop intent to verified result."""

from __future__ import annotations

import hashlib
from pathlib import Path

from contracts.chal_vsource.v1.models import LeaseState
from services.job_pipeline import JobState, LocalJobPipeline
from tests.private_mesh.test_execution_wiring import (
    RESULT_DOCUMENT,
    TEXT_CLASSIFICATION_RESULT_SCHEMA,
    _wiring,
)
from tests.vsource.test_local_control_plane import ACCOUNT, SUBJECT, capability_doc


def _result_loader(result_dir: Path):
    def load(sha256: str) -> bytes | None:
        path = result_dir / sha256
        try:
            return path.read_bytes()
        except OSError:
            return None

    return load


def _pipeline(tmp_path: Path):
    harness = _wiring(tmp_path, preadmit=False)
    ctx = harness.ctx
    pipeline = LocalJobPipeline(
        control_plane=ctx.service(),
        backend=harness.agent,
        request_signer=ctx.controller,
        capability_provider=lambda: capability_doc(ctx),
        authenticated_subject_id=SUBJECT,
        account_id=ACCOUNT,
        capability_id="capability:001",
        clock=ctx.clock.now,
        resource_vector={
            "cpu_millicores": 1_000,
            "memory_bytes": 1_024,
            "gpu_count": 0,
            "gpu_memory_bytes": 0,
            "storage_bytes": 0,
            "ingress_bps": 0,
            "egress_bps": 0,
        },
        result_loader=_result_loader(harness.result_dir),
    )
    return harness, pipeline


def test_submitted_job_completes_with_verified_outputs(tmp_path):
    harness, pipeline = _pipeline(tmp_path)

    record = pipeline.submit(bundle=harness.bundle)

    assert record.state is JobState.COMPLETED
    assert record.reason is None
    assert record.completed_at is not None
    assert len(record.outputs) == 2
    result_sha256 = hashlib.sha256(RESULT_DOCUMENT).hexdigest()
    assert record.outputs[0]["sha256"] == result_sha256
    assert record.report is not None

    wire = record.to_wire()
    assert wire["state"] == "completed"
    assert wire["outputs"][0]["uri"] == f"artifact://aivm/result/{result_sha256}"
    assert "report" not in wire

    stored = harness.result_dir / result_sha256
    stored_result = stored.read_bytes()
    assert hashlib.sha256(stored_result).hexdigest() == result_sha256
    assert TEXT_CLASSIFICATION_RESULT_SCHEMA.encode() in stored_result

    lease = harness.ctx.service().get_lease(record.lease_id)
    assert lease is not None
    assert lease.state is LeaseState.RELEASED

    assert pipeline.status(record.job_id) is record


def test_admitted_job_can_be_cancelled_and_never_executes(tmp_path):
    harness, pipeline = _pipeline(tmp_path)

    record = pipeline.submit(bundle=harness.bundle, start=False)
    assert record.state is JobState.ADMITTED

    cancelled = pipeline.cancel(record.job_id)
    assert cancelled is not None
    assert cancelled.state is JobState.CANCELLED

    lease = harness.ctx.service().get_lease(record.lease_id)
    assert lease is not None
    assert lease.state is LeaseState.REVOKED

    after = pipeline.run(record.job_id)
    assert after is not None
    assert after.state is JobState.CANCELLED
    assert [
        command for command in harness.runner.commands if command[1] == "run"
    ] == []


def test_garbage_bundle_fails_terminally_without_fabricated_success(tmp_path):
    harness, pipeline = _pipeline(tmp_path)

    record = pipeline.submit(bundle=b"this is not a signed workload manifest")

    assert record.state is JobState.FAILED
    assert record.reason == "bundle_not_a_workload_manifest"
    assert record.outputs == ()
    assert [
        command for command in harness.runner.commands if command[1] == "run"
    ] == []


def test_completed_job_result_is_served_only_verified(tmp_path):
    harness, pipeline = _pipeline(tmp_path)
    record = pipeline.submit(bundle=harness.bundle)
    assert record.state is JobState.COMPLETED
    result_sha256 = hashlib.sha256(RESULT_DOCUMENT).hexdigest()

    loaded = pipeline.result(record.job_id, result_sha256)
    assert loaded is not None
    payload, media_type = loaded
    assert payload == RESULT_DOCUMENT
    assert media_type == "application/json"

    assert pipeline.result("job:unknown:000", result_sha256) is None
    assert pipeline.result(record.job_id, "f" * 64) is None
    assert pipeline.result(record.job_id, "not-a-digest") is None

    stored = harness.result_dir / result_sha256
    stored.chmod(0o600)
    stored.write_bytes(b"tampered result bytes")
    assert pipeline.result(record.job_id, result_sha256) is None


def test_out_of_policy_submissions_are_rejected_before_allocation(tmp_path):
    harness, pipeline = _pipeline(tmp_path)

    empty = pipeline.submit(bundle=b"")
    oversized = pipeline.submit(bundle=b"x" * (8 * 1024 * 1024 + 1))
    bad_kind = pipeline.submit(bundle=harness.bundle, workload_kind="shell")

    assert empty.state is JobState.REJECTED
    assert oversized.state is JobState.REJECTED
    assert bad_kind.state is JobState.REJECTED
    assert bad_kind.reason == "unsupported workload kind"
    assert pipeline.status("job:unknown:000") is None
