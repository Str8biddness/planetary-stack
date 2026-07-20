"""F-020 consolidated fail-closed rejection matrix.

One focused test per named F-020 checklist case, each asserting that the
request is rejected BEFORE any workload execution actually happens:

- stale        -> a superseded (older fencing token) lease revision
- duplicated   -> a replay of an already-consumed durable execution authority
- substituted  -> mutated workload/manifest bundle bytes
- expired      -> a manifest outside its validity window
- cross-account-> a request whose account does not match the executing node
- wrong-node   -> a lease whose node does not match the executing node
- oversized    -> an input artifact larger than executor policy allows
- unsupported  -> an untrusted runtime image

Each executor-level case proves "before workload execution" by asserting the
container ``podman run`` command was never issued (the ``FakeModelRunner``
records every command).  The node-agent-level case asserts the same for the
node agent's injected executor.  Authority-level cases assert the durable
verifier fails closed.

The fixtures are reused from the existing suites:
``tests/private_mesh/test_execution_wiring.py`` (node-agent + executor + real
authority wiring) and the ``aivm`` execution package that
``tests/aivm/test_model_profile.py`` and ``tests/aivm/test_execution_authority.py``
exercise directly.
"""

from __future__ import annotations

import hashlib
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

# Make the runtime-packaged ``aivm`` importable exactly like the existing
# execution-wiring test does (the runtime is not installed on sys.path).
_RUNTIME_PACKAGES = (
    Path(__file__).resolve().parents[2]
    / "apps"
    / "synthesus"
    / "runtime"
    / "packages"
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
    PersistentExecutionAuthority,
    PodmanExecutor,
    text_classification_entrypoint,
)

from tests.private_mesh.test_execution_wiring import (  # noqa: E402
    ACCOUNT,
    DOCUMENT_ARTIFACT_ID,
    DOCUMENT_PAYLOAD,
    MODEL_ARTIFACT_ID,
    MODEL_PAYLOAD,
    NODE_ID,
    OUTPUT_ID,
    LOGICAL_IMAGE,
    IMMUTABLE_IMAGE,
    FakeModelRunner,
    NodeAgentStatus,
    _wiring,
    _workload_manifest,
)

# The reused ``_workload_manifest`` is valid from 12:00 to 12:30 on 2026-07-17.
NOW = datetime(2026, 7, 17, 12, 10, tzinfo=UTC)
EXPIRES = datetime(2026, 7, 17, 12, 30, tzinfo=UTC)
AFTER_EXPIRY = datetime(2026, 7, 17, 13, 0, tzinfo=UTC)
WORKLOAD_ID = "workload:model:001"


def _admitted(manifest) -> AdmissionDecision:
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


def _request(
    *,
    fence: int = 11,
    lease_id: str = "lease:model:001",
    lease_sha256: str = "6" * 64,
    account_id: str = ACCOUNT,
    node_id: str = NODE_ID,
) -> AdmittedExecutionRequest:
    manifest = _workload_manifest()
    lease = LeaseAuthority(
        account_id=account_id,
        workload_id=manifest.workload_id,
        node_id=node_id,
        lease_id=lease_id,
        lease_sha256=lease_sha256,
        fencing_token=fence,
    )
    return AdmittedExecutionRequest(manifest, _admitted(manifest), lease)


class _PermissiveAuthority:
    """Verifier that would always VERIFY -- used only for cases whose rejection
    happens before (or independently of) the authority so the assertion proves
    the *executor's own* fail-closed gate, not the authority's."""

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


def _private_directory(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True)
    path.chmod(0o700)
    return path


def _build_executor(
    tmp_path: Path,
    runner: FakeModelRunner,
    *,
    authority_verifier=None,
    policy_account: str = ACCOUNT,
    policy_node: str = NODE_ID,
    trusted_images=None,
    max_input_file_bytes: int = 64 * 1024 * 1024,
    clock=None,
) -> PodmanExecutor:
    state = _private_directory(tmp_path / "state")
    artifacts = _private_directory(tmp_path / "artifacts")
    results = _private_directory(tmp_path / "results")
    for payload in (MODEL_PAYLOAD, DOCUMENT_PAYLOAD):
        artifact = artifacts / hashlib.sha256(payload).hexdigest()
        artifact.write_bytes(payload)
        artifact.chmod(0o600)
    entrypoint = text_classification_entrypoint(
        model_artifact_id=MODEL_ARTIFACT_ID,
        document_artifact_id=DOCUMENT_ARTIFACT_ID,
        output_id=OUTPUT_ID,
    )
    policy = ExecutorPolicy(
        state_dir=state,
        artifact_dir=artifacts,
        result_dir=results,
        trusted_images=trusted_images or {LOGICAL_IMAGE: IMMUTABLE_IMAGE},
        trusted_entrypoints={entrypoint.entrypoint_id: entrypoint},
        account_id=policy_account,
        node_id=policy_node,
        stdout_limit_bytes=4096,
        stderr_limit_bytes=256,
        max_input_file_bytes=max_input_file_bytes,
    )
    return PodmanExecutor(
        policy,
        authority_verifier=authority_verifier or _PermissiveAuthority(),
        runner=runner,
        clock=clock or (lambda: NOW),
    )


def _no_run(runner: FakeModelRunner) -> bool:
    return not any(command[1] == "run" for command in runner.commands)


def _persistent_authority(tmp_path: Path) -> PersistentExecutionAuthority:
    directory = _private_directory(tmp_path / "authority")
    return PersistentExecutionAuthority(directory, verifier_id="verifier:node:001")


