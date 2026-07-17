from __future__ import annotations

import hashlib
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable

import pytest

from contracts.chal_vsource.v1.canonical import document_sha256
from contracts.chal_vsource.v1.models import (
    CapabilityDocument,
    ChalRequest,
    LeaseDocument,
    LifecycleState,
    ResourceInventory,
    validate_lease_bound_lifecycle,
    validate_lease_bound_response,
)
from services.private_mesh import (
    Ed25519DocumentVerifier,
    NodeAdmissionResult,
    NodeAgent,
    NodeAgentStatus,
    VerificationResult,
)
from services.vsource import KeyRecord, VSourceStatus, sign_contract_document
from tests.vsource.test_local_control_plane import (
    ACCOUNT,
    SCHEDULER,
    SUBJECT,
    MeshContext,
    allocate_once,
    capability_doc,
    inventory_doc,
    mesh_context,
    public_bytes,
    request_doc,
    signer,
)


NODE_ID = "node:owner:a"
BUNDLE = b"x" * 128


@dataclass
class Harness:
    ctx: MeshContext
    inventory: ResourceInventory
    request: ChalRequest
    capability: CapabilityDocument
    lease: LeaseDocument
    agent: NodeAgent
    admission: NodeAdmissionResult


def _add_scheduler_key(ctx: MeshContext) -> None:
    ctx.resolver.add(
        KeyRecord(
            key_id=ctx.scheduler.key_id,
            public_key=public_bytes(ctx.scheduler),
            account_id=ACCOUNT,
            audiences=(SCHEDULER,),
        )
    )


def _new_agent(
    ctx: MeshContext,
    inventory: ResourceInventory | None,
    *,
    verifier: object = ...,
    signer: object = ...,
    clock: object = ...,
) -> NodeAgent:
    actual_verifier = (
        Ed25519DocumentVerifier(ctx.resolver, ctx.clock, SCHEDULER)
        if verifier is ...
        else verifier
    )
    return NodeAgent(
        account_id=ACCOUNT,
        node_id=NODE_ID,
        inventory=inventory,
        verifier=actual_verifier,  # type: ignore[arg-type]
        signer=ctx.nodes[NODE_ID] if signer is ... else signer,  # type: ignore[arg-type]
        clock=ctx.clock if clock is ... else clock,  # type: ignore[arg-type]
    )


@pytest.fixture
def harness(tmp_path) -> Harness:
    ctx = mesh_context(tmp_path)
    _add_scheduler_key(ctx)
    inventory = inventory_doc(ctx)
    registered = ctx.service().register_inventory(inventory)
    assert registered.status == VSourceStatus.ACCEPTED
    request = request_doc(
        ctx,
        workload_digest=hashlib.sha256(BUNDLE).hexdigest(),
    )
    capability = capability_doc(ctx)
    allocation = allocate_once(ctx, request=request, capability=capability)
    assert allocation.lease is not None
    agent = _new_agent(ctx, inventory)
    admission = agent.admit_lease(
        allocation.lease,
        request,
        capability,
        authenticated_subject_id=SUBJECT,
    )
    assert admission.accepted
    return Harness(
        ctx,
        inventory,
        request,
        capability,
        allocation.lease,
        agent,
        admission,
    )


def _resign(
    document,
    document_signer,
    mutate: Callable[[dict[str, Any]], None],
):
    payload = document.model_dump(mode="json", by_alias=True)
    payload.pop("signature")
    mutate(payload)
    return sign_contract_document(type(document), payload, document_signer)


def _admit(
    agent: NodeAgent,
    lease: LeaseDocument,
    request: ChalRequest,
    capability: CapabilityDocument,
    *,
    subject: str = SUBJECT,
):
    return agent.admit_lease(
        lease,
        request,
        capability,
        authenticated_subject_id=subject,
    )


