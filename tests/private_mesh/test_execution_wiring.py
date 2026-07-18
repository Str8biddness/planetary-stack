"""End-to-end wiring: CHAL lease/request through the real AIVM boundary.

This is the F-020 local proof that node-agent completion is no longer an
in-process shortcut: the signed workload bundle must be an exact canonical
AIVM manifest, admission and the durable execution authority both run for
real, the (faked-transport) Podman executor produces a content-addressed
model result with evidence, and the node agent signs lease-bound lifecycle
and response documents around the outcome.  Container transport itself is
exercised physically on Podman workers via AIVM_RUN_PODMAN_PHYSICAL.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

_RUNTIME_PACKAGES = (
    Path(__file__).resolve().parents[2] / "apps" / "synthesus" / "runtime" / "packages"
)
if str(_RUNTIME_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_PACKAGES))

from aivm.admission import (  # noqa: E402
    AIVMAdmissionController,
    AdmissionPolicy,
    DocumentVerification,
    HostIsolationCapabilities,
    StaticHostCapabilityProbe,
)
from aivm.execution import (  # noqa: E402
    CommandResult,
    ExecutorPolicy,
    PersistentExecutionAuthority,
    PodmanExecutor,
    TEXT_CLASSIFICATION_RESULT_SCHEMA,
    text_classification_entrypoint,
)
from aivm.execution.chal_adapter import (  # noqa: E402
    AIVM_EVIDENCE_MEDIA_TYPE,
    ChalWorkloadExecutor,
)
from contracts.aivm.v1 import (  # noqa: E402
    AIVMWorkloadManifest,
    canonical_document_bytes,
)
from contracts.chal_vsource.v1.models import (  # noqa: E402
    LifecycleState,
    ResponseStatus,
    validate_lease_bound_lifecycle,
    validate_lease_bound_response,
)
from services.private_mesh import (  # noqa: E402
    Ed25519DocumentVerifier,
    NodeAgent,
    NodeAgentStatus,
)
from services.vsource import VSourceStatus  # noqa: E402
from tests.private_mesh.test_node_agent import (  # noqa: E402
    NODE_ID,
    _add_scheduler_key,
)
from tests.vsource.test_local_control_plane import (  # noqa: E402
    ACCOUNT,
    SCHEDULER,
    SUBJECT,
    allocate_once,
    capability_doc,
    inventory_doc,
    mesh_context,
    request_doc,
)


MODEL_PAYLOAD = b"onnx model artifact bytes"
DOCUMENT_PAYLOAD = b"planetary stack useful workload document\n"
IMAGE_DIGEST = "sha256:" + "4" * 64
IMAGE_ID = "sha256:" + "5" * 64
LOGICAL_IMAGE = f"aivm-text-classify@{IMAGE_DIGEST}"
IMMUTABLE_IMAGE = f"localhost/aivm-text-classify@{IMAGE_DIGEST}"

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


def _workload_manifest() -> AIVMWorkloadManifest:
    wire = {
        "schema": "planetary.aivm.workload.v1",
        "manifest_id": "manifest:model:001",
        "account_id": ACCOUNT,
        "workload_id": "workload:model:001",
        "issued_at": "2026-07-17T12:00:00Z",
        "expires_at": "2026-07-17T12:30:00Z",
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
        "filesystem": {"rootfs": "readonly", "writable_paths": [], "host_mounts": []},
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
                "created_at": "2026-07-17T11:59:00Z",
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
                "created_at": "2026-07-17T11:59:00Z",
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


class ApproveManifestVerifier:
    def verify_manifest(self, manifest, payload):
        return DocumentVerification(ok=True, status="verified", key_id=manifest.signer_key_id)


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


def _private_directory(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True)
    path.chmod(0o700)
    return path


@dataclass
class WiringHarness:
    ctx: object
    agent: NodeAgent
    lease: object
    request: object
    bundle: bytes
    result_dir: Path
    authority_dir: Path
    runner: FakeModelRunner


def _admission_controller() -> AIVMAdmissionController:
    policy = AdmissionPolicy(
        allowed_runtime_images=frozenset({LOGICAL_IMAGE}),
        allowed_entrypoints=frozenset({"aivm.model.text-classify.v1"}),
        max_cpu_millicores=4_000,
        max_memory_bytes=4 * 1024 * 1024 * 1024,
        max_time_limit_seconds=900,
        max_process_limit=256,
        max_open_file_limit=4096,
        max_output_bytes=65_536,
        max_scratch_bytes=0,
        max_gpu_count=0,
        max_gpu_memory_bytes=0,
        allowed_devices=frozenset(),
        allowed_network_destinations=frozenset(),
        max_devices=0,
        max_writable_paths=0,
        max_artifacts=8,
        max_inputs=8,
        max_outputs=8,
        max_network_destinations=0,
    )
    probe = StaticHostCapabilityProbe(
        HostIsolationCapabilities(
            os_enforced_backend=True,
            cgroup_control=True,
            namespaces=True,
            no_new_privileges=True,
            container_runtime=True,
            guard_available=True,
        )
    )
    return AIVMAdmissionController(
        verifier=ApproveManifestVerifier(),
        policy=policy,
        host_probe=probe,
    )


def _wiring(
    tmp_path: Path,
    *,
    runner: FakeModelRunner | None = None,
    preadmit: bool = True,
) -> WiringHarness:
    ctx = mesh_context(tmp_path)
    _add_scheduler_key(ctx)
    inventory = inventory_doc(ctx)
    registered = ctx.service().register_inventory(inventory)
    assert registered.status == VSourceStatus.ACCEPTED

    manifest = _workload_manifest()
    bundle = canonical_document_bytes(manifest)
    request = None
    capability = None
    allocation = None
    if preadmit:
        request = request_doc(
            ctx,
            workload_digest=hashlib.sha256(bundle).hexdigest(),
            workload_size=len(bundle),
        )
        capability = capability_doc(ctx)
        allocation = allocate_once(ctx, request=request, capability=capability)
        assert allocation.lease is not None

    state = _private_directory(tmp_path / "executor-state")
    artifacts = _private_directory(tmp_path / "executor-artifacts")
    results = _private_directory(tmp_path / "executor-results")
    authority_dir = _private_directory(tmp_path / "executor-authority")
    for payload in (MODEL_PAYLOAD, DOCUMENT_PAYLOAD):
        artifact = artifacts / hashlib.sha256(payload).hexdigest()
        artifact.write_bytes(payload)
        artifact.chmod(0o600)

    entrypoint = text_classification_entrypoint(
        model_artifact_id=MODEL_ARTIFACT_ID,
        document_artifact_id=DOCUMENT_ARTIFACT_ID,
        output_id=OUTPUT_ID,
    )
    executor_policy = ExecutorPolicy(
        state_dir=state,
        artifact_dir=artifacts,
        result_dir=results,
        trusted_images={LOGICAL_IMAGE: IMMUTABLE_IMAGE},
        trusted_entrypoints={entrypoint.entrypoint_id: entrypoint},
        account_id=ACCOUNT,
        node_id=NODE_ID,
        stdout_limit_bytes=4096,
        stderr_limit_bytes=256,
    )
    runner = runner or FakeModelRunner()
    authority = PersistentExecutionAuthority(
        authority_dir, verifier_id="verifier:node:001"
    )
    executor = PodmanExecutor(
        executor_policy,
        authority_verifier=authority,
        runner=runner,
        clock=lambda: ctx.clock.now(),
    )
    adapter = ChalWorkloadExecutor(
        executor=executor,
        authority=authority,
        admission=_admission_controller(),
        artifact_dir=artifacts,
        clock=lambda: ctx.clock.now(),
    )
    agent = NodeAgent(
        account_id=ACCOUNT,
        node_id=NODE_ID,
        inventory=inventory,
        verifier=Ed25519DocumentVerifier(ctx.resolver, ctx.clock, SCHEDULER),
        signer=ctx.nodes[NODE_ID],
        clock=ctx.clock,
        workload_executor=adapter,
    )
    lease = None
    if preadmit:
        assert allocation is not None and request is not None and capability is not None
        admission = agent.admit_lease(
            allocation.lease,
            request,
            capability,
            authenticated_subject_id=SUBJECT,
        )
        assert admission.accepted
        lease = allocation.lease
    return WiringHarness(
        ctx=ctx,
        agent=agent,
        lease=lease,
        request=request,
        bundle=bundle,
        result_dir=results,
        authority_dir=authority_dir,
        runner=runner,
    )


def _execute(harness: WiringHarness):
    from contracts.chal_vsource.v1.canonical import document_sha256

    return harness.agent.execute(
        lease_id=harness.lease.lease_id,
        lease_sha256=document_sha256(harness.lease),
        fencing_token=harness.lease.fencing_token,
        bundle=harness.bundle,
    )


def test_useful_model_workload_completes_with_verified_result(tmp_path):
    harness = _wiring(tmp_path)

    result = _execute(harness)

    assert result.status == NodeAgentStatus.EXECUTED
    assert result.accepted
    assert result.response is not None
    assert result.response.status == ResponseStatus.SUCCEEDED
    validate_lease_bound_response(result.response, harness.lease)
    for event in result.lifecycle_events:
        validate_lease_bound_lifecycle(event, harness.lease)
    assert [event.state for event in result.lifecycle_events] == [
        LifecycleState.STAGED,
        LifecycleState.RUNNING,
        LifecycleState.COMPLETED,
    ]

    result_sha256 = hashlib.sha256(RESULT_DOCUMENT).hexdigest()
    outputs = result.response.outputs
    assert len(outputs) == 2
    model_output, evidence_output = outputs
    assert model_output.sha256 == result_sha256
    assert model_output.uri == f"artifact://aivm/result/{result_sha256}"
    assert model_output.media_type == "application/json"
    stored = harness.result_dir / result_sha256
    assert stored.read_bytes() == RESULT_DOCUMENT

    assert evidence_output.media_type == AIVM_EVIDENCE_MEDIA_TYPE
    assert result.report is not None
    assert hashlib.sha256(result.report).hexdigest() == evidence_output.sha256
    evidence = json.loads(result.report)
    assert evidence["account_id"] == ACCOUNT
    assert evidence["node_id"] == NODE_ID
    assert evidence["entrypoint_id"] == "aivm.model.text-classify.v1"
    assert evidence["outputs"][0]["sha256"] == result_sha256
    assert evidence["lease_id"] == harness.lease.lease_id
    assert evidence["fencing_token"] == harness.lease.fencing_token
    assert evidence["wall_time_ms"] >= 0

    # The verified result document itself is the useful model output.
    stored_result = json.loads(stored.read_bytes())
    assert stored_result["schema"] == TEXT_CLASSIFICATION_RESULT_SCHEMA
    assert stored_result["label"] == "positive"


def test_replay_after_agent_restart_terminalizes_without_reexecution(tmp_path):
    harness = _wiring(tmp_path)
    first = _execute(harness)
    assert first.status == NodeAgentStatus.EXECUTED
    run_commands = [command for command in harness.runner.commands if command[1] == "run"]
    assert len(run_commands) == 1

    same_agent_replay = _execute(harness)
    assert same_agent_replay.status == NodeAgentStatus.DUPLICATE_TRANSITION

    # A fresh agent (process restart) admits the same lease again, but the
    # durable execution authority refuses a second consumption, so the retry
    # terminalizes as FAILED without ever reaching Podman again.
    restarted = _wiring_same_authority(tmp_path, harness)
    retry = _execute(restarted)
    assert retry.status == NodeAgentStatus.EXECUTION_FAILED
    assert retry.response is not None
    assert retry.response.status == ResponseStatus.FAILED
    assert retry.response.error is not None
    assert retry.reason == "lease_scope_already_consumed"
    retry_runs = [command for command in restarted.runner.commands if command[1] == "run"]
    assert retry_runs == []


def _wiring_same_authority(tmp_path: Path, harness: WiringHarness) -> WiringHarness:
    ctx = harness.ctx
    inventory = inventory_doc(ctx)
    runner = FakeModelRunner()
    entrypoint = text_classification_entrypoint(
        model_artifact_id=MODEL_ARTIFACT_ID,
        document_artifact_id=DOCUMENT_ARTIFACT_ID,
        output_id=OUTPUT_ID,
    )
    state = _private_directory(tmp_path / "executor-state-retry")
    executor_policy = ExecutorPolicy(
        state_dir=state,
        artifact_dir=tmp_path / "executor-artifacts",
        result_dir=harness.result_dir,
        trusted_images={LOGICAL_IMAGE: IMMUTABLE_IMAGE},
        trusted_entrypoints={entrypoint.entrypoint_id: entrypoint},
        account_id=ACCOUNT,
        node_id=NODE_ID,
        stdout_limit_bytes=4096,
        stderr_limit_bytes=256,
    )
    authority = PersistentExecutionAuthority(
        harness.authority_dir, verifier_id="verifier:node:001"
    )
    executor = PodmanExecutor(
        executor_policy,
        authority_verifier=authority,
        runner=runner,
        clock=lambda: ctx.clock.now(),
    )
    adapter = ChalWorkloadExecutor(
        executor=executor,
        authority=authority,
        admission=_admission_controller(),
        artifact_dir=tmp_path / "executor-artifacts",
        clock=lambda: ctx.clock.now(),
    )
    agent = NodeAgent(
        account_id=ACCOUNT,
        node_id=NODE_ID,
        inventory=inventory,
        verifier=Ed25519DocumentVerifier(ctx.resolver, ctx.clock, SCHEDULER),
        signer=ctx.nodes[NODE_ID],
        clock=ctx.clock,
        workload_executor=adapter,
    )
    capability = capability_doc(ctx)
    admission = agent.admit_lease(
        harness.lease,
        harness.request,
        capability,
        authenticated_subject_id=SUBJECT,
    )
    assert admission.accepted
    return WiringHarness(
        ctx=ctx,
        agent=agent,
        lease=harness.lease,
        request=harness.request,
        bundle=harness.bundle,
        result_dir=harness.result_dir,
        authority_dir=harness.authority_dir,
        runner=runner,
    )


def test_invalid_model_output_signs_a_terminal_failure(tmp_path):
    harness = _wiring(
        tmp_path,
        runner=FakeModelRunner(
            run_result=CommandResult((), 0, b"not json\n", b""),
        ),
    )

    result = _execute(harness)

    assert result.status == NodeAgentStatus.EXECUTION_FAILED
    assert not result.accepted
    assert result.reason == "model_result_output_invalid"
    assert result.response is not None
    assert result.response.status == ResponseStatus.FAILED
    assert result.response.error is not None
    validate_lease_bound_response(result.response, harness.lease)
    assert [event.state for event in result.lifecycle_events] == [LifecycleState.FAILED]
    validate_lease_bound_lifecycle(result.lifecycle_events[0], harness.lease)
    assert list(harness.result_dir.iterdir()) == []


def test_tampered_bundle_never_reaches_the_executor(tmp_path):
    harness = _wiring(tmp_path)

    from contracts.chal_vsource.v1.canonical import document_sha256

    tampered = harness.bundle[:-1] + b" "
    result = harness.agent.execute(
        lease_id=harness.lease.lease_id,
        lease_sha256=document_sha256(harness.lease),
        fencing_token=harness.lease.fencing_token,
        bundle=tampered,
    )

    assert result.status == NodeAgentStatus.BUNDLE_MISMATCH
    assert [command for command in harness.runner.commands if command[1] == "run"] == []


def test_cancel_before_execution_is_signed_and_terminal(tmp_path):
    harness = _wiring(tmp_path)

    from contracts.chal_vsource.v1.canonical import document_sha256

    lease_sha256 = document_sha256(harness.lease)
    cancelled = harness.agent.cancel(
        lease_id=harness.lease.lease_id,
        lease_sha256=lease_sha256,
        fencing_token=harness.lease.fencing_token,
    )

    assert cancelled.status == NodeAgentStatus.CANCELLED
    assert cancelled.accepted
    assert [event.state for event in cancelled.lifecycle_events] == [
        LifecycleState.CANCELLED
    ]
    validate_lease_bound_lifecycle(cancelled.lifecycle_events[0], harness.lease)

    after_cancel = _execute(harness)
    assert after_cancel.status == NodeAgentStatus.DUPLICATE_TRANSITION
    assert [command for command in harness.runner.commands if command[1] == "run"] == []
