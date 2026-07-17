from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from contracts.chal_vsource.v1.canonical import document_sha256
from contracts.chal_vsource.v1.models import (
    CapabilityDocument,
    ChalRequest,
    ChalResponse,
    ContentReference,
    LeaseDocument,
    LifecycleEvent,
    LifecycleState,
    ResourceInventory,
)
from services.vsource import (
    Ed25519DocumentSigner,
    KeyRecord,
    LocalVSourceControlPlane,
    VSourceStatus,
    sign_contract_document,
)


ACCOUNT = "account:owner:001"
SUBJECT = "node-agent:001"
SCHEDULER = "scheduler:local:001"
NOW = datetime(2026, 7, 17, 12, 0, 0, tzinfo=UTC)
HASH_A = "a" * 64
HASH_B = "b" * 64


class FakeClock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value = self.value + timedelta(seconds=seconds)


class MemoryResolver:
    def __init__(self) -> None:
        self.records: dict[str, KeyRecord] = {}

    def resolve_key(self, key_id: str) -> KeyRecord | None:
        return self.records.get(key_id)

    def add(self, record: KeyRecord) -> None:
        self.records[record.key_id] = record


@dataclass
class MeshContext:
    db_path: Path
    clock: FakeClock
    resolver: MemoryResolver
    scheduler: Ed25519DocumentSigner
    controller: Ed25519DocumentSigner
    nodes: dict[str, Ed25519DocumentSigner]

    def service(self) -> LocalVSourceControlPlane:
        return LocalVSourceControlPlane(
            self.db_path,
            key_resolver=self.resolver,
            signer=self.scheduler,
            clock=self.clock,
            scheduler_id=SCHEDULER,
        )


def signer(key_id: str) -> Ed25519DocumentSigner:
    return Ed25519DocumentSigner(key_id, Ed25519PrivateKey.generate())


def public_bytes(document_signer: Ed25519DocumentSigner) -> bytes:
    return document_signer.private_key.public_key().public_bytes(
        encoding=Encoding.Raw,
        format=PublicFormat.Raw,
    )


def fingerprint(document_signer: Ed25519DocumentSigner) -> str:
    return hashlib.sha256(public_bytes(document_signer)).hexdigest()


def mesh_context(tmp_path: Path, *, controller_record: dict[str, Any] | None = None) -> MeshContext:
    resolver = MemoryResolver()
    controller = signer("key:controller:001")
    scheduler = signer("key:scheduler:001")
    controller_kwargs = {
        "key_id": controller.key_id,
        "public_key": public_bytes(controller),
        "account_id": ACCOUNT,
        "audiences": (SCHEDULER,),
    }
    if controller_record:
        controller_kwargs.update(controller_record)
    resolver.add(KeyRecord(**controller_kwargs))
    ctx = MeshContext(
        db_path=tmp_path / "vsource.sqlite3",
        clock=FakeClock(),
        resolver=resolver,
        scheduler=scheduler,
        controller=controller,
        nodes={},
    )
    add_node(ctx, "node:owner:a")
    return ctx


def add_node(ctx: MeshContext, node_id: str) -> Ed25519DocumentSigner:
    node_signer = signer(f"key:{node_id.replace(':', '-')}")
    ctx.nodes[node_id] = node_signer
    ctx.resolver.add(
        KeyRecord(
            key_id=node_signer.key_id,
            public_key=public_bytes(node_signer),
            account_id=ACCOUNT,
            audiences=(SCHEDULER,),
            subject_id=SUBJECT,
            node_id=node_id,
        )
    )
    return node_signer