def test_valid_admission_and_hash_only_execution_are_fully_bound(harness: Harness) -> None:
    admission = harness.admission
    assert admission.status == NodeAgentStatus.ADMITTED
    assert admission.lifecycle_event is not None
    validate_lease_bound_lifecycle(admission.lifecycle_event, harness.lease)

    result = harness.agent.execute(
        lease_id=harness.lease.lease_id,
        lease_sha256=document_sha256(harness.lease),
        fencing_token=harness.lease.fencing_token,
        bundle=BUNDLE,
    )

    assert result.status == NodeAgentStatus.EXECUTED
    assert result.accepted
    assert result.response is not None
    assert result.report is not None
    validate_lease_bound_response(result.response, harness.lease)
    assert [event.state for event in result.lifecycle_events] == [
        LifecycleState.STAGED,
        LifecycleState.RUNNING,
        LifecycleState.COMPLETED,
    ]
    for event in result.lifecycle_events:
        validate_lease_bound_lifecycle(event, harness.lease)
    report = json.loads(result.report)
    assert report["algorithm"] == "sha256"
    assert report["bundle_sha256"] == hashlib.sha256(BUNDLE).hexdigest()
    assert report["bundle_size_bytes"] == len(BUNDLE)
    assert report["request_sha256"] == document_sha256(harness.request)
    assert report["lease_sha256"] == document_sha256(harness.lease)


@pytest.mark.parametrize("missing", ["inventory", "verifier", "signer", "clock"])
def test_missing_required_services_fail_explicitly(tmp_path, missing: str) -> None:
    ctx = mesh_context(tmp_path)
    _add_scheduler_key(ctx)
    inventory = inventory_doc(ctx)
    request = request_doc(ctx, workload_digest=hashlib.sha256(BUNDLE).hexdigest())
    capability = capability_doc(ctx)
    ctx.service().register_inventory(inventory)
    allocation = allocate_once(ctx, request=request, capability=capability)
    assert allocation.lease is not None
    kwargs: dict[str, object] = {}
    if missing == "verifier":
        kwargs["verifier"] = None
    elif missing == "signer":
        kwargs["signer"] = None
    elif missing == "clock":
        kwargs["clock"] = None
    agent = _new_agent(ctx, None if missing == "inventory" else inventory, **kwargs)

    result = _admit(agent, allocation.lease, request, capability)

    assert result.status == NodeAgentStatus.UNAVAILABLE
    assert not result.accepted
    assert agent.admitted_lease_ids() == ()


def test_signer_must_match_inventory_key(tmp_path) -> None:
    ctx = mesh_context(tmp_path)
    _add_scheduler_key(ctx)
    inventory = inventory_doc(ctx)
    request = request_doc(ctx, workload_digest=hashlib.sha256(BUNDLE).hexdigest())
    capability = capability_doc(ctx)
    ctx.service().register_inventory(inventory)
    allocation = allocate_once(ctx, request=request, capability=capability)
    assert allocation.lease is not None
    agent = _new_agent(ctx, inventory, signer=ctx.controller)

    result = _admit(agent, allocation.lease, request, capability)

    assert result.status == NodeAgentStatus.UNAVAILABLE
    assert "signer key" in (result.reason or "")


def test_signer_with_right_key_id_but_wrong_private_key_fails_self_verification(
    harness: Harness,
) -> None:
    impostor = signer(harness.inventory.signature.key_id)
    result = _admit(
        _new_agent(harness.ctx, harness.inventory, signer=impostor),
        harness.lease,
        harness.request,
        harness.capability,
    )

    assert result.status == NodeAgentStatus.UNAVAILABLE
    assert not result.accepted


