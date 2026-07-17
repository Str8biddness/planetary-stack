from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from contracts.chal_vsource.v1.models import (
    CapabilityDocument,
    ChalRequest,
    ChalResponse,
    ContentReference,
    CpuDescriptor,
    ErrorFrame,
    GpuDescriptor,
    LeaseDocument,
    LifecycleEvent,
    NodeResources,
    PlacementCandidate,
    PlacementDecision,
    RequestConstraints,
    ResourceInventory,
    ResourceVector,
    SCHEMA_EXPORTS,
    Signature,
    TelemetryEvent,
    validate_document,
)
from contracts.chal_vsource.v1.schema_tool import (
    SCHEMA_ROOT,
    check_schemas,
    validate_path,
)


NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)
HASH_A = "a" * 64
HASH_B = "b" * 64


def signature() -> Signature:
    return Signature(key_id="key:owner:001", value="A" * 86)


def content(name: str = "workload") -> ContentReference:
    return ContentReference(
        uri=f"artifact://private/{name}",
        sha256=HASH_A,
        size_bytes=128,
        media_type="application/vnd.planetary.manifest+json",
    )


def resources() -> ResourceVector:
    return ResourceVector(
        cpu_millicores=2_000,
        memory_bytes=4_294_967_296,
        gpu_count=1,
        gpu_memory_bytes=8_589_934_592,
        storage_bytes=10_000_000_000,
        ingress_bps=100_000_000,
        egress_bps=100_000_000,
    )


def error_frame() -> ErrorFrame:
    return ErrorFrame(
        error_id="error:001",
        request_id="request:001",
        trace_id="trace:001",
        code="node_unavailable",
        retryable=True,
        safe_detail="selected node stopped responding",
        retry_after_ms=1_000,
    )


def request() -> ChalRequest:
    return ChalRequest(
        request_id="request:001",
        trace_id="trace:001",
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
        idempotency_key="idempotency:001",
        account_id="account:owner:001",
        capability_id="capability:001",
        device_uri="chal://aivm/inference",
        workload_kind="inference",
        workload_manifest=content(),
        inputs=[content("input")],
        parameters={"temperature": 0.2, "max_tokens": 128},
        constraints=RequestConstraints(
            resources=resources(),
            latency_budget_ms=30_000,
            deadline=NOW + timedelta(minutes=4),
            grounding_required=True,
            network_access="artifact_plane_only",
        ),
    )


def inventory(**overrides: object) -> ResourceInventory:
    values: dict[str, object] = {
        "inventory_id": "inventory:001",
        "node_id": "node:owner:laptop",
        "account_id": "account:owner:001",
        "public_key_fingerprint": HASH_B,
        "attestation": "software_verified",
        "observed_at": NOW,
        "expires_at": NOW + timedelta(minutes=2),
        "health": "ready",
        "resources": NodeResources(
            capacity=ResourceVector(
                cpu_millicores=4_000,
                memory_bytes=8_589_934_592,
                gpu_count=1,
                gpu_memory_bytes=8_589_934_592,
                storage_bytes=20_000_000_000,
                ingress_bps=1_000_000_000,
                egress_bps=1_000_000_000,
            ),
            allocatable=resources(),
            cpu=CpuDescriptor(
                architecture="x86_64",
                logical_cores=8,
                features={"avx2"},
            ),
            gpus=[
                GpuDescriptor(
                    gpu_id="gpu:001",
                    vendor="NVIDIA",
                    model="RTX",
                    memory_bytes=8_589_934_592,
                    compute_apis={"cuda"},
                )
            ],
        ),
        "transports": {"lan_mtls"},
        "workload_kinds": {"inference", "embedding"},
        "labels": {"thermal_class": "consumer"},
        "signature": signature(),
    }
    values.update(overrides)
    return ResourceInventory(**values)