def wire_time(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def content(name: str = "workload", digest: str = HASH_A) -> dict[str, Any]:
    return {
        "uri": f"artifact://private/{name}",
        "sha256": digest,
        "size_bytes": 128,
        "media_type": "application/vnd.planetary.manifest+json",
        "classification": "private",
    }


def resources(
    *,
    cpu: int = 1_000,
    memory: int = 1_024,
    gpu_count: int = 0,
    gpu_memory: int = 0,
    storage: int = 1_000,
) -> dict[str, int]:
    return {
        "cpu_millicores": cpu,
        "memory_bytes": memory,
        "gpu_count": gpu_count,
        "gpu_memory_bytes": gpu_memory,
        "storage_bytes": storage,
        "ingress_bps": 100,
        "egress_bps": 100,
    }


def parameters() -> dict[str, Any]:
    return {
        "batch_size": None,
        "max_tokens": 128,
        "temperature": 0.2,
        "top_k": None,
        "seed": None,
        "precision": None,
        "checkpoint_interval_seconds": None,
        "replica_count": None,
        "chunk_size": None,
        "width": None,
        "height": None,
        "steps": None,
        "deterministic": False,
    }


def request_doc(
    ctx: MeshContext,
    *,
    request_id: str = "request:001",
    idempotency_key: str = "idempotency:001",
    resource_vector: dict[str, int] | None = None,
    issued_at: datetime | None = None,
    workload_digest: str = HASH_A,
    signed_by: Ed25519DocumentSigner | None = None,
) -> ChalRequest:
    payload = {
        "schema": "planetary.chal.request.v1",
        "request_id": request_id,
        "trace_id": f"trace:{request_id.split(':')[-1]}",
        "parent_request_id": None,
        "issued_at": wire_time(issued_at or ctx.clock.now()),
        "ttl_seconds": 300,
        "idempotency_key": idempotency_key,
        "account_id": ACCOUNT,
        "capability_id": "capability:001",
        "device_uri": "chal://aivm/inference",
        "workload_kind": "inference",
        "workload_manifest": content("workload", workload_digest),
        "inputs": [content("input")],
        "parameters": parameters(),
        "constraints": {
            "resources": resource_vector or resources(),
            "latency_budget_ms": 30_000,
            "grounding_required": True,
            "template_leakage_allowed": False,
            "network_access": "artifact_plane_only",
            "checkpoint_required": False,
        },
    }
    return sign_contract_document(
        ChalRequest,
        payload,
        signed_by or ctx.controller,
    )


def capability_doc(
    ctx: MeshContext,
    *,
    resource_vector: dict[str, int] | None = None,
    nodes: list[str] | None = None,
) -> CapabilityDocument:
    payload = {
        "schema": "planetary.chal.capability.v1",
        "capability_id": "capability:001",
        "issuer_id": "controller:001",
        "subject_id": SUBJECT,
        "account_id": ACCOUNT,
        "audience_node_ids": sorted(nodes or ["node:owner:a"]),
        "actions": ["execute", "reserve"],
        "constraints": {
            "resources": resource_vector or resources(),
            "minimum_attestation": "software_verified",
            "workload_kinds": ["inference"],
            "transports": ["lan_mtls"],
            "resource_prefixes": ["chal://aivm/"],
        },
        "not_before": wire_time(ctx.clock.now()),
        "ttl_seconds": 600,
        "nonce": "random-capability-nonce-001",
        "revocation_epoch": 0,
        "delegable": False,
    }
    return sign_contract_document(CapabilityDocument, payload, ctx.controller)


def inventory_doc(
    ctx: MeshContext,
    *,
    node_id: str = "node:owner:a",
    inventory_id: str = "inventory:a",
    cpu: int = 1_000,
    memory: int = 1_024,
    gpu_memory: int = 0,
    gpus: dict[str, dict[str, Any]] | None = None,
) -> ResourceInventory:
    node_signer = ctx.nodes[node_id]
    payload = {
        "schema": "planetary.vsource.inventory.v1",
        "inventory_id": inventory_id,
        "node_id": node_id,
        "account_id": ACCOUNT,
        "trust_zone": "personal_cell",
        "public_key_fingerprint": fingerprint(node_signer),
        "attestation": "software_verified",
        "observed_at": wire_time(ctx.clock.now()),
        "ttl_seconds": 120,
        "health": "ready",
        "resources": {
            "allocatable": {
                "cpu_millicores": cpu,
                "memory_bytes": memory,
                "storage_bytes": 1_000,
                "ingress_bps": 100,
                "egress_bps": 100,
            },
            "cpu": {
                "architecture": "x86_64",
                "logical_cores": 8,
                "features": ["avx2"],
            },
            "gpus": gpus or {},
        },
        "transports": ["lan_mtls"],
        "workload_kinds": ["inference"],
        "labels": {
            "power_class": "consumer",
            "thermal_policy": "balanced",
            "network_scope": "trusted_lan",
        },
    }
    return sign_contract_document(ResourceInventory, payload, node_signer)


def assert_inventory_admitted(ctx: MeshContext, **kwargs: Any) -> ResourceInventory:
    inventory = inventory_doc(ctx, **kwargs)
    result = ctx.service().register_inventory(inventory)
    assert result.status == VSourceStatus.ACCEPTED
    assert result.accepted
    return inventory


def allocate_once(
    ctx: MeshContext,
    *,
    request: ChalRequest | None = None,
    capability: CapabilityDocument | None = None,
    ttl_seconds: int | None = None,
):
    req = request or request_doc(ctx)
    cap = capability or capability_doc(ctx)
    return ctx.service().allocate(
        req,
        cap,
        authenticated_subject_id=SUBJECT,
        lease_ttl_seconds=ttl_seconds,
    )


def response_doc(
    ctx: MeshContext,
    request: ChalRequest,
    lease: LeaseDocument,
    *,
    response_id: str = "response:001",
) -> ChalResponse:
    payload = {
        "schema": "planetary.chal.response.v1",
        "response_id": response_id,
        "request_id": request.request_id,
        "request_sha256": document_sha256(request),
        "trace_id": request.trace_id,
        "account_id": ACCOUNT,
        "node_id": lease.node_id,
        "device_uri": request.device_uri,
        "lease_id": lease.lease_id,
        "lease_sha256": document_sha256(lease),
        "fencing_token": lease.fencing_token,
        "status": "succeeded",
        "completed_at": wire_time(ctx.clock.now()),
        "outputs": [content("output", HASH_B)],
        "telemetry_ids": [],
        "error": None,
    }
    return sign_contract_document(ChalResponse, payload, ctx.nodes[lease.node_id])


def lifecycle_doc(
    ctx: MeshContext,
    request: ChalRequest,
    lease: LeaseDocument,
    *,
    event_id: str,
    sequence: int,
    previous: LifecycleState | None,
    state: LifecycleState,
) -> LifecycleEvent:
    payload = {
        "schema": "planetary.vsource.lifecycle.v1",
        "event_id": event_id,
        "sequence": sequence,
        "workload_id": "workload:001",
        "request_id": request.request_id,
        "request_sha256": document_sha256(request),
        "trace_id": request.trace_id,
        "placement_id": lease.placement_id,
        "lease_id": lease.lease_id,
        "lease_sha256": document_sha256(lease),
        "fencing_token": lease.fencing_token,
        "node_id": lease.node_id,
        "inventory_id": lease.inventory_id,
        "inventory_sha256": lease.inventory_sha256,
        "account_id": ACCOUNT,
        "previous_state": previous.value if previous else None,
        "state": state.value,
        "occurred_at": wire_time(ctx.clock.now()),
        "checkpoint": None,
        "outputs": [content("output", HASH_B)] if state == LifecycleState.COMPLETED else [],
        "error": None,
    }
    return sign_contract_document(LifecycleEvent, payload, ctx.nodes[lease.node_id])


def test_restart_persists_inventory_idempotency_and_lease(tmp_path: Path) -> None:
    ctx = mesh_context(tmp_path)
    assert_inventory_admitted(ctx)
    request = request_doc(ctx)
    capability = capability_doc(ctx)

    first = allocate_once(ctx, request=request, capability=capability)
    assert first.status == VSourceStatus.ACCEPTED
    assert first.lease is not None

    restarted = ctx.service()
    persisted = restarted.get_lease(first.lease.lease_id)
    assert persisted is not None
    assert persisted.fencing_token == first.lease.fencing_token

    replay = restarted.allocate(request, capability, authenticated_subject_id=SUBJECT)
    assert replay.status == VSourceStatus.IDEMPOTENT_REPLAY
    assert replay.lease is not None
    assert replay.lease.lease_id == first.lease.lease_id

    second = restarted.allocate(
        request_doc(ctx, request_id="request:002", idempotency_key="idempotency:002"),
        capability,
        authenticated_subject_id=SUBJECT,
    )
    assert second.status == VSourceStatus.NO_PLACEMENT
    assert second.lease is None


def test_concurrent_allocation_allows_one_winner(tmp_path: Path) -> None:
    ctx = mesh_context(tmp_path)
    assert_inventory_admitted(ctx)
    capability = capability_doc(ctx)
    requests = [
        request_doc(ctx, request_id="request:101", idempotency_key="idempotency:101"),
        request_doc(ctx, request_id="request:102", idempotency_key="idempotency:102"),
    ]

    def allocate(request: ChalRequest) -> VSourceStatus:
        return ctx.service().allocate(
            request,
            capability,
            authenticated_subject_id=SUBJECT,
        ).status

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(allocate, requests))

    assert statuses.count(VSourceStatus.ACCEPTED) == 1
    assert statuses.count(VSourceStatus.NO_PLACEMENT) == 1