@pytest.mark.parametrize(
    ("field", "value", "status"),
    [
        ("account_id", "account:other:001", NodeAgentStatus.ACCOUNT_MISMATCH),
        ("node_id", "node:owner:b", NodeAgentStatus.NODE_MISMATCH),
        ("request_id", "request:other", NodeAgentStatus.DIGEST_MISMATCH),
        ("request_sha256", "f" * 64, NodeAgentStatus.DIGEST_MISMATCH),
        ("capability_id", "capability:other", NodeAgentStatus.CAPABILITY_MISMATCH),
        ("inventory_id", "inventory:other", NodeAgentStatus.DIGEST_MISMATCH),
        ("inventory_sha256", "e" * 64, NodeAgentStatus.DIGEST_MISMATCH),
        ("transport", "local_process", NodeAgentStatus.TRANSPORT_UNSUPPORTED),
    ],
)
def test_every_lease_join_mismatch_fails_closed(
    harness: Harness,
    field: str,
    value: object,
    status: NodeAgentStatus,
) -> None:
    fresh = _new_agent(harness.ctx, harness.inventory)
    lease = _resign(
        harness.lease,
        harness.ctx.scheduler,
        lambda payload: payload.__setitem__(field, value),
    )

    result = _admit(fresh, lease, harness.request, harness.capability)

    assert result.status == status
    assert not result.accepted
    assert fresh.admitted_lease_ids() == ()


def test_subject_and_capability_joins_fail_closed(harness: Harness) -> None:
    wrong_subject = _admit(
        _new_agent(harness.ctx, harness.inventory),
        harness.lease,
        harness.request,
        harness.capability,
        subject="node-agent:attacker",
    )
    changed_capability = _resign(
        harness.capability,
        harness.ctx.controller,
        lambda payload: payload.__setitem__("subject_id", "node-agent:other"),
    )
    wrong_capability = _admit(
        _new_agent(harness.ctx, harness.inventory),
        harness.lease,
        harness.request,
        changed_capability,
    )

    assert wrong_subject.status == NodeAgentStatus.SUBJECT_MISMATCH
    assert wrong_capability.status == NodeAgentStatus.SUBJECT_MISMATCH


def test_non_ready_signed_inventory_cannot_execute_new_work(harness: Harness) -> None:
    degraded_inventory = _resign(
        harness.inventory,
        harness.ctx.nodes[NODE_ID],
        lambda payload: payload.__setitem__("health", "degraded"),
    )
    rebound_lease = _resign(
        harness.lease,
        harness.ctx.scheduler,
        lambda payload: payload.__setitem__(
            "inventory_sha256", document_sha256(degraded_inventory)
        ),
    )

    result = _admit(
        _new_agent(harness.ctx, degraded_inventory),
        rebound_lease,
        harness.request,
        harness.capability,
    )

    assert result.status == NodeAgentStatus.WORKLOAD_REJECTED
    assert not result.accepted


def test_signature_tampering_unknown_keys_and_resolver_failure_fail_closed(
    harness: Harness,
) -> None:
    tampered_request = harness.request.model_copy(
        update={"trace_id": "trace:tampered"}
    )
    invalid = _admit(
        _new_agent(harness.ctx, harness.inventory),
        harness.lease,
        tampered_request,
        harness.capability,
    )

    class BrokenResolver:
        def resolve_key(self, key_id: str):
            raise RuntimeError("key backend unavailable")

    unavailable_verifier = Ed25519DocumentVerifier(
        BrokenResolver(), harness.ctx.clock, SCHEDULER
    )
    unavailable = _admit(
        _new_agent(
            harness.ctx,
            harness.inventory,
            verifier=unavailable_verifier,
        ),
        harness.lease,
        harness.request,
        harness.capability,
    )

    assert invalid.status == NodeAgentStatus.INVALID_SIGNATURE
    assert unavailable.status == NodeAgentStatus.UNAVAILABLE


@pytest.mark.parametrize("mode", ["raises", "omits_digest", "wrong_type"])
def test_injected_verifier_failures_never_escape(harness: Harness, mode: str) -> None:
    class BrokenVerifier:
        def verify_document(self, document, **kwargs):
            if mode == "raises":
                raise RuntimeError("verifier backend failed")
            if mode == "omits_digest":
                return VerificationResult(None)
            return object()

    result = _admit(
        _new_agent(harness.ctx, harness.inventory, verifier=BrokenVerifier()),
        harness.lease,
        harness.request,
        harness.capability,
    )

    assert result.status == NodeAgentStatus.UNAVAILABLE
    assert not result.accepted