def test_private_cell_flow_round_trips_every_frozen_document() -> None:
    req = request()
    documents = [
        req,
        error_frame(),
        ChalResponse(
            response_id="response:001",
            request_id=req.request_id,
            trace_id=req.trace_id,
            device_uri=req.device_uri,
            status="succeeded",
            completed_at=NOW + timedelta(seconds=5),
            outputs=[content("output")],
            telemetry_ids=["telemetry:001"],
        ),
        CapabilityDocument(
            capability_id=req.capability_id,
            issuer_id="controller:001",
            subject_id="node-agent:001",
            account_id=req.account_id,
            audience_node_ids={"node:owner:laptop"},
            actions={"inspect", "reserve", "execute", "release"},
            constraints={
                "resources": resources(),
                "workload_kinds": {"inference"},
                "transports": {"lan_mtls"},
                "resource_patterns": ["chal://aivm/"],
            },
            not_before=NOW,
            expires_at=NOW + timedelta(minutes=10),
            nonce="random-capability-nonce-001",
            revocation_epoch=3,
            signature=signature(),
        ),
        inventory(),
        LeaseDocument(
            lease_id="lease:001",
            placement_id="placement:001",
            request_id=req.request_id,
            capability_id=req.capability_id,
            node_id="node:owner:laptop",
            account_id=req.account_id,
            resources=resources(),
            state="active",
            not_before=NOW,
            expires_at=NOW + timedelta(minutes=2),
            fencing_token=7,
            renewable=True,
            max_renewals=2,
            signature=signature(),
        ),
        PlacementDecision(
            placement_id="placement:001",
            request_id=req.request_id,
            trace_id=req.trace_id,
            account_id=req.account_id,
            scheduler_id="scheduler:local:001",
            decided_at=NOW,
            result="placed",
            selected_node_id="node:owner:laptop",
            candidates=[
                PlacementCandidate(
                    node_id="node:owner:laptop",
                    eligible=True,
                    score=0.95,
                    reasons=["capacity", "same_account"],
                )
            ],
            policy_version="private-cell-v1",
        ),
        LifecycleEvent(
            event_id="event:001",
            sequence=0,
            workload_id="workload:001",
            request_id=req.request_id,
            trace_id=req.trace_id,
            placement_id="placement:001",
            lease_id="lease:001",
            node_id="node:owner:laptop",
            account_id=req.account_id,
            state="admitted",
            occurred_at=NOW,
        ),
        TelemetryEvent(
            telemetry_id="telemetry:001",
            request_id=req.request_id,
            trace_id=req.trace_id,
            workload_id="workload:001",
            node_id="node:owner:laptop",
            recorded_at=NOW,
            phase="execution",
            status="ok",
            measurement_kind="measured",
            latency_ms=23.5,
            usage=resources(),
            input_sha256=HASH_A,
            output_sha256=HASH_B,
            labels={"backend": "local-aivm"},
        ),
    ]

    assert len(documents) == len(SCHEMA_EXPORTS) == 9
    for document in documents:
        wire = json.loads(document.model_dump_json(by_alias=True))
        validated = validate_document(wire)
        assert type(validated) is type(document)
        assert validated.model_dump(mode="json", by_alias=True) == wire


