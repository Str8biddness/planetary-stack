from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import stat
import sys
from pathlib import Path

import pytest

from aivm.admission import AdmissionDecision, AdmissionStatus
from aivm.execution import (
    AdmittedExecutionRequest,
    CommandResult,
    ExecutionStatus,
    ExecutorPolicy,
    LeaseAuthority,
    PodmanExecutor,
    ReplayRejected,
    ReplayStore,
    SubprocessCommandRunner,
    TrustedEntrypoint,
)
from contracts.aivm.v1 import AIVMWorkloadManifest, document_sha256


PAYLOAD = b"physical aivm cpu slice\n"
IMAGE_DIGEST = "sha256:" + "1" * 64
IMAGE_ID = "sha256:" + "2" * 64
LOGICAL_IMAGE = f"aivm-cpu-safe@{IMAGE_DIGEST}"
IMMUTABLE_IMAGE = f"docker.io/library/archlinux@{IMAGE_DIGEST}"


def _private_directory(path: Path) -> Path:
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return path


def _manifest(*, image_digest: str = IMAGE_DIGEST) -> AIVMWorkloadManifest:
    payload_sha = hashlib.sha256(PAYLOAD).hexdigest()
    wire = {
        "schema": "planetary.aivm.workload.v1",
        "manifest_id": "manifest:cpu:001",
        "account_id": "account:owner:001",
        "workload_id": "workload:cpu:001",
        "issued_at": "2026-07-17T12:00:00Z",
        "expires_at": "2026-07-17T12:30:00Z",
        "signer_key_id": "key:owner:001",
        "runtime_image": {
            "image_id": "aivm-cpu-safe",
            "digest": image_digest,
            "media_type": "application/vnd.oci.image.manifest.v1+json",
            "user": "aivm",
            "privileged": False,
            "host_network": False,
            "host_pid": False,
            "host_ipc": False,
            "devices": [],
        },
        "entrypoint_id": "aivm.copy.v1",
        "resources": {
            "cpu_millicores": 500,
            "memory_bytes": 67_108_864,
            "time_limit_seconds": 5,
            "process_limit": 8,
            "open_file_limit": 64,
            "output_bytes": 4096,
            "scratch_bytes": 0,
            "gpu_count": 0,
            "gpu_memory_bytes": 0,
        },
        "filesystem": {
            "rootfs": "readonly",
            "writable_paths": ["/work/output"],
            "host_mounts": [],
        },
        "network": {"mode": "deny", "allowlist": []},
        "artifacts": [
            {
                "schema": "planetary.aivm.artifact.v1",
                "artifact_id": "artifact:input:001",
                "uri": "artifact://private/input",
                "kind": "input",
                "sha256": payload_sha,
                "size_bytes": len(PAYLOAD),
                "media_type": "application/octet-stream",
                "content_encoding": "identity",
                "created_at": "2026-07-17T11:59:00Z",
                "mount_path": "/work/input/payload",
                "readonly": True,
            }
        ],
        "inputs": ["artifact:input:001"],
        "outputs": ["output:result:001"],
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


def _lease(*, fence: int = 7, lease_id: str = "lease:cpu:001") -> LeaseAuthority:
    return LeaseAuthority(
        account_id="account:owner:001",
        workload_id="workload:cpu:001",
        node_id="node:local:001",
        lease_id=lease_id,
        lease_sha256="3" * 64,
        fencing_token=fence,
    )


def _request(
    *, fence: int = 7, lease_id: str = "lease:cpu:001"
) -> AdmittedExecutionRequest:
    manifest = _manifest()
    return AdmittedExecutionRequest(
        manifest,
        _admitted(manifest),
        _lease(fence=fence, lease_id=lease_id),
    )


class FakePodmanRunner:
    def __init__(self, *, image_digest: str = IMAGE_DIGEST, run_result: CommandResult | None = None):
        self.image_digest = image_digest
        self.run_result = run_result
        self.commands: list[tuple[str, ...]] = []
        self.output_mutator = None

    @staticmethod
    def _output_path(command: tuple[str, ...]) -> Path:
        for index, item in enumerate(command):
            if item == "--volume" and ":/work/output:rw," in command[index + 1]:
                return Path(command[index + 1].split(":/work/output:rw,", 1)[0])
        raise AssertionError("output mount missing")

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
                    "Digest": self.image_digest,
                    "RepoDigests": [f"docker.io/library/archlinux@{self.image_digest}"],
                }
            ]
            return CommandResult(command, 0, json.dumps(value).encode())
        if command[1] == "run":
            output_path = self._output_path(command)
            if self.output_mutator is None:
                result = output_path / "result.bin"
                result.write_bytes(PAYLOAD)
                result.chmod(0o600)
            else:
                self.output_mutator(output_path)
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
            return CommandResult(command, 0, b"bounded stdout", b"")
        return CommandResult(command, 0)