def test_verifier_cannot_substitute_a_different_document_digest(harness: Harness) -> None:
    real = Ed25519DocumentVerifier(harness.ctx.resolver, harness.ctx.clock, SCHEDULER)

    class DigestSubstitutingVerifier:
        def verify_document(self, document, **kwargs):
            result = real.verify_document(document, **kwargs)
            if result.verified:
                return VerificationResult(None, "f" * 64, result.key)
            return result

    result = _admit(
        _new_agent(
            harness.ctx,
            harness.inventory,
            verifier=DigestSubstitutingVerifier(),
        ),
        harness.lease,
        harness.request,
        harness.capability,
    )

    assert result.status == NodeAgentStatus.DIGEST_MISMATCH
    assert not result.accepted


def test_duplicate_and_non_i_json_documents_are_rejected_before_verification(
    harness: Harness,
) -> None:
    raw = harness.lease.model_dump_json(by_alias=True)
    duplicate = raw[:-1] + f',"lease_id":"{harness.lease.lease_id}"' + "}"
    duplicate_result = harness.agent.admit_lease(
        duplicate,
        harness.request,
        harness.capability,
        authenticated_subject_id=SUBJECT,
    )
    non_i_json = harness.agent.admit_lease(
        '{"schema":"planetary.vsource.lease.v1","ttl_seconds":NaN}',
        harness.request,
        harness.capability,
        authenticated_subject_id=SUBJECT,
    )

    assert duplicate_result.status == NodeAgentStatus.MALFORMED_DOCUMENT
    assert non_i_json.status == NodeAgentStatus.MALFORMED_DOCUMENT


def test_replay_renewal_and_stale_fence_are_rejected(harness: Harness) -> None:
    exact_replay = _admit(
        harness.agent,
        harness.lease,
        harness.request,
        harness.capability,
    )
    renewed = harness.ctx.service().renew_lease(
        harness.lease.lease_id,
        lease_sha256=document_sha256(harness.lease),
        fencing_token=harness.lease.fencing_token,
        renewal_sequence=harness.lease.renewal_sequence,
    )
    assert renewed.lease is not None
    renewal_admission = _admit(
        harness.agent,
        renewed.lease,
        harness.request,
        harness.capability,
    )
    stale_execution = harness.agent.execute(
        lease_id=harness.lease.lease_id,
        lease_sha256=document_sha256(harness.lease),
        fencing_token=harness.lease.fencing_token,
        bundle=BUNDLE,
    )
    stale_readmission = _admit(
        harness.agent,
        harness.lease,
        harness.request,
        harness.capability,
    )

    assert exact_replay.status == NodeAgentStatus.REPLAY
    assert renewal_admission.status == NodeAgentStatus.RENEWED
    assert stale_execution.status == NodeAgentStatus.STALE_LEASE
    assert stale_readmission.status == NodeAgentStatus.STALE_LEASE


def test_expired_and_revoked_leases_fail_closed(harness: Harness) -> None:
    harness.ctx.clock.advance(harness.lease.ttl_seconds)
    expired = harness.agent.execute(
        lease_id=harness.lease.lease_id,
        lease_sha256=document_sha256(harness.lease),
        fencing_token=harness.lease.fencing_token,
        bundle=BUNDLE,
    )
    harness.ctx.clock.value = harness.lease.not_before
    revoked_lease = _resign(
        harness.lease,
        harness.ctx.scheduler,
        lambda payload: payload.update(
            state="revoked", revocation_reason="owner_request"
        ),
    )
    revoked = _admit(
        _new_agent(harness.ctx, harness.inventory),
        revoked_lease,
        harness.request,
        harness.capability,
    )

    assert expired.status == NodeAgentStatus.LEASE_EXPIRED
    assert revoked.status == NodeAgentStatus.LEASE_REVOKED


