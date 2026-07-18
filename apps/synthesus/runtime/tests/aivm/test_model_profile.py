"""Adversarial tests for the bounded JSON useful-model execution profile."""

from __future__ import annotations

import hashlib
import json
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from aivm.admission import AdmissionDecision, AdmissionStatus
from aivm.execution import (
    AdmittedExecutionRequest,
    AuthorityStatus,
    AuthorityVerification,
    CommandResult,
    ExecutionStatus,
    ExecutorPolicy,
    LeaseAuthority,
    PodmanExecutor,
    TEXT_CLASSIFICATION_RESULT_SCHEMA,
    TrustedEntrypoint,
    text_classification_entrypoint,
)
from contracts.aivm.v1 import AIVMWorkloadManifest


MODEL_PAYLOAD = b"onnx model artifact bytes"
DOCUMENT_PAYLOAD = b"planetary stack useful workload document\n"
IMAGE_DIGEST = "sha256:" + "4" * 64
IMAGE_ID = "sha256:" + "5" * 64
LOGICAL_IMAGE = f"aivm-text-classify@{IMAGE_DIGEST}"
IMMUTABLE_IMAGE = f"localhost/aivm-text-classify@{IMAGE_DIGEST}"
NOW = datetime(2026, 7, 18, 12, 10, tzinfo=UTC)

MODEL_ARTIFACT_ID = "artifact:model:001"
DOCUMENT_ARTIFACT_ID = "artifact:document:001"
OUTPUT_ID = "output:classification:001"

RESULT_DOCUMENT = json.dumps(
    {
        "schema": TEXT_CLASSIFICATION_RESULT_SCHEMA,
        "document_sha256": hashlib.sha256(DOCUMENT_PAYLOAD).hexdigest(),
        "feature_dims": 256,
        "label": "positive",
        "model_sha256": hashlib.sha256(MODEL_PAYLOAD).hexdigest(),
        "scores": {"negative": 0.117702, "positive": 0.882298},
    },
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=True,
).encode("ascii") + b"\n"


def _private_directory(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True)
    path.chmod(0o700)
    return path


def _entrypoint() -> TrustedEntrypoint:
    return text_classification_entrypoint(
        model_artifact_id=MODEL_ARTIFACT_ID,
        document_artifact_id=DOCUMENT_ARTIFACT_ID,
        output_id=OUTPUT_ID,
    )


def _manifest() -> AIVMWorkloadManifest:
    wire = {
        "schema": "planetary.aivm.workload.v1",
        "manifest_id": "manifest:model:001",
        "account_id": "account:owner:001",
        "workload_id": "workload:model:001",
        "issued_at": "2026-07-18T12:00:00Z",
        "expires_at": "2026-07-18T12:30:00Z",
        "signer_key_id": "key:owner:001",
        "runtime_image": {
            "image_id": "aivm-text-classify",
            "digest": IMAGE_DIGEST,
            "media_type": "application/vnd.oci.image.manifest.v1+json",
            "user": "aivm",
            "privileged": False,
            "host_network": False,
            "host_pid": False,
            "host_ipc": False,
            "devices": [],
        },
        "entrypoint_id": "aivm.model.text-classify.v1",
        "resources": {
            "cpu_millicores": 1000,
            "memory_bytes": 268_435_456,
            "time_limit_seconds": 30,
            "process_limit": 16,
            "open_file_limit": 64,
            "output_bytes": 4096,
            "scratch_bytes": 0,
            "gpu_count": 0,
            "gpu_memory_bytes": 0,
        },
        "filesystem": {
            "rootfs": "readonly",
            "writable_paths": [],
            "host_mounts": [],
        },
        "network": {"mode": "deny", "allowlist": []},
        "artifacts": [
            {
                "schema": "planetary.aivm.artifact.v1",
                "artifact_id": DOCUMENT_ARTIFACT_ID,
                "uri": "artifact://private/document",
                "kind": "input",
                "sha256": hashlib.sha256(DOCUMENT_PAYLOAD).hexdigest(),
                "size_bytes": len(DOCUMENT_PAYLOAD),
                "media_type": "text/plain",
                "content_encoding": "identity",
                "created_at": "2026-07-18T11:59:00Z",
                "mount_path": "/work/input/document.txt",
                "readonly": True,
            },
            {
                "schema": "planetary.aivm.artifact.v1",
                "artifact_id": MODEL_ARTIFACT_ID,
                "uri": "artifact://private/model",
                "kind": "model",
                "sha256": hashlib.sha256(MODEL_PAYLOAD).hexdigest(),
                "size_bytes": len(MODEL_PAYLOAD),
                "media_type": "application/octet-stream",
                "content_encoding": "identity",
                "created_at": "2026-07-18T11:59:00Z",
                "mount_path": "/work/input/model.onnx",
                "readonly": True,
            },
        ],
        "inputs": [DOCUMENT_ARTIFACT_ID, MODEL_ARTIFACT_ID],
        "outputs": [OUTPUT_ID],
        "signature": {
            "algorithm": "ed25519",
            "key_id": "key:owner:001",
            "value": "A" * 86,
        },
    }
    return AIVMWorkloadManifest.model_validate_json(json.dumps(wire, separators=(",", ":")))