def _executor(tmp_path: Path, runner: FakePodmanRunner) -> PodmanExecutor:
    state = _private_directory(tmp_path / "state")
    artifacts = _private_directory(tmp_path / "artifacts")
    outputs = _private_directory(tmp_path / "outputs")
    payload_sha = hashlib.sha256(PAYLOAD).hexdigest()
    artifact = artifacts / payload_sha
    artifact.write_bytes(PAYLOAD)
    artifact.chmod(0o600)
    entrypoint = TrustedEntrypoint(
        entrypoint_id="aivm.copy.v1",
        executable="/usr/bin/cp",
        arguments=(
            "--no-preserve=mode,ownership,timestamps",
            "/work/input/payload",
            "/work/output/result.bin",
        ),
        output_mount="/work/output",
        outputs=(("output:result:001", "result.bin"),),
    )
    policy = ExecutorPolicy(
        state_dir=state,
        artifact_dir=artifacts,
        output_dir=outputs,
        trusted_images={LOGICAL_IMAGE: IMMUTABLE_IMAGE},
        trusted_entrypoints={entrypoint.entrypoint_id: entrypoint},
        stdout_limit_bytes=64,
        stderr_limit_bytes=64,
        max_output_files=1,
        max_output_file_bytes=4096,
    )
    return PodmanExecutor(policy, runner=runner)


def test_success_binds_authority_and_emits_hardened_podman_argv(tmp_path):
    runner = FakePodmanRunner()
    executor = _executor(tmp_path, runner)

    result = executor.execute(_request())

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.evidence is not None
    evidence = result.evidence
    assert evidence.manifest_sha256 == document_sha256(_manifest())
    assert evidence.lease_sha256 == "3" * 64
    assert evidence.fencing_token == 7
    assert evidence.runtime_image == LOGICAL_IMAGE
    assert evidence.immutable_image_ref == IMMUTABLE_IMAGE
    assert evidence.cached_image_id == IMAGE_ID
    assert evidence.outputs[0]["sha256"] == hashlib.sha256(PAYLOAD).hexdigest()
    command = next(command for command in runner.commands if command[1] == "run")
    required = {
        "--pull=never",
        "--network=none",
        "--read-only",
        "--cap-drop=all",
        "--security-opt=no-new-privileges",
        "--userns=keep-id",
        "--ipc=private",
        "--pid=private",
        "--uts=private",
        "--log-driver=none",
    }
    assert required.issubset(command)
    assert command[command.index("--entrypoint") + 1] == "/usr/bin/cp"
    assert command[-4:] == (
        IMMUTABLE_IMAGE,
        "--no-preserve=mode,ownership,timestamps",
        "/work/input/payload",
        "/work/output/result.bin",
    )
    assert "sh" not in command and "bash" not in command
    claim = next((tmp_path / "state").glob("*.claim.json"))
    final = next((tmp_path / "state").glob("*.result.json"))
    assert stat.S_IMODE(claim.stat().st_mode) == 0o600
    assert stat.S_IMODE(final.stat().st_mode) == 0o600


def test_consumed_lease_id_cannot_run_again_even_with_a_new_fence(tmp_path):
    runner = FakePodmanRunner()
    executor = _executor(tmp_path, runner)

    first = executor.execute(_request())
    replay = executor.execute(_request())
    same_lease_renewed = executor.execute(_request(fence=8))
    new_lease = executor.execute(_request(fence=8, lease_id="lease:cpu:002"))

    assert first.ok
    assert replay.status is ExecutionStatus.REJECTED
    assert replay.reason == "authority_already_consumed"
    assert same_lease_renewed.status is ExecutionStatus.REJECTED
    assert new_lease.ok
    assert first.evidence.authority_sha256 != new_lease.evidence.authority_sha256


def test_request_requires_admission_and_exact_lease_identity():
    manifest = _manifest()
    rejected = AdmissionDecision(
        AdmissionStatus.REJECTED,
        "no",
        manifest_id=manifest.manifest_id,
        workload_id=manifest.workload_id,
        account_id=manifest.account_id,
    )
    with pytest.raises(Exception, match="manifest_not_admitted"):
        AdmittedExecutionRequest(manifest, rejected, _lease())
    with pytest.raises(Exception, match="invalid_lease_id"):
        LeaseAuthority(
            account_id="account:owner:001",
            workload_id="workload:cpu:001",
            node_id="node:local:001",
            lease_id="../escape",
            lease_sha256="3" * 64,
            fencing_token=7,
        )