def test_bundle_mismatch_has_zero_state_change_and_allows_exact_retry(
    harness: Harness,
) -> None:
    wrong = harness.agent.execute(
        lease_id=harness.lease.lease_id,
        lease_sha256=document_sha256(harness.lease),
        fencing_token=harness.lease.fencing_token,
        bundle=BUNDLE + b"changed",
    )

    assert wrong.status == NodeAgentStatus.BUNDLE_MISMATCH
    assert not wrong.accepted
    assert wrong.lifecycle_events == ()
    assert wrong.response is None
    assert harness.agent.workload_state(harness.lease.lease_id) == LifecycleState.ADMITTED

    retry = harness.agent.execute(
        lease_id=harness.lease.lease_id,
        lease_sha256=document_sha256(harness.lease),
        fencing_token=harness.lease.fencing_token,
        bundle=BUNDLE,
    )
    assert retry.status == NodeAgentStatus.EXECUTED


def test_duplicate_and_concurrent_execution_have_one_winner(harness: Harness) -> None:
    def execute():
        return harness.agent.execute(
            lease_id=harness.lease.lease_id,
            lease_sha256=document_sha256(harness.lease),
            fencing_token=harness.lease.fencing_token,
            bundle=BUNDLE,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: execute(), range(2)))

    assert sum(result.accepted for result in results) == 1
    assert {result.status for result in results} == {
        NodeAgentStatus.EXECUTED,
        NodeAgentStatus.DUPLICATE_TRANSITION,
    }
    third = execute()
    assert third.status == NodeAgentStatus.DUPLICATE_TRANSITION


@pytest.mark.parametrize(
    ("lease_id", "lease_sha256", "fencing_token"),
    [
        ("../lease", "a" * 64, 1),
        ("lease:valid:001", "A" * 64, 1),
        ("lease:valid:001", "a" * 64, True),
        ("lease:valid:001", "a" * 64, 1.0),
    ],
)
def test_execution_context_types_are_strict(
    harness: Harness,
    lease_id: object,
    lease_sha256: object,
    fencing_token: object,
) -> None:
    result = harness.agent.execute(
        lease_id=lease_id,  # type: ignore[arg-type]
        lease_sha256=lease_sha256,  # type: ignore[arg-type]
        fencing_token=fencing_token,  # type: ignore[arg-type]
        bundle=BUNDLE,
    )

    assert result.status == NodeAgentStatus.REJECTED
    assert not result.accepted
    assert harness.agent.workload_state(harness.lease.lease_id) == LifecycleState.ADMITTED


def test_opaque_shell_like_bytes_are_hashed_without_process_execution(
    tmp_path,
    monkeypatch,
) -> None:
    bundle = b"#!/bin/sh\ntouch /tmp/should-never-exist\n".ljust(128, b"\0")
    ctx = mesh_context(tmp_path)
    _add_scheduler_key(ctx)
    inventory = inventory_doc(ctx)
    ctx.service().register_inventory(inventory)
    request = request_doc(ctx, workload_digest=hashlib.sha256(bundle).hexdigest())
    capability = capability_doc(ctx)
    allocation = allocate_once(ctx, request=request, capability=capability)
    assert allocation.lease is not None
    agent = _new_agent(ctx, inventory)
    admitted = _admit(agent, allocation.lease, request, capability)
    assert admitted.accepted

    def forbidden(*args, **kwargs):
        raise AssertionError("process execution is forbidden")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    result = agent.execute(
        lease_id=allocation.lease.lease_id,
        lease_sha256=document_sha256(allocation.lease),
        fencing_token=allocation.lease.fencing_token,
        bundle=bundle,
    )

    assert result.status == NodeAgentStatus.EXECUTED
    assert result.report is not None
    assert json.loads(result.report)["bundle_sha256"] == hashlib.sha256(bundle).hexdigest()