@pytest.mark.parametrize(
    ("request_resources", "inventory_kwargs", "reason"),
    [
        (resources(cpu=2_000), {}, "cpu"),
        (resources(memory=4_096), {}, "memory"),
        (
            resources(gpu_count=1, gpu_memory=1_024),
            {"gpus": {}},
            "gpu",
        ),
    ],
)
def test_insufficient_resources_fail_closed(
    tmp_path: Path,
    request_resources: dict[str, int],
    inventory_kwargs: dict[str, Any],
    reason: str,
) -> None:
    ctx = mesh_context(tmp_path)
    assert_inventory_admitted(ctx, **inventory_kwargs)
    request = request_doc(ctx, resource_vector=request_resources)
    capability = capability_doc(ctx, resource_vector=request_resources)

    result = allocate_once(ctx, request=request, capability=capability)

    assert result.status == VSourceStatus.NO_PLACEMENT
    assert result.lease is None
    assert result.placement is not None
    assert result.placement.candidates[0].eligible is False
    assert reason in result.placement.candidates[0].reasons


def run_two_node_placement(tmp_path: Path, order: list[str]) -> tuple[str, list[str]]:
    ctx = mesh_context(tmp_path)
    add_node(ctx, "node:owner:b")
    for node_id in order:
        assert_inventory_admitted(
            ctx,
            node_id=node_id,
            inventory_id=f"inventory:{node_id[-1]}",
        )
    capability = capability_doc(ctx, nodes=["node:owner:a", "node:owner:b"])
    result = allocate_once(ctx, capability=capability)
    assert result.status == VSourceStatus.ACCEPTED
    assert result.placement is not None
    assert result.placement.selected_candidate is not None
    return (
        result.placement.selected_candidate.node_id,
        [candidate.node_id for candidate in result.placement.candidates],
    )