def _admitted(manifest: AIVMWorkloadManifest) -> AdmissionDecision:
    return AdmissionDecision(
        AdmissionStatus.ADMITTED,
        "manifest admitted",
        manifest_id=manifest.manifest_id,
        workload_id=manifest.workload_id,
        account_id=manifest.account_id,
        evidence={
            "runtime_image": f"{manifest.runtime_image.image_id}@{manifest.runtime_image.digest}",
            "entrypoint_id": manifest.entrypoint_id,
            "guard_status": "ok",
        },
    )


def _lease(*, fence: int = 11, lease_id: str = "lease:model:001") -> LeaseAuthority:
    return LeaseAuthority(
        account_id="account:owner:001",
        workload_id="workload:model:001",
        node_id="node:local:001",
        lease_id=lease_id,
        lease_sha256="6" * 64,
        fencing_token=fence,
    )


def _request(*, fence: int = 11, lease_id: str = "lease:model:001") -> AdmittedExecutionRequest:
    manifest = _manifest()
    return AdmittedExecutionRequest(
        manifest,
        _admitted(manifest),
        _lease(fence=fence, lease_id=lease_id),
    )


class FakeAuthorityVerifier:
    def __init__(self, *, track_consumption: bool = True) -> None:
        self.track_consumption = track_consumption
        self.consumed: set[tuple[str, str, str]] = set()

    def verify_and_consume(self, request, *, expected_account_id, expected_node_id, now):
        scope = (expected_account_id, expected_node_id, request.lease.lease_id)
        if self.track_consumption and scope in self.consumed:
            return AuthorityVerification(AuthorityStatus.REJECTED, "verifier:test:001")
        self.consumed.add(scope)
        return AuthorityVerification(
            AuthorityStatus.VERIFIED,
            "verifier:test:001",
            manifest_sha256=request.manifest_sha256,
            account_id=request.manifest.account_id,
            workload_id=request.manifest.workload_id,
            node_id=request.lease.node_id,
            lease_id=request.lease.lease_id,
            lease_sha256=request.lease.lease_sha256,
            fencing_token=request.lease.fencing_token,
            consumed=True,
        )


class FakeModelRunner:
    def __init__(self, *, run_result: CommandResult | None = None) -> None:
        self.run_result = run_result
        self.commands: list[tuple[str, ...]] = []

    def run(self, argv, *, timeout_seconds, stdout_limit, stderr_limit):
        command = tuple(argv)
        self.commands.append(command)
        if command[1] == "info":
            value = {
                "host": {
                    "cgroupVersion": "v2",
                    "cgroupControllers": ["pids", "memory", "cpu"],
                    "security": {"rootless": True, "seccompEnabled": True},
                },
                "version": {"Version": "5.0.0-test"},
            }
            return CommandResult(command, 0, json.dumps(value).encode())
        if command[1:3] == ("image", "inspect"):
            value = [
                {
                    "Id": IMAGE_ID,
                    "Digest": IMAGE_DIGEST,
                    "RepoDigests": [IMMUTABLE_IMAGE],
                }
            ]
            return CommandResult(command, 0, json.dumps(value).encode())
        if command[1] == "run":
            if self.run_result is not None:
                return CommandResult(
                    command,
                    self.run_result.exit_code,
                    self.run_result.stdout,
                    self.run_result.stderr,
                    self.run_result.timed_out,
                    self.run_result.stdout_truncated,
                    self.run_result.stderr_truncated,
                )
            return CommandResult(command, 0, RESULT_DOCUMENT, b"")
        return CommandResult(command, 0)