def test_cached_image_digest_mismatch_fails_before_claim(tmp_path):
    runner = FakePodmanRunner(image_digest="sha256:" + "9" * 64)
    executor = _executor(tmp_path, runner)

    result = executor.execute(_request())

    assert result.status is ExecutionStatus.UNAVAILABLE
    assert result.reason == "cached_image_digest_mismatch"
    assert not list((tmp_path / "state").glob("*.claim.json"))
    assert not any(command[1] == "run" for command in runner.commands)


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "unexpected", "oversized"])
def test_unsafe_outputs_fail_closed(tmp_path, kind):
    runner = FakePodmanRunner()

    def mutate(output_path: Path) -> None:
        if kind == "symlink":
            (output_path / "result.bin").symlink_to("/etc/passwd")
        elif kind == "hardlink":
            source = output_path.parent / "hardlink-source"
            source.write_bytes(PAYLOAD)
            source.chmod(0o600)
            os.link(source, output_path / "result.bin")
        elif kind == "unexpected":
            result = output_path / "result.bin"
            result.write_bytes(PAYLOAD)
            result.chmod(0o600)
            extra = output_path / "extra.bin"
            extra.write_bytes(b"extra")
            extra.chmod(0o600)
        else:
            result = output_path / "result.bin"
            result.write_bytes(b"x" * 4097)
            result.chmod(0o600)

    runner.output_mutator = mutate
    executor = _executor(tmp_path, runner)

    result = executor.execute(_request())

    assert result.status is ExecutionStatus.FAILED
    assert result.evidence is None


def test_timeout_runs_stop_kill_and_remove_without_exposing_stderr(tmp_path):
    runner = FakePodmanRunner(
        run_result=CommandResult(
            ("placeholder",),
            -9,
            b"",
            b"secret backend detail",
            timed_out=True,
        )
    )
    executor = _executor(tmp_path, runner)

    result = executor.execute(_request())

    assert result.status is ExecutionStatus.FAILED
    assert result.reason == "execution_timeout"
    assert "secret" not in result.reason
    controls = [command[1] for command in runner.commands if command[1] != "run"]
    assert "stop" in controls
    assert "kill" in controls
    assert "rm" in controls


def test_truncated_process_output_fails_closed(tmp_path):
    runner = FakePodmanRunner(
        run_result=CommandResult(
            ("placeholder",),
            0,
            b"x" * 64,
            b"",
            stdout_truncated=True,
        )
    )
    executor = _executor(tmp_path, runner)

    result = executor.execute(_request())

    assert result.status is ExecutionStatus.FAILED
    assert result.reason == "process_output_limit_exceeded"


def test_subprocess_runner_bounds_streams_without_shell():
    runner = SubprocessCommandRunner()
    result = runner.run(
        (sys.executable, "-c", "import os; os.write(1, b'x' * 200000); os.write(2, b'y' * 200000)"),
        timeout_seconds=5,
        stdout_limit=1024,
        stderr_limit=2048,
    )
    assert result.exit_code == 0
    assert len(result.stdout) == 1024
    assert len(result.stderr) == 2048
    assert result.stdout_truncated and result.stderr_truncated


def _process_claim(state_dir: str, start, ready, results) -> None:
    store = ReplayStore(Path(state_dir))
    ready.put(True)
    start.wait(5)
    try:
        store.claim({"lease": "lease:cpu:001", "fence": 7})
    except ReplayRejected:
        results.put("rejected")
    else:
        results.put("claimed")


def test_replay_claim_is_atomic_across_processes(tmp_path):
    state = _private_directory(tmp_path / "state")
    context = multiprocessing.get_context("fork")
    start = context.Event()
    ready = context.Queue()
    results = context.Queue()
    processes = [
        context.Process(target=_process_claim, args=(str(state), start, ready, results))
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    assert ready.get(timeout=5) and ready.get(timeout=5)
    start.set()
    for process in processes:
        process.join(timeout=5)
        assert process.exitcode == 0
    assert sorted([results.get(timeout=5), results.get(timeout=5)]) == ["claimed", "rejected"]


@pytest.mark.skipif(
    not os.environ.get("AIVM_RUN_PODMAN_PHYSICAL"),
    reason="set AIVM_RUN_PODMAN_PHYSICAL=1 and AIVM_PODMAN_IMAGE_REF to run",
)
def test_physical_rootless_podman_fixed_entrypoint(tmp_path):
    immutable_ref = os.environ["AIVM_PODMAN_IMAGE_REF"]
    image_digest = immutable_ref.rsplit("@", 1)[1]
    manifest = _manifest(image_digest=image_digest)
    logical = f"aivm-cpu-safe@{image_digest}"
    state = _private_directory(tmp_path / "state")
    artifacts = _private_directory(tmp_path / "artifacts")
    outputs = _private_directory(tmp_path / "outputs")
    artifact = artifacts / hashlib.sha256(PAYLOAD).hexdigest()
    artifact.write_bytes(PAYLOAD)
    artifact.chmod(0o600)
    entrypoint = TrustedEntrypoint(
        "aivm.copy.v1",
        "/usr/bin/cp",
        (
            "--no-preserve=mode,ownership,timestamps",
            "/work/input/payload",
            "/work/output/result.bin",
        ),
        "/work/output",
        (("output:result:001", "result.bin"),),
    )
    executor = PodmanExecutor(
        ExecutorPolicy(
            state,
            artifacts,
            outputs,
            {logical: immutable_ref},
            {entrypoint.entrypoint_id: entrypoint},
        )
    )
    request = AdmittedExecutionRequest(manifest, _admitted(manifest), _lease())

    result = executor.execute(request)

    assert result.ok, result.reason
    assert result.evidence.outputs[0]["sha256"] == hashlib.sha256(PAYLOAD).hexdigest()