def test_deterministic_placement_selects_lowest_node_independent_of_registration_order(
    tmp_path: Path,
) -> None:
    first = run_two_node_placement(tmp_path / "first", ["node:owner:b", "node:owner:a"])
    second = run_two_node_placement(tmp_path / "second", ["node:owner:a", "node:owner:b"])
    assert first == second == ("node:owner:a", ["node:owner:a", "node:owner:b"])


def test_idempotency_collision_rejects_different_digest(tmp_path: Path) -> None:
    ctx = mesh_context(tmp_path)
    assert_inventory_admitted(ctx)
    capability = capability_doc(ctx)
    first = request_doc(ctx)
    assert allocate_once(ctx, request=first, capability=capability).status == VSourceStatus.ACCEPTED

    collision = request_doc(
        ctx,
        request_id="request:changed",
        idempotency_key=first.idempotency_key,
        workload_digest=HASH_B,
    )
    result = allocate_once(ctx, request=collision, capability=capability)
    assert result.status == VSourceStatus.IDEMPOTENCY_COLLISION
    assert result.lease is None


def test_renewal_monotonicity_and_stale_digest_rejected(tmp_path: Path) -> None:
    ctx = mesh_context(tmp_path)
    assert_inventory_admitted(ctx)
    result = allocate_once(ctx)
    assert result.lease is not None
    old_lease = result.lease
    old_digest = document_sha256(old_lease)

    renewed = ctx.service().renew_lease(
        old_lease.lease_id,
        lease_sha256=old_digest,
        fencing_token=old_lease.fencing_token,
    )

    assert renewed.status == VSourceStatus.ACCEPTED
    assert renewed.lease is not None
    assert renewed.lease.fencing_token == old_lease.fencing_token + 1
    assert renewed.lease.renewal_sequence == old_lease.renewal_sequence + 1
    assert document_sha256(renewed.lease) != old_digest

    stale = ctx.service().renew_lease(
        old_lease.lease_id,
        lease_sha256=old_digest,
        fencing_token=old_lease.fencing_token,
    )
    assert stale.status == VSourceStatus.STALE_LEASE


def test_expired_lease_fails_closed_without_sleep(tmp_path: Path) -> None:
    ctx = mesh_context(tmp_path)
    assert_inventory_admitted(ctx)
    result = allocate_once(ctx, ttl_seconds=60)
    assert result.lease is not None
    digest = document_sha256(result.lease)

    ctx.clock.advance(61)
    renewed = ctx.service().renew_lease(
        result.lease.lease_id,
        lease_sha256=digest,
        fencing_token=result.lease.fencing_token,
    )
    assert renewed.status == VSourceStatus.LEASE_EXPIRED