def _executor(
    tmp_path: Path,
    runner: FakeModelRunner,
    *,
    authority_verifier: FakeAuthorityVerifier | None = None,
) -> PodmanExecutor:
    state = _private_directory(tmp_path / "state")
    artifacts = _private_directory(tmp_path / "artifacts")
    results = _private_directory(tmp_path / "results")
    for payload in (MODEL_PAYLOAD, DOCUMENT_PAYLOAD):
        artifact = artifacts / hashlib.sha256(payload).hexdigest()
        artifact.write_bytes(payload)
        artifact.chmod(0o600)
    entrypoint = _entrypoint()
    policy = ExecutorPolicy(
        state_dir=state,
        artifact_dir=artifacts,
        result_dir=results,
        trusted_images={LOGICAL_IMAGE: IMMUTABLE_IMAGE},
        trusted_entrypoints={entrypoint.entrypoint_id: entrypoint},
        account_id="account:owner:001",
        node_id="node:local:001",
        stdout_limit_bytes=4096,
        stderr_limit_bytes=256,
    )
    return PodmanExecutor(
        policy,
        authority_verifier=authority_verifier or FakeAuthorityVerifier(),
        runner=runner,
        clock=lambda: NOW,
    )


def test_profile_entrypoint_is_fixed_and_sorted():
    entrypoint = _entrypoint()
    assert entrypoint.output_transport == "bounded_stdout_json"
    assert entrypoint.result_schema == TEXT_CLASSIFICATION_RESULT_SCHEMA
    assert entrypoint.input_mounts == (
        (DOCUMENT_ARTIFACT_ID, "/work/input/document.txt"),
        (MODEL_ARTIFACT_ID, "/work/input/model.onnx"),
    )
    with pytest.raises(ValueError):
        text_classification_entrypoint(
            model_artifact_id=MODEL_ARTIFACT_ID,
            document_artifact_id=MODEL_ARTIFACT_ID,
            output_id=OUTPUT_ID,
        )


def test_entrypoint_transport_and_schema_validation():
    with pytest.raises(ValueError):
        TrustedEntrypoint(
            entrypoint_id="aivm.model.bad.v1",
            executable="/opt/aivm/bin/aivm-text-classify",
            arguments=(),
            input_mounts=((MODEL_ARTIFACT_ID, "/work/input/model.onnx"),),
            output_id=OUTPUT_ID,
            output_transport="raw_stream",
        )
    with pytest.raises(ValueError):
        TrustedEntrypoint(
            entrypoint_id="aivm.model.bad.v1",
            executable="/opt/aivm/bin/aivm-text-classify",
            arguments=(),
            input_mounts=((MODEL_ARTIFACT_ID, "/work/input/model.onnx"),),
            output_id=OUTPUT_ID,
            output_transport="bounded_stdout_json",
            result_schema="",
        )
    with pytest.raises(ValueError):
        TrustedEntrypoint(
            entrypoint_id="aivm.sha256.bad.v1",
            executable="/usr/bin/sha256sum",
            arguments=("/work/input/payload",),
            input_mounts=((MODEL_ARTIFACT_ID, "/work/input/model.onnx"),),
            output_id=OUTPUT_ID,
            result_schema="planetary.aivm.result.text-classification.v1",
        )


def test_model_entrypoints_require_a_result_directory(tmp_path):
    entrypoint = _entrypoint()
    with pytest.raises(ValueError, match="result directory"):
        ExecutorPolicy(
            state_dir=tmp_path / "state",
            artifact_dir=tmp_path / "artifacts",
            trusted_images={LOGICAL_IMAGE: IMMUTABLE_IMAGE},
            trusted_entrypoints={entrypoint.entrypoint_id: entrypoint},
            account_id="account:owner:001",
            node_id="node:local:001",
        )


