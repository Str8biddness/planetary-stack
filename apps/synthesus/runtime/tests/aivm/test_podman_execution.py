from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import stat
import sys
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
NOW = datetime(2026, 7, 17, 12, 10, tzinfo=UTC)


def _private_directory(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True)
    path.chmod(0o700)
    return path


def _manifest(
    *,
    image_digest: str = IMAGE_DIGEST,
    mount_path: str = "/work/input/payload",
) -> AIVMWorkloadManifest:
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
        "entrypoint_id": "aivm.sha256.v1",
        "resources": {
            "cpu_millicores": 500,
            "memory_bytes": 67_108_864,
            "time_limit_seconds": 5,
            "process_limit": 8,
            "open_file_limit": 64,
            "output_bytes": 256,
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
                "artifact_id": "artifact:input:001",
                "uri": "artifact://private/input",
                "kind": "input",
                "sha256": payload_sha,
                "size_bytes": len(PAYLOAD),
                "media_type": "application/octet-stream",
                "content_encoding": "identity",
                "created_at": "2026-07-17T11:59:00Z",
                "mount_path": mount_path,
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


def _lease(
    *,
    fence: int = 7,
    lease_id: str = "lease:cpu:001",
    node_id: str = "node:local:001",
) -> LeaseAuthority:
    return LeaseAuthority(
        account_id="account:owner:001",
        workload_id="workload:cpu:001",
        node_id=node_id,
        lease_id=lease_id,
        lease_sha256="3" * 64,
        fencing_token=fence,
    )


def _request(
    *,
    fence: int = 7,
    lease_id: str = "lease:cpu:001",
    node_id: str = "node:local:001",
) -> AdmittedExecutionRequest:
    manifest = _manifest()
    return AdmittedExecutionRequest(
        manifest,
        _admitted(manifest),
        _lease(fence=fence, lease_id=lease_id, node_id=node_id),
    )


class FakeAuthorityVerifier:
    def __init__(
        self,
        *,
        status: AuthorityStatus = AuthorityStatus.VERIFIED,
        mutate=None,
        after_consume=None,
    ):
        self.status = status
        self.mutate = mutate
        self.after_consume = after_consume
        self.consumed: set[tuple[str, str, str]] = set()

    def verify_and_consume(
        self,
        request,
        *,
        expected_account_id,
        expected_node_id,
        now,
    ):
        scope = (expected_account_id, expected_node_id, request.lease.lease_id)
        if scope in self.consumed:
            return AuthorityVerification(
                AuthorityStatus.REJECTED,
                "verifier:test:001",
            )
        if self.status is not AuthorityStatus.VERIFIED:
            return AuthorityVerification(self.status, "verifier:test:001")
        record = {
            "status": AuthorityStatus.VERIFIED,
            "verifier_id": "verifier:test:001",
            "manifest_sha256": request.manifest_sha256,
            "account_id": request.manifest.account_id,
            "workload_id": request.manifest.workload_id,
            "node_id": request.lease.node_id,
            "lease_id": request.lease.lease_id,
            "lease_sha256": request.lease.lease_sha256,
            "fencing_token": request.lease.fencing_token,
            "consumed": True,
        }
        if self.mutate is not None:
            self.mutate(record)
        verification = AuthorityVerification(**record)
        if verification.binding_record() == {
            "manifest_sha256": request.manifest_sha256,
            "account_id": request.manifest.account_id,
            "workload_id": request.manifest.workload_id,
            "node_id": request.lease.node_id,
            "lease_id": request.lease.lease_id,
            "lease_sha256": request.lease.lease_sha256,
            "fencing_token": request.lease.fencing_token,
            "consumed": True,
        }:
            self.consumed.add(scope)
            if self.after_consume is not None:
                self.after_consume()
        return verification


class FakePodmanRunner:
    def __init__(
        self,
        *,
        image_digest: str = IMAGE_DIGEST,
        run_result: CommandResult | None = None,
        info_mutator=None,
    ):
        self.image_digest = image_digest
        self.run_result = run_result
        self.info_mutator = info_mutator
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
            if self.info_mutator is not None:
                self.info_mutator(value)
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
            digest = hashlib.sha256(PAYLOAD).hexdigest()
            return CommandResult(
                command,
                0,
                f"{digest}  /work/input/payload\n".encode("ascii"),
                b"",
            )
        return CommandResult(command, 0)


def _executor(
    tmp_path: Path,
    runner: FakePodmanRunner,
    *,
    max_input_file_bytes: int = 64 * 1024 * 1024,
    authority_verifier=None,
    clock=lambda: NOW,
) -> PodmanExecutor:
    state = _private_directory(tmp_path / "state")
    artifacts = _private_directory(tmp_path / "artifacts")
    payload_sha = hashlib.sha256(PAYLOAD).hexdigest()
    artifact = artifacts / payload_sha
    artifact.write_bytes(PAYLOAD)
    artifact.chmod(0o600)
    entrypoint = TrustedEntrypoint(
        entrypoint_id="aivm.sha256.v1",
        executable="/usr/bin/sha256sum",
        arguments=("/work/input/payload",),
        input_mounts=(("artifact:input:001", "/work/input/payload"),),
        output_id="output:result:001",
    )
    policy = ExecutorPolicy(
        state_dir=state,
        artifact_dir=artifacts,
        trusted_images={LOGICAL_IMAGE: IMMUTABLE_IMAGE},
        trusted_entrypoints={entrypoint.entrypoint_id: entrypoint},
        account_id="account:owner:001",
        node_id="node:local:001",
        stdout_limit_bytes=256,
        stderr_limit_bytes=64,
        max_input_file_bytes=max_input_file_bytes,
    )
    return PodmanExecutor(
        policy,
        authority_verifier=authority_verifier or FakeAuthorityVerifier(),
        runner=runner,
        clock=clock,
    )


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
    assert evidence.authority_verifier_id == "verifier:test:001"
    assert len(evidence.authority_verification_sha256) == 64
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
    assert command[command.index("--user") + 1] == f"{os.geteuid()}:{os.getegid()}"
    assert command[command.index("--user") + 1] != "0:0"
    assert command[command.index("--entrypoint") + 1] == "/usr/bin/sha256sum"
    assert command[-2:] == (
        IMMUTABLE_IMAGE,
        "/work/input/payload",
    )
    assert not any(":rw," in item for item in command)
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
    assert replay.reason == "execution_authority_rejected"
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


@pytest.mark.parametrize(
    "mutate",
    [
        lambda record: record.update(manifest_sha256="9" * 64),
        lambda record: record.update(fencing_token=record["fencing_token"] - 1),
    ],
)
def test_authority_substitution_or_stale_fence_is_rejected(tmp_path, mutate):
    runner = FakePodmanRunner()
    verifier = FakeAuthorityVerifier(mutate=mutate)
    executor = _executor(tmp_path, runner, authority_verifier=verifier)

    result = executor.execute(_request())

    assert result.status is ExecutionStatus.REJECTED
    assert result.reason == "execution_authority_binding_mismatch"
    assert not any(command[1] == "run" for command in runner.commands)


def test_caller_manifest_mutation_after_authority_cannot_change_execution(tmp_path):
    manifest = _manifest()
    original_digest = manifest.artifacts[0].sha256

    def mutate_caller_owned_graph():
        manifest.resources.cpu_millicores = 4_000
        manifest.resources.memory_bytes = 4 * 1024 * 1024 * 1024
        manifest.resources.time_limit_seconds = 900
        manifest.artifacts[0].sha256 = "9" * 64

    verifier = FakeAuthorityVerifier(after_consume=mutate_caller_owned_graph)
    runner = FakePodmanRunner()
    executor = _executor(tmp_path, runner, authority_verifier=verifier)
    request = AdmittedExecutionRequest(manifest, _admitted(manifest), _lease())

    result = executor.execute(request)

    assert result.ok, result.reason
    command = next(command for command in runner.commands if command[1] == "run")
    assert command[command.index("--cpus") + 1] == "0.500"
    assert command[command.index("--memory") + 1] == "67108864"
    volume = command[command.index("--volume") + 1]
    assert f"/{original_digest}:/work/input/payload:ro," in volume
    assert "9" * 64 not in volume
    assert request.manifest.resources.cpu_millicores == 500
    assert request.manifest.artifacts[0].sha256 == original_digest
    assert result.evidence.manifest_sha256 == request.manifest_sha256


def test_wrong_node_and_expired_manifest_are_rejected_before_authority_use(tmp_path):
    wrong_node_runner = FakePodmanRunner()
    wrong_node_verifier = FakeAuthorityVerifier()
    wrong_node_executor = _executor(
        tmp_path / "wrong-node",
        wrong_node_runner,
        authority_verifier=wrong_node_verifier,
    )

    wrong_node = wrong_node_executor.execute(_request(node_id="node:other:001"))

    assert wrong_node.status is ExecutionStatus.REJECTED
    assert wrong_node.reason == "executor_node_mismatch"
    assert not wrong_node_verifier.consumed
    assert not any(command[1] == "run" for command in wrong_node_runner.commands)

    expired_runner = FakePodmanRunner()
    expired_verifier = FakeAuthorityVerifier()
    expired_executor = _executor(
        tmp_path / "expired",
        expired_runner,
        authority_verifier=expired_verifier,
        clock=lambda: datetime(2026, 7, 17, 12, 30, tzinfo=UTC),
    )

    expired = expired_executor.execute(_request())

    assert expired.status is ExecutionStatus.REJECTED
    assert expired.reason == "manifest_outside_validity_window"
    assert not expired_verifier.consumed
    assert not any(command[1] == "run" for command in expired_runner.commands)


def test_cached_image_digest_mismatch_fails_before_claim(tmp_path):
    runner = FakePodmanRunner(image_digest="sha256:" + "9" * 64)
    executor = _executor(tmp_path, runner)

    result = executor.execute(_request())

    assert result.status is ExecutionStatus.UNAVAILABLE
    assert result.reason == "cached_image_digest_mismatch"
    assert not list((tmp_path / "state").glob("*.claim.json"))
    assert not any(command[1] == "run" for command in runner.commands)


@pytest.mark.parametrize(
    ("mutator", "reason"),
    [
        (
            lambda value: value["host"]["security"].update(rootless=False),
            "podman_not_rootless",
        ),
        (
            lambda value: value["host"]["security"].update(seccompEnabled=False),
            "podman_seccomp_unavailable",
        ),
        (
            lambda value: value["host"].update(cgroupVersion="v1"),
            "cgroup_v2_unavailable",
        ),
        (
            lambda value: value["host"].update(cgroupControllers=["cpu", "memory"]),
            "required_cgroup_controllers_unavailable",
        ),
    ],
)
def test_missing_host_isolation_capability_fails_before_claim(tmp_path, mutator, reason):
    runner = FakePodmanRunner(info_mutator=mutator)
    executor = _executor(tmp_path, runner)

    result = executor.execute(_request())

    assert result.status is ExecutionStatus.UNAVAILABLE
    assert result.reason == reason
    assert not list((tmp_path / "state").glob("*.claim.json"))
    assert not any(command[1] == "run" for command in runner.commands)


def test_input_symlink_and_oversize_fail_before_container_start(tmp_path):
    symlink_runner = FakePodmanRunner()
    symlink_executor = _executor(tmp_path / "symlink", symlink_runner)
    artifact = next((tmp_path / "symlink" / "artifacts").iterdir())
    artifact.unlink()
    artifact.symlink_to("/etc/passwd")

    symlink_result = symlink_executor.execute(_request())

    assert symlink_result.status is ExecutionStatus.REJECTED
    assert symlink_result.reason == "input_artifact_not_confined"
    assert not any(command[1] == "run" for command in symlink_runner.commands)

    oversized_runner = FakePodmanRunner()
    oversized_executor = _executor(
        tmp_path / "oversized",
        oversized_runner,
        max_input_file_bytes=len(PAYLOAD) - 1,
    )

    oversized_result = oversized_executor.execute(_request())

    assert oversized_result.status is ExecutionStatus.REJECTED
    assert oversized_result.reason == "input_artifact_too_large"
    assert not any(command[1] == "run" for command in oversized_runner.commands)


def test_manifest_cannot_shadow_a_trusted_runtime_path(tmp_path):
    runner = FakePodmanRunner()
    executor = _executor(tmp_path, runner)
    manifest = _manifest(mount_path="/usr/bin/sha256sum")
    request = AdmittedExecutionRequest(manifest, _admitted(manifest), _lease())

    result = executor.execute(request)

    assert result.status is ExecutionStatus.REJECTED
    assert result.reason == "manifest_input_destination_mismatch"
    assert not any(command[1] == "run" for command in runner.commands)


@pytest.mark.parametrize(
    ("stdout", "stderr"),
    [
        (b"0" * 64 + b"  /work/input/payload\n", b""),
        (hashlib.sha256(PAYLOAD).hexdigest().encode() + b"  /wrong\n", b""),
        (hashlib.sha256(PAYLOAD).hexdigest().encode() + b"  /work/input/payload\n", b"warning"),
    ],
)
def test_noncanonical_fixed_entrypoint_output_fails_closed(tmp_path, stdout, stderr):
    runner = FakePodmanRunner(
        run_result=CommandResult(("placeholder",), 0, stdout, stderr)
    )
    executor = _executor(tmp_path, runner)

    result = executor.execute(_request())

    assert result.status is ExecutionStatus.FAILED
    assert result.reason == "fixed_entrypoint_output_invalid"
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
    artifact = artifacts / hashlib.sha256(PAYLOAD).hexdigest()
    artifact.write_bytes(PAYLOAD)
    artifact.chmod(0o600)
    entrypoint = TrustedEntrypoint(
        entrypoint_id="aivm.sha256.v1",
        executable="/usr/bin/sha256sum",
        arguments=("/work/input/payload",),
        input_mounts=(("artifact:input:001", "/work/input/payload"),),
        output_id="output:result:001",
    )
    executor = PodmanExecutor(
        ExecutorPolicy(
            state_dir=state,
            artifact_dir=artifacts,
            trusted_images={logical: immutable_ref},
            trusted_entrypoints={entrypoint.entrypoint_id: entrypoint},
            account_id="account:owner:001",
            node_id="node:local:001",
            stdout_limit_bytes=256,
        ),
        authority_verifier=FakeAuthorityVerifier(),
        clock=lambda: NOW,
    )
    request = AdmittedExecutionRequest(manifest, _admitted(manifest), _lease())

    result = executor.execute(request)

    assert result.ok, result.reason
    assert result.evidence.outputs[0]["sha256"] == hashlib.sha256(PAYLOAD).hexdigest()
    assert result.evidence.outputs[0]["algorithm"] == "sha256"
