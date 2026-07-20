"""F-020 proof: cancel/stop produces terminal cleanup at every layer.

This test file proves the "Implement cancel/stop and prove terminal cleanup at
every layer" checklist item with real, signed-contract behaviour at three
distinct layers of the local execution spine:

1. Node agent (``services.private_mesh.node_agent.NodeAgent.cancel``): cancelling
   an admitted lease emits a signed, lease-bound CANCELLED lifecycle event,
   drives the workload into a terminal state, and makes any subsequent
   ``execute`` a DUPLICATE_TRANSITION that never reaches the container runner.

2. Job pipeline (``services.job_pipeline.LocalJobPipeline.cancel``): cancelling
   an admitted job terminalizes it as ``JobState.CANCELLED``, durably revokes
   the fenced lease at the control plane (lease state ``REVOKED``), drops the
   retained bundle, and the fake Podman runner is never invoked -- even if the
   job is subsequently ``run``.

3. Podman executor (``aivm.execution.PodmanExecutor``): a timed-out container run
   issues ``stop`` -> ``kill`` -> ``rm`` cleanup in order and returns a terminal
   FAILED result whose stable reason never leaks captured stderr.

The node-agent and job-pipeline layers reuse the exact end-to-end harnesses
already used by ``tests/private_mesh/test_execution_wiring.py`` and
``tests/private_mesh/test_job_pipeline.py`` (real admission, real durable
execution authority, faked container transport). The executor layer reuses the
``tests/aivm/test_podman_execution.py`` patterns, importing the runtime AIVM
package through the same ``sys.path`` insert that ``test_execution_wiring.py``
performs.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from contracts.chal_vsource.v1.canonical import document_sha256
from contracts.chal_vsource.v1.models import (
    LeaseState,
    LifecycleState,
    validate_lease_bound_lifecycle,
)
from services.job_pipeline import JobState
from services.private_mesh import NodeAgentStatus

# Reuse the fully-wired node-agent harness and the job-pipeline composition.
from tests.private_mesh.test_execution_wiring import _execute, _wiring
from tests.private_mesh.test_job_pipeline import _pipeline

# The runtime AIVM package lives outside the top-level import roots; reuse the
# exact path insert that test_execution_wiring.py already applies at import time
# so the executor layer can import PodmanExecutor and friends.
_RUNTIME_PACKAGES = (
    Path(__file__).resolve().parents[2] / "apps" / "synthesus" / "runtime" / "packages"
)
if str(_RUNTIME_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_PACKAGES))

from aivm.admission import AdmissionDecision, AdmissionStatus  # noqa: E402
from aivm.execution import (  # noqa: E402
    AdmittedExecutionRequest,
    AuthorityStatus,
    AuthorityVerification,
    CommandResult,
    ExecutionStatus,
    ExecutorPolicy,
    LeaseAuthority,
    PodmanExecutor,
    TrustedEntrypoint,
)
from contracts.aivm.v1 import AIVMWorkloadManifest  # noqa: E402


def _run_commands(harness) -> list[tuple[str, ...]]:
    return [command for command in harness.runner.commands if command[1] == "run"]


# ---------------------------------------------------------------------------
# Layer 1: node agent cancel -> signed CANCELLED, terminal, no execution.
# ---------------------------------------------------------------------------


def test_node_agent_cancel_signs_terminal_cancelled_and_blocks_execution(tmp_path):
    harness = _wiring(tmp_path)
    lease = harness.lease
    lease_sha256 = document_sha256(lease)

    # Precondition: the lease is admitted and no container has ever run.
    assert harness.agent.workload_state(lease.lease_id) is LifecycleState.ADMITTED
    assert _run_commands(harness) == []

    cancelled = harness.agent.cancel(
        lease_id=lease.lease_id,
        lease_sha256=lease_sha256,
        fencing_token=lease.fencing_token,
    )

    # A signed, lease-bound CANCELLED lifecycle event is produced.
    assert cancelled.status is NodeAgentStatus.CANCELLED
    assert cancelled.accepted
    assert cancelled.response is None
    assert len(cancelled.lifecycle_events) == 1
    event = cancelled.lifecycle_events[0]
    assert event.state is LifecycleState.CANCELLED
    assert event.previous_state is LifecycleState.ADMITTED
    # Signature/binding self-verify against the exact admitted lease revision.
    validate_lease_bound_lifecycle(event, lease)
    assert event.lease_id == lease.lease_id
    assert event.lease_sha256 == lease_sha256
    assert event.fencing_token == lease.fencing_token

    # The workload is now durably terminal at the node agent.
    assert harness.agent.workload_state(lease.lease_id) is LifecycleState.CANCELLED

    # A subsequent execute is rejected as a duplicate transition and never runs
    # a container.
    after_cancel = _execute(harness)
    assert after_cancel.status is NodeAgentStatus.DUPLICATE_TRANSITION
    assert not after_cancel.accepted
    assert _run_commands(harness) == []

    # Cancelling again is likewise a terminal duplicate transition (idempotent,
    # non-re-signing).
    again = harness.agent.cancel(
        lease_id=lease.lease_id,
        lease_sha256=lease_sha256,
        fencing_token=lease.fencing_token,
    )
    assert again.status is NodeAgentStatus.DUPLICATE_TRANSITION
    assert again.lifecycle_events == ()
    assert harness.agent.workload_state(lease.lease_id) is LifecycleState.CANCELLED


# ---------------------------------------------------------------------------
# Layer 2: job pipeline cancel -> CANCELLED, lease REVOKED, runner untouched.
# ---------------------------------------------------------------------------


def test_job_pipeline_cancel_revokes_lease_and_never_executes(tmp_path):
    harness, pipeline = _pipeline(tmp_path)

    record = pipeline.submit(bundle=harness.bundle, start=False)
    assert record.state is JobState.ADMITTED
    lease_id = record.lease_id
    assert lease_id is not None

    # The control-plane lease is active before cancellation.
    active = harness.ctx.service().get_lease(lease_id)
    assert active is not None
    assert active.state is LeaseState.ACTIVE

    cancelled = pipeline.cancel(record.job_id)
    assert cancelled is not None
    assert cancelled.state is JobState.CANCELLED
    assert cancelled.reason is None
    assert cancelled.completed_at is not None
    # The retained bundle is dropped once the job is terminal.
    assert cancelled._bundle is None

    # The fenced lease is durably revoked at the control plane.
    revoked = harness.ctx.service().get_lease(lease_id)
    assert revoked is not None
    assert revoked.state is LeaseState.REVOKED

    # No container was ever launched by the faked Podman runner.
    assert _run_commands(harness) == []

    # A post-cancel run is a no-op that stays CANCELLED and still never executes.
    after = pipeline.run(record.job_id)
    assert after is not None
    assert after.state is JobState.CANCELLED
    assert _run_commands(harness) == []

    # Cancelling a terminal job is idempotent and does not revive it.
    again = pipeline.cancel(record.job_id)
    assert again is not None
    assert again.state is JobState.CANCELLED
    assert _run_commands(harness) == []


# ---------------------------------------------------------------------------
# Layer 3: podman executor timeout -> stop/kill/rm cleanup, FAILED, no stderr.
# ---------------------------------------------------------------------------

_PAYLOAD = b"physical aivm cpu slice\n"
_IMAGE_DIGEST = "sha256:" + "1" * 64
_IMAGE_ID = "sha256:" + "2" * 64
_LOGICAL_IMAGE = f"aivm-cpu-safe@{_IMAGE_DIGEST}"
_IMMUTABLE_IMAGE = f"docker.io/library/archlinux@{_IMAGE_DIGEST}"
_NOW = datetime(2026, 7, 17, 12, 10, tzinfo=UTC)


def _executor_manifest() -> AIVMWorkloadManifest:
    payload_sha = hashlib.sha256(_PAYLOAD).hexdigest()
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
            "digest": _IMAGE_DIGEST,
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
        "filesystem": {"rootfs": "readonly", "writable_paths": [], "host_mounts": []},
        "network": {"mode": "deny", "allowlist": []},
        "artifacts": [
            {
                "schema": "planetary.aivm.artifact.v1",
                "artifact_id": "artifact:input:001",
                "uri": "artifact://private/input",
                "kind": "input",
                "sha256": payload_sha,
                "size_bytes": len(_PAYLOAD),
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
            "runtime_image": (
                f"{manifest.runtime_image.image_id}@{manifest.runtime_image.digest}"
            ),
            "entrypoint_id": manifest.entrypoint_id,
            "guard_status": "ok",
        },
    )


def _lease_authority() -> LeaseAuthority:
    return LeaseAuthority(
        account_id="account:owner:001",
        workload_id="workload:cpu:001",
        node_id="node:local:001",
        lease_id="lease:cpu:001",
        lease_sha256="3" * 64,
        fencing_token=7,
    )


def _executor_request() -> AdmittedExecutionRequest:
    manifest = _executor_manifest()
    return AdmittedExecutionRequest(manifest, _admitted(manifest), _lease_authority())


class _VerifiedAuthority:
    """Minimal authority verifier that consumes the exact admitted binding."""

    def verify_and_consume(self, request, *, expected_account_id, expected_node_id, now):
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


class _TimingOutRunner:
    """Fake Podman runner whose container ``run`` reports a timeout with stderr."""

    def __init__(self) -> None:
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
                    "Id": _IMAGE_ID,
                    "Digest": _IMAGE_DIGEST,
                    "RepoDigests": [_IMMUTABLE_IMAGE],
                }
            ]
            return CommandResult(command, 0, json.dumps(value).encode())
        if command[1] == "run":
            return CommandResult(
                command,
                -9,
                b"",
                b"secret backend detail",
                timed_out=True,
            )
        # stop / kill / rm control commands succeed.
        return CommandResult(command, 0)


def _private_directory(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True)
    path.chmod(0o700)
    return path


def _timeout_executor(tmp_path: Path, runner: _TimingOutRunner) -> PodmanExecutor:
    state = _private_directory(tmp_path / "state")
    artifacts = _private_directory(tmp_path / "artifacts")
    artifact = artifacts / hashlib.sha256(_PAYLOAD).hexdigest()
    artifact.write_bytes(_PAYLOAD)
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
        trusted_images={_LOGICAL_IMAGE: _IMMUTABLE_IMAGE},
        trusted_entrypoints={entrypoint.entrypoint_id: entrypoint},
        account_id="account:owner:001",
        node_id="node:local:001",
        stdout_limit_bytes=256,
        stderr_limit_bytes=64,
    )
    return PodmanExecutor(
        policy,
        authority_verifier=_VerifiedAuthority(),
        runner=runner,
        clock=lambda: _NOW,
    )


def test_podman_timeout_runs_stop_kill_rm_and_hides_stderr(tmp_path):
    runner = _TimingOutRunner()
    executor = _timeout_executor(tmp_path, runner)

    result = executor.execute(_executor_request())

    # Terminal FAILED with a stable reason; captured stderr is never exposed.
    assert result.status is ExecutionStatus.FAILED
    assert result.reason == "execution_timeout"
    assert result.evidence is None
    assert "secret" not in result.reason
    assert "backend" not in result.reason

    # Cleanup after the timed-out run issues stop -> kill -> rm, in that order.
    post_run: list[str] = []
    seen_run = False
    for command in runner.commands:
        if command[1] == "run":
            seen_run = True
            continue
        if seen_run:
            post_run.append(command[1])
    assert post_run == ["stop", "kill", "rm"]

    # The removal is forced and every control command targets the same container.
    stop = next(c for c in runner.commands if c[1] == "stop")
    kill = next(c for c in runner.commands if c[1] == "kill")
    rm = next(c for c in runner.commands if c[1] == "rm")
    assert "--ignore" in stop and stop[-1] == kill[-1] == rm[-1]
    assert "--force" in rm
    assert "--signal" in kill and "KILL" in kill