def test_model_success_persists_content_addressed_result(tmp_path):
    runner = FakeModelRunner()
    executor = _executor(tmp_path, runner)

    result = executor.execute(_request())

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.evidence is not None
    evidence = result.evidence
    result_sha256 = hashlib.sha256(RESULT_DOCUMENT).hexdigest()
    output = evidence.outputs[0]
    assert output["transport"] == "bounded_stdout_json"
    assert output["result_schema"] == TEXT_CLASSIFICATION_RESULT_SCHEMA
    assert output["sha256"] == result_sha256
    assert output["size_bytes"] == len(RESULT_DOCUMENT)
    assert output["uri"] == f"artifact://aivm/result/{result_sha256}"
    assert output["input_artifact_ids"] == [DOCUMENT_ARTIFACT_ID, MODEL_ARTIFACT_ID]
    assert evidence.wall_time_ms >= 0

    stored = tmp_path / "results" / result_sha256
    assert stored.read_bytes() == RESULT_DOCUMENT
    assert stat.S_IMODE(stored.lstat().st_mode) == 0o400

    run_command = next(command for command in runner.commands if command[1] == "run")
    joined = " ".join(run_command)
    assert "--network=none" in joined
    assert "--read-only" in joined
    assert f"/work/input/document.txt:ro,nosuid,nodev,noexec" in joined
    assert f"/work/input/model.onnx:ro,nosuid,nodev,noexec" in joined
    assert run_command[-2:] == ("/work/input/model.onnx", "/work/input/document.txt")


@pytest.mark.parametrize(
    ("stdout", "stderr", "reason"),
    [
        (b"", b"", "model_result_output_invalid"),
        (b"not json\n", b"", "model_result_output_invalid"),
        (b"[1,2,3]\n", b"", "model_result_output_invalid"),
        (b'{"a":1,"a":2}\n', b"", "model_result_output_invalid"),
        (RESULT_DOCUMENT, b"warning\n", "model_result_output_invalid"),
        (
            b'{"schema":"planetary.aivm.result.other.v1"}\n',
            b"",
            "model_result_schema_mismatch",
        ),
    ],
)
def test_noncanonical_model_output_fails_closed(tmp_path, stdout, stderr, reason):
    runner = FakeModelRunner(
        run_result=CommandResult((), 0, stdout, stderr),
    )
    executor = _executor(tmp_path, runner)

    result = executor.execute(_request())

    assert result.status is ExecutionStatus.FAILED
    assert result.reason == reason
    result_dir = tmp_path / "results"
    assert list(result_dir.iterdir()) == []


def test_consumed_model_authority_cannot_run_again(tmp_path):
    runner = FakeModelRunner()
    executor = _executor(tmp_path, runner)

    first = executor.execute(_request())
    replay = executor.execute(_request())

    assert first.status is ExecutionStatus.SUCCEEDED
    assert replay.status is ExecutionStatus.REJECTED
    assert replay.reason == "execution_authority_rejected"


def test_local_replay_store_rejects_even_a_permissive_authority(tmp_path):
    runner = FakeModelRunner()
    executor = _executor(
        tmp_path,
        runner,
        authority_verifier=FakeAuthorityVerifier(track_consumption=False),
    )

    first = executor.execute(_request())
    replay = executor.execute(_request())

    assert first.status is ExecutionStatus.SUCCEEDED
    assert replay.status is ExecutionStatus.REJECTED
    assert replay.reason == "authority_already_consumed"


def test_existing_identical_result_is_idempotent(tmp_path):
    runner = FakeModelRunner()
    executor = _executor(tmp_path, runner)
    result_sha256 = hashlib.sha256(RESULT_DOCUMENT).hexdigest()
    stored = tmp_path / "results" / result_sha256
    stored.write_bytes(RESULT_DOCUMENT)
    stored.chmod(0o400)

    result = executor.execute(_request())

    assert result.status is ExecutionStatus.SUCCEEDED
    assert stored.read_bytes() == RESULT_DOCUMENT


def test_corrupt_result_store_entry_fails_unavailable(tmp_path):
    runner = FakeModelRunner()
    executor = _executor(tmp_path, runner)
    result_sha256 = hashlib.sha256(RESULT_DOCUMENT).hexdigest()
    stored = tmp_path / "results" / result_sha256
    stored.write_bytes(b"tampered bytes that do not match the digest")

    result = executor.execute(_request())

    assert result.status is ExecutionStatus.UNAVAILABLE
    assert result.reason == "result_persist_failed"