def test_terminal_lifecycle_releases_lease_and_blocks_renewal(tmp_path: Path) -> None:
    ctx = mesh_context(tmp_path)
    assert_inventory_admitted(ctx)
    request = request_doc(ctx)
    result = allocate_once(ctx, request=request)
    assert result.lease is not None
    lease = result.lease

    transitions = [
        (0, None, LifecycleState.ADMITTED),
        (1, LifecycleState.ADMITTED, LifecycleState.STAGED),
        (2, LifecycleState.STAGED, LifecycleState.RUNNING),
        (3, LifecycleState.RUNNING, LifecycleState.COMPLETED),
    ]
    for sequence, previous, state in transitions:
        event = lifecycle_doc(
            ctx,
            request,
            lease,
            event_id=f"event:{sequence:03d}",
            sequence=sequence,
            previous=previous,
            state=state,
        )
        accepted = ctx.service().record_lifecycle_event(event)
        assert accepted.status == VSourceStatus.ACCEPTED

    renewed = ctx.service().renew_lease(
        lease.lease_id,
        lease_sha256=document_sha256(lease),
        fencing_token=lease.fencing_token,
    )
    assert renewed.status == VSourceStatus.TERMINAL_LEASE


def test_stale_response_and_lifecycle_binding_after_renewal(tmp_path: Path) -> None:
    ctx = mesh_context(tmp_path)
    assert_inventory_admitted(ctx)
    request = request_doc(ctx)
    result = allocate_once(ctx, request=request)
    assert result.lease is not None
    old_lease = result.lease
    renewed = ctx.service().renew_lease(
        old_lease.lease_id,
        lease_sha256=document_sha256(old_lease),
        fencing_token=old_lease.fencing_token,
    )
    assert renewed.status == VSourceStatus.ACCEPTED

    response = response_doc(ctx, request, old_lease)
    assert ctx.service().record_response(response).status == VSourceStatus.STALE_LEASE

    event = lifecycle_doc(
        ctx,
        request,
        old_lease,
        event_id="event:stale",
        sequence=0,
        previous=None,
        state=LifecycleState.ADMITTED,
    )
    assert ctx.service().record_lifecycle_event(event).status == VSourceStatus.STALE_LEASE


@pytest.mark.parametrize(
    "case",
    ["invalid", "unknown", "revoked", "expired", "wrong_account", "wrong_audience"],
)
def test_signature_admission_failures_reject_before_state_mutation(
    tmp_path: Path,
    case: str,
) -> None:
    controller_record: dict[str, Any] = {}
    if case == "revoked":
        controller_record["revoked"] = True
    if case == "wrong_account":
        controller_record["account_id"] = "account:other:001"
    if case == "wrong_audience":
        controller_record["audiences"] = ("scheduler:other",)
    ctx = mesh_context(tmp_path, controller_record=controller_record)
    capability = capability_doc(ctx)
    signed_by = None
    issued_at = None
    if case == "unknown":
        signed_by = signer("key:unknown:001")
    if case == "expired":
        issued_at = ctx.clock.now() - timedelta(seconds=301)
    request = request_doc(ctx, signed_by=signed_by, issued_at=issued_at)
    if case == "invalid":
        request_wire = request.model_dump(mode="json", by_alias=True)
        request_wire["workload_manifest"]["sha256"] = HASH_B
        request_input: ChalRequest | dict[str, Any] = request_wire
    else:
        request_input = request

    result = ctx.service().allocate(
        request_input,
        capability,
        authenticated_subject_id=SUBJECT,
    )

    expected = {
        "invalid": VSourceStatus.INVALID_SIGNATURE,
        "unknown": VSourceStatus.UNKNOWN_KEY,
        "revoked": VSourceStatus.KEY_REVOKED,
        "expired": VSourceStatus.DOCUMENT_EXPIRED,
        "wrong_account": VSourceStatus.ACCOUNT_MISMATCH,
        "wrong_audience": VSourceStatus.AUDIENCE_MISMATCH,
    }[case]
    assert result.status == expected
    assert result.lease is None


def test_malformed_signature_and_missing_services_fail_closed(tmp_path: Path) -> None:
    ctx = mesh_context(tmp_path)
    request = request_doc(ctx).model_dump(mode="json", by_alias=True)
    request["signature"]["value"] = "A" * 85 + "B"
    capability = capability_doc(ctx)

    malformed = ctx.service().allocate(
        request,
        capability,
        authenticated_subject_id=SUBJECT,
    )
    assert malformed.status == VSourceStatus.MALFORMED_DOCUMENT

    unavailable = LocalVSourceControlPlane(
        tmp_path / "unavailable.sqlite3",
        key_resolver=None,
        signer=None,
        clock=None,
    )
    assert unavailable.register_inventory({}).status == VSourceStatus.UNAVAILABLE

    no_state = LocalVSourceControlPlane(
        None,
        key_resolver=ctx.resolver,
        signer=ctx.scheduler,
        clock=ctx.clock,
    )
    assert no_state.register_inventory(inventory_doc(ctx)).status == VSourceStatus.UNAVAILABLE