def _register(authority: PersistentExecutionAuthority, request, *, expires=EXPIRES, now=NOW):
    authority.register(
        account_id=request.lease.account_id,
        node_id=request.lease.node_id,
        lease_id=request.lease.lease_id,
        lease_sha256=request.lease.lease_sha256,
        fencing_token=request.lease.fencing_token,
        manifest_sha256=request.manifest_sha256,
        workload_id=request.manifest.workload_id,
        expires_at=expires,
        now=now,
    )


# --------------------------------------------------------------------------
# stale: an older fencing token / superseded lease revision must not consume.
# --------------------------------------------------------------------------
def test_stale_superseded_lease_is_rejected(tmp_path):
    authority = _persistent_authority(tmp_path)
    old_revision = _request(fence=11, lease_sha256="6" * 64)
    new_revision = _request(fence=12, lease_sha256="7" * 64)
    _register(authority, old_revision)
    _register(authority, new_revision)  # supersedes fence 11

    stale = authority.verify_and_consume(
        old_revision,
        expected_account_id=ACCOUNT,
        expected_node_id=NODE_ID,
        now=NOW,
    )

    assert stale.status is AuthorityStatus.REJECTED
    # The newest fence still consumes exactly once, proving the store was live.
    current = authority.verify_and_consume(
        new_revision,
        expected_account_id=ACCOUNT,
        expected_node_id=NODE_ID,
        now=NOW,
    )
    assert current.status is AuthorityStatus.VERIFIED


# --------------------------------------------------------------------------
# duplicated: replay of an already-consumed durable authority never re-runs.
# --------------------------------------------------------------------------
def test_duplicated_consumed_authority_is_rejected(tmp_path):
    authority = _persistent_authority(tmp_path)
    request = _request()
    _register(authority, request)
    runner = FakeModelRunner()
    executor = _build_executor(tmp_path / "exec", runner, authority_verifier=authority)

    first = executor.execute(request)
    replay = executor.execute(request)

    assert first.status is ExecutionStatus.SUCCEEDED
    assert replay.status is ExecutionStatus.REJECTED
    assert replay.reason == "execution_authority_rejected"
    # The workload container ran exactly once; the replay never reached podman.
    assert len([c for c in runner.commands if c[1] == "run"]) == 1


# --------------------------------------------------------------------------
# substituted: mutated workload/manifest bundle bytes never reach the executor.
# --------------------------------------------------------------------------
def test_substituted_bundle_is_rejected_before_execution(tmp_path):
    from contracts.chal_vsource.v1.canonical import document_sha256

    harness = _wiring(tmp_path)
    substituted = harness.bundle[:-1] + b" "  # mutate the signed manifest binding

    result = harness.agent.execute(
        lease_id=harness.lease.lease_id,
        lease_sha256=document_sha256(harness.lease),
        fencing_token=harness.lease.fencing_token,
        bundle=substituted,
    )

    assert result.status is NodeAgentStatus.BUNDLE_MISMATCH
    assert not result.accepted
    assert _no_run(harness.runner)


# --------------------------------------------------------------------------
# expired: a manifest outside its validity window is rejected before running.
# --------------------------------------------------------------------------
def test_expired_manifest_is_rejected_before_execution(tmp_path):
    runner = FakeModelRunner()
    executor = _build_executor(tmp_path, runner, clock=lambda: AFTER_EXPIRY)

    result = executor.execute(_request())

    assert result.status is ExecutionStatus.REJECTED
    assert result.reason == "manifest_outside_validity_window"
    assert _no_run(runner)


# --------------------------------------------------------------------------
# cross-account: a request whose account != the executing node's account.
# --------------------------------------------------------------------------
def test_cross_account_request_is_rejected_before_execution(tmp_path):
    runner = FakeModelRunner()
    executor = _build_executor(
        tmp_path, runner, policy_account="account:intruder:001"
    )

    result = executor.execute(_request())

    assert result.status is ExecutionStatus.REJECTED
    assert result.reason == "executor_account_mismatch"
    assert _no_run(runner)


# --------------------------------------------------------------------------
# wrong-node: a lease bound to a different node than the executor.
# --------------------------------------------------------------------------
def test_wrong_node_lease_is_rejected_before_execution(tmp_path):
    runner = FakeModelRunner()
    executor = _build_executor(tmp_path, runner)

    result = executor.execute(_request(node_id="node:intruder:002"))

    assert result.status is ExecutionStatus.REJECTED
    assert result.reason == "executor_node_mismatch"
    assert _no_run(runner)


# --------------------------------------------------------------------------
# oversized: an input artifact larger than executor policy allows.
# --------------------------------------------------------------------------
def test_oversized_input_is_rejected_before_execution(tmp_path):
    runner = FakeModelRunner()
    executor = _build_executor(tmp_path, runner, max_input_file_bytes=1)

    result = executor.execute(_request())

    assert result.status is ExecutionStatus.REJECTED
    assert result.reason == "input_artifact_too_large"
    assert _no_run(runner)


# --------------------------------------------------------------------------
# unsupported: an untrusted runtime image is refused before running.
# --------------------------------------------------------------------------
def test_unsupported_untrusted_image_is_rejected_before_execution(tmp_path):
    other_logical = "aivm-other@sha256:" + "a" * 64
    other_immutable = "localhost/aivm-other@sha256:" + "a" * 64
    runner = FakeModelRunner()
    executor = _build_executor(
        tmp_path, runner, trusted_images={other_logical: other_immutable}
    )

    result = executor.execute(_request())

    assert result.status is ExecutionStatus.REJECTED
    assert result.reason == "runtime_image_not_trusted"
    assert _no_run(runner)