def test_committed_json_schemas_match_canonical_models() -> None:
    assert check_schemas() == []
    manifest = json.loads(
        (SCHEMA_ROOT / "schema-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["bundle"] == "planetary.chal-vsource.v1"
    assert set(manifest["schemas"]) == set(SCHEMA_EXPORTS)
    for filename, descriptor in manifest["schemas"].items():
        assert descriptor["sha256"] == hashlib.sha256(
            (SCHEMA_ROOT / filename).read_bytes()
        ).hexdigest()


def test_schema_cli_validator_accepts_wire_document(tmp_path) -> None:
    path = tmp_path / "request.json"
    path.write_text(request().model_dump_json(by_alias=True), encoding="utf-8")
    validate_path(path)


def test_schema_cli_validator_rejects_duplicate_json_keys(tmp_path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text(
        '{"schema":"planetary.chal.request.v1","schema":"other"}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate JSON key"):
        validate_path(path)


@pytest.mark.parametrize("field", ["command", "code", "marshal", "pickle"])
def test_request_rejects_inline_execution_material(field: str) -> None:
    payload = request().model_dump(mode="python", by_alias=True)
    payload["parameters"][field] = "do-something"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ChalRequest.model_validate(payload)


def test_request_rejects_unknown_inline_code_field() -> None:
    payload = request().model_dump(mode="python", by_alias=True)
    payload["inline_code"] = "print('unsafe')"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ChalRequest.model_validate(payload)


def test_inventory_rejects_overcommit_and_public_fabric() -> None:
    overcommitted = inventory().model_dump(mode="python", by_alias=True)
    overcommitted["resources"]["allocatable"]["cpu_millicores"] = 8_000
    with pytest.raises(ValidationError, match="exceeds capacity"):
        ResourceInventory.model_validate(overcommitted)

    with pytest.raises(ValidationError):
        inventory(trust_zone="public_fabric")


def test_capability_and_lease_windows_are_bounded_and_fenced() -> None:
    with pytest.raises(ValidationError, match="expires_at must be after not_before"):
        LeaseDocument(
            lease_id="lease:bad",
            placement_id="placement:001",
            request_id="request:001",
            capability_id="capability:001",
            node_id="node:owner:laptop",
            account_id="account:owner:001",
            resources=resources(),
            state="active",
            not_before=NOW,
            expires_at=NOW,
            fencing_token=1,
            signature=signature(),
        )

    payload = {
        "lease_id": "lease:bad",
        "placement_id": "placement:001",
        "request_id": "request:001",
        "capability_id": "capability:001",
        "node_id": "node:owner:laptop",
        "account_id": "account:owner:001",
        "resources": resources(),
        "state": "active",
        "not_before": NOW,
        "expires_at": NOW + timedelta(minutes=1),
        "fencing_token": 0,
        "signature": signature(),
    }
    with pytest.raises(ValidationError):
        LeaseDocument(**payload)

    capability = {
        "capability_id": "capability:bad",
        "issuer_id": "controller:001",
        "subject_id": "node-agent:001",
        "account_id": "account:owner:001",
        "audience_node_ids": {"node:owner:laptop"},
        "actions": {"execute"},
        "constraints": {
            "resources": resources(),
            "workload_kinds": {"inference"},
            "transports": {"lan_mtls"},
            "resource_patterns": ["chal://aivm/"],
        },
        "not_before": NOW,
        "expires_at": NOW + timedelta(hours=2),
        "nonce": "random-capability-nonce-bad",
        "revocation_epoch": 0,
        "signature": signature(),
    }
    with pytest.raises(ValidationError, match="cannot exceed one hour"):
        CapabilityDocument(**capability)


def test_placement_requires_private_scope_and_eligible_selection() -> None:
    candidate = PlacementCandidate(node_id="node:001", eligible=False, score=0.2)
    with pytest.raises(ValidationError, match="eligible candidate"):
        PlacementDecision(
            placement_id="placement:bad",
            request_id="request:001",
            trace_id="trace:001",
            account_id="account:owner:001",
            scheduler_id="scheduler:001",
            decided_at=NOW,
            result="placed",
            selected_node_id="node:001",
            candidates=[candidate],
            policy_version="private-cell-v1",
        )

    payload = {
        "placement_id": "placement:bad",
        "request_id": "request:001",
        "trace_id": "trace:001",
        "account_id": "account:owner:001",
        "scheduler_id": "scheduler:001",
        "scheduler_scope": "public_marketplace",
        "decided_at": NOW,
        "result": "unplaced",
        "candidates": [candidate],
        "policy_version": "private-cell-v1",
        "rejection_error": error_frame(),
    }
    with pytest.raises(ValidationError):
        PlacementDecision(**payload)


def test_lifecycle_rejects_illegal_jumps_and_missing_evidence() -> None:
    common = {
        "event_id": "event:bad",
        "sequence": 1,
        "workload_id": "workload:001",
        "request_id": "request:001",
        "trace_id": "trace:001",
        "placement_id": "placement:001",
        "lease_id": "lease:001",
        "node_id": "node:owner:laptop",
        "account_id": "account:owner:001",
        "occurred_at": NOW,
    }
    with pytest.raises(ValidationError, match="invalid lifecycle transition"):
        LifecycleEvent(previous_state="admitted", state="completed", **common)

    with pytest.raises(ValidationError, match="requires checkpoint"):
        LifecycleEvent(previous_state="running", state="checkpointed", **common)


def test_response_requires_a_structured_error_when_not_successful() -> None:
    with pytest.raises(ValidationError, match="require an error frame"):
        ChalResponse(
            response_id="response:bad",
            request_id="request:001",
            trace_id="trace:001",
            device_uri="chal://aivm/inference",
            status="degraded",
            completed_at=NOW,
        )


@pytest.mark.parametrize("label", ["prompt", "output", "token", "content"])
def test_telemetry_rejects_raw_or_secret_bearing_labels(label: str) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        TelemetryEvent(
            telemetry_id="telemetry:bad",
            request_id="request:001",
            trace_id="trace:001",
            recorded_at=NOW,
            phase="execution",
            status="ok",
            measurement_kind="measured",
            labels={label: "must-not-cross-the-boundary"},
        )
