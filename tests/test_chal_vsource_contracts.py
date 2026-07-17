from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, TypeVar

import pytest
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ValidationError

from contracts.chal_vsource.v1 import schema_tool
from contracts.chal_vsource.v1.canonical import document_sha256, signing_bytes
from contracts.chal_vsource.v1.models import (
    CapabilityDocument,
    ChalRequest,
    ChalResponse,
    ErrorFrame,
    LeaseDocument,
    LifecycleEvent,
    MAX_SAFE_INTEGER,
    PlacementDecision,
    ResourceInventory,
    ResourceVector,
    SCHEMA_EXPORTS,
    Signature,
    TelemetryEvent,
    device_uri_matches_prefix,
    validate_document,
    validate_lease_bound_lifecycle,
    validate_lease_bound_response,
    validate_private_cell_allocation,
)
from contracts.chal_vsource.v1.schema_tool import (
    SCHEMA_ROOT,
    check_schemas,
    validate_path,
    validate_schema_document,
)


ModelT = TypeVar("ModelT", bound=BaseModel)
NOW_WIRE = "2026-07-16T12:00:00Z"
HASH_A = "a" * 64
HASH_B = "b" * 64
SIGNATURE_VALUE = "A" * 86
ALTERNATE_SIGNATURE_VALUE = (
    base64.urlsafe_b64encode(b"B" * 64).rstrip(b"=").decode("ascii")
)


def from_wire(model: type[ModelT], payload: dict[str, Any]) -> ModelT:
    return model.model_validate_json(
        json.dumps(payload, allow_nan=False, separators=(",", ":"))
    )


def signature_wire() -> dict[str, Any]:
    return {
        "algorithm": "ed25519",
        "key_id": "key:owner:001",
        "value": SIGNATURE_VALUE,
    }


def content_wire(name: str = "workload", digest: str = HASH_A) -> dict[str, Any]:
    return {
        "uri": f"artifact://private/{name}",
        "sha256": digest,
        "size_bytes": 128,
        "media_type": "application/vnd.planetary.manifest+json",
        "classification": "private",
    }


def resources_wire() -> dict[str, int]:
    return {
        "cpu_millicores": 2_000,
        "memory_bytes": 4_294_967_296,
        "gpu_count": 1,
        "gpu_memory_bytes": 8_589_934_592,
        "storage_bytes": 10_000_000_000,
        "ingress_bps": 100_000_000,
        "egress_bps": 100_000_000,
    }


def request_wire() -> dict[str, Any]:
    return {
        "schema": "planetary.chal.request.v1",
        "request_id": "request:001",
        "trace_id": "trace:001",
        "parent_request_id": None,
        "issued_at": NOW_WIRE,
        "ttl_seconds": 300,
        "idempotency_key": "idempotency:001",
        "account_id": "account:owner:001",
        "capability_id": "capability:001",
        "device_uri": "chal://aivm/inference",
        "workload_kind": "inference",
        "workload_manifest": content_wire(),
        "inputs": [content_wire("input")],
        "parameters": {
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
        },
        "constraints": {
            "resources": resources_wire(),
            "latency_budget_ms": 30_000,
            "grounding_required": True,
            "template_leakage_allowed": False,
            "network_access": "artifact_plane_only",
            "checkpoint_required": False,
        },
        "signature": signature_wire(),
    }


def request() -> ChalRequest:
    return from_wire(ChalRequest, request_wire())


def error_wire(request_sha256: str) -> dict[str, Any]:
    return {
        "schema": "planetary.chal.error.v1",
        "error_id": "error:001",
        "request_id": "request:001",
        "request_sha256": request_sha256,
        "trace_id": "trace:001",
        "code": "node_unavailable",
        "retryable": True,
        "diagnostic_id": "diagnostic:node-unavailable:001",
        "retry_after_ms": 1_000,
        "device_uri": "chal://aivm/inference",
        "signature": signature_wire(),
    }


def inventory_wire(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": "planetary.vsource.inventory.v1",
        "inventory_id": "inventory:001",
        "node_id": "node:owner:laptop",
        "account_id": "account:owner:001",
        "trust_zone": "personal_cell",
        "public_key_fingerprint": HASH_B,
        "attestation": "software_verified",
        "observed_at": NOW_WIRE,
        "ttl_seconds": 120,
        "health": "ready",
        "resources": {
            "allocatable": {
                "cpu_millicores": 2_000,
                "memory_bytes": 4_294_967_296,
                "storage_bytes": 10_000_000_000,
                "ingress_bps": 100_000_000,
                "egress_bps": 100_000_000,
            },
            "cpu": {
                "architecture": "x86_64",
                "logical_cores": 8,
                "features": ["avx2"],
            },
            "gpus": {
                "gpu:001": {
                    "vendor": "NVIDIA",
                    "model": "RTX",
                    "allocatable_memory_bytes": 8_589_934_592,
                    "compute_apis": ["cuda"],
                }
            },
        },
        "transports": ["lan_mtls"],
        "workload_kinds": ["embedding", "inference"],
        "labels": {
            "power_class": "consumer",
            "thermal_policy": "balanced",
            "network_scope": "trusted_lan",
        },
        "signature": signature_wire(),
    }
    payload.update(overrides)
    return payload


def candidate_wire(
    *,
    eligible: bool = True,
    inventory_sha256: str = HASH_B,
) -> dict[str, Any]:
    return {
        "node_id": "node:owner:laptop",
        "account_id": "account:owner:001",
        "inventory_id": "inventory:001",
        "inventory_sha256": inventory_sha256,
        "eligible": eligible,
        "score": 0.95,
        "reasons": ["capacity", "same_account"],
    }


def full_flow_documents() -> list[BaseModel]:
    req = request()
    request_sha = document_sha256(req)
    error = from_wire(ErrorFrame, error_wire(request_sha))
    capability = from_wire(
        CapabilityDocument,
        {
            "schema": "planetary.chal.capability.v1",
            "capability_id": req.capability_id,
            "issuer_id": "controller:001",
            "subject_id": "node-agent:001",
            "account_id": req.account_id,
            "audience_node_ids": ["node:owner:laptop"],
            "actions": ["execute", "inspect", "release", "reserve"],
            "constraints": {
                "resources": resources_wire(),
                "minimum_attestation": "software_verified",
                "workload_kinds": ["inference"],
                "transports": ["lan_mtls"],
                "resource_prefixes": ["chal://aivm/"],
            },
            "not_before": NOW_WIRE,
            "ttl_seconds": 600,
            "nonce": "random-capability-nonce-001",
            "revocation_epoch": 3,
            "delegable": False,
            "signature": signature_wire(),
        },
    )
    inventory = from_wire(ResourceInventory, inventory_wire())
    inventory_sha = document_sha256(inventory)
    lease = from_wire(
        LeaseDocument,
        {
            "schema": "planetary.vsource.lease.v1",
            "lease_id": "lease:001",
            "placement_id": "placement:001",
            "request_id": req.request_id,
            "request_sha256": request_sha,
            "capability_id": req.capability_id,
            "node_id": "node:owner:laptop",
            "inventory_id": "inventory:001",
            "inventory_sha256": inventory_sha,
            "account_id": req.account_id,
            "transport": "lan_mtls",
            "resources": resources_wire(),
            "gpu_ids": ["gpu:001"],
            "state": "active",
            "not_before": NOW_WIRE,
            "ttl_seconds": 120,
            "fencing_token": 7,
            "renewal_sequence": 0,
            "renewals_remaining": 2,
            "revocation_reason": None,
            "signature": signature_wire(),
        },
    )
    candidate = candidate_wire(inventory_sha256=inventory_sha)
    placement = from_wire(
        PlacementDecision,
        {
            "schema": "planetary.vsource.placement.v1",
            "placement_id": "placement:001",
            "request_id": req.request_id,
            "request_sha256": request_sha,
            "trace_id": req.trace_id,
            "account_id": req.account_id,
            "scheduler_id": "scheduler:local:001",
            "scheduler_scope": "same_account_private_cell",
            "transport": "lan_mtls",
            "decided_at": NOW_WIRE,
            "result": "placed",
            "selected_candidate": candidate,
            "candidates": [candidate],
            "policy_version": "private-cell-v1",
            "rejection_error": None,
            "signature": signature_wire(),
        },
    )
    lifecycle = from_wire(
        LifecycleEvent,
        {
            "schema": "planetary.vsource.lifecycle.v1",
            "event_id": "event:001",
            "sequence": 0,
            "workload_id": "workload:001",
            "request_id": req.request_id,
            "request_sha256": request_sha,
            "trace_id": req.trace_id,
            "placement_id": "placement:001",
            "lease_id": "lease:001",
            "lease_sha256": document_sha256(lease),
            "fencing_token": lease.fencing_token,
            "node_id": "node:owner:laptop",
            "inventory_id": "inventory:001",
            "inventory_sha256": inventory_sha,
            "account_id": req.account_id,
            "previous_state": None,
            "state": "admitted",
            "occurred_at": NOW_WIRE,
            "checkpoint": None,
            "outputs": [],
            "error": None,
            "signature": signature_wire(),
        },
    )
    telemetry = from_wire(
        TelemetryEvent,
        {
            "schema": "planetary.chal.telemetry.v1",
            "telemetry_id": "telemetry:001",
            "request_id": req.request_id,
            "request_sha256": request_sha,
            "trace_id": req.trace_id,
            "workload_id": "workload:001",
            "node_id": "node:owner:laptop",
            "recorded_at": NOW_WIRE,
            "phase": "execution",
            "status": "ok",
            "measurement_kind": "measured",
            "latency_ms": 23.5,
            "queue_ms": 1.0,
            "usage": resources_wire(),
            "input_sha256": HASH_A,
            "output_sha256": HASH_B,
            "contains_user_content": False,
            "labels": {
                "backend": "aivm_container",
                "route": "grounded_path",
                "accelerator": "cuda",
                "degradation_code": None,
                "verification": "verified",
            },
            "error_id": None,
            "signature": signature_wire(),
        },
    )
    response = from_wire(
        ChalResponse,
        {
            "schema": "planetary.chal.response.v1",
            "response_id": "response:001",
            "request_id": req.request_id,
            "request_sha256": request_sha,
            "trace_id": req.trace_id,
            "account_id": req.account_id,
            "node_id": lease.node_id,
            "device_uri": req.device_uri,
            "lease_id": lease.lease_id,
            "lease_sha256": document_sha256(lease),
            "fencing_token": lease.fencing_token,
            "status": "succeeded",
            "completed_at": "2026-07-16T12:00:05Z",
            "outputs": [content_wire("output", HASH_B)],
            "telemetry_ids": ["telemetry:001"],
            "error": None,
            "signature": signature_wire(),
        },
    )
    return [
        req,
        error,
        response,
        capability,
        inventory,
        lease,
        placement,
        lifecycle,
        telemetry,
    ]


def assert_wire_rejected(payload: dict[str, Any], match: str | None = None) -> None:
    with pytest.raises(ValueError):
        validate_schema_document(payload)
    with pytest.raises((ValidationError, ValueError), match=match):
        validate_document(payload)


def test_private_cell_flow_round_trips_every_frozen_document() -> None:
    documents = full_flow_documents()
    assert len(documents) == len(SCHEMA_EXPORTS) == 9
    for document in documents:
        wire = json.loads(document.model_dump_json(by_alias=True))
        validate_schema_document(wire)
        validated = validate_document(wire)
        assert type(validated) is type(document)
        assert validated.model_dump(mode="json", by_alias=True) == wire


def test_committed_schemas_are_valid_drift_free_and_manifest_pinned() -> None:
    assert check_schemas() == []
    manifest = json.loads(
        (SCHEMA_ROOT / "schema-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["bundle"] == "planetary.chal-vsource.v1"
    assert manifest["generator"] == {"pydantic": "2.13.4"}
    assert set(manifest["schemas"]) == set(SCHEMA_EXPORTS)
    for filename, descriptor in manifest["schemas"].items():
        schema = json.loads((SCHEMA_ROOT / filename).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        assert schema["x-planetary-semantic-invariants"]
        assert descriptor["sha256"] == hashlib.sha256(
            (SCHEMA_ROOT / filename).read_bytes()
        ).hexdigest()


def test_schema_generator_refuses_an_unpinned_pydantic(monkeypatch) -> None:
    monkeypatch.setattr(schema_tool, "PYDANTIC_VERSION", "2.7.0")
    with pytest.raises(RuntimeError, match="pydantic==2.13.4"):
        schema_tool.check_schemas()


def test_cli_accepts_wire_document_and_rejects_duplicate_keys(tmp_path: Path) -> None:
    valid_path = tmp_path / "request.json"
    valid_path.write_text(request().model_dump_json(by_alias=True), encoding="utf-8")
    validate_path(valid_path)

    duplicate_path = tmp_path / "duplicate.json"
    duplicate_path.write_text(
        '{"schema":"planetary.chal.request.v1","schema":"other"}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate JSON key"):
        validate_path(duplicate_path)


def test_schema_discriminator_is_required_by_all_nine_schemas() -> None:
    for document in full_flow_documents():
        wire = json.loads(document.model_dump_json(by_alias=True))
        wire.pop("schema")
        with pytest.raises(ValueError):
            validate_schema_document(wire)
        with pytest.raises(ValueError, match="unsupported"):
            validate_document(wire)


def test_every_nested_wire_property_is_explicit() -> None:
    def assert_all_properties_required(node: Any) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if node.get("type") == "object" and isinstance(properties, dict):
                assert set(node.get("required", [])) == set(properties)
            for value in node.values():
                assert_all_properties_required(value)
        elif isinstance(node, list):
            for value in node:
                assert_all_properties_required(value)

    for filename in SCHEMA_EXPORTS:
        schema = json.loads((SCHEMA_ROOT / filename).read_text(encoding="utf-8"))
        assert_all_properties_required(schema)

    payload = request_wire()
    payload["parameters"].pop("max_tokens")
    assert_wire_rejected(payload)


def test_non_success_response_requires_structured_correlated_error() -> None:
    response = full_flow_documents()[2].model_dump(mode="json", by_alias=True)
    response["status"] = "degraded"
    response["error"] = None
    assert_wire_rejected(response, "require an error frame")

    response["error"] = error_wire(response["request_sha256"])
    response["error"]["trace_id"] = "trace:different"
    validate_schema_document(response)
    with pytest.raises(ValidationError, match="same request and trace"):
        validate_document(response)


def test_error_lease_and_telemetry_conditionals_match_reference_validator() -> None:
    request_sha = document_sha256(request())
    error = error_wire(request_sha)
    error.update(retryable=False, retry_after_ms=1_000)
    assert_wire_rejected(error)

    lease = full_flow_documents()[5].model_dump(mode="json", by_alias=True)
    lease.update(state="revoked", revocation_reason=None)
    assert_wire_rejected(lease, "require revocation_reason")

    lease = full_flow_documents()[5].model_dump(mode="json", by_alias=True)
    lease["revocation_reason"] = "owner_request"
    assert_wire_rejected(lease, "only revoked")

    telemetry = full_flow_documents()[8].model_dump(mode="json", by_alias=True)
    telemetry.update(status="failed", error_id=None)
    assert_wire_rejected(telemetry, "requires error_id")


def test_lifecycle_schema_enforces_transitions_and_evidence() -> None:
    lifecycle = full_flow_documents()[7].model_dump(mode="json", by_alias=True)
    lifecycle.update(
        previous_state="admitted",
        state="completed",
        sequence=1,
        outputs=[],
    )
    assert_wire_rejected(lifecycle)

    lifecycle.update(previous_state="running", state="checkpointed", outputs=[])
    lifecycle["checkpoint"] = None
    assert_wire_rejected(lifecycle, "requires checkpoint")


def test_lost_lifecycle_state_is_terminal_and_sequence_zero_is_initial_only() -> None:
    lifecycle = full_flow_documents()[7].model_dump(mode="json", by_alias=True)
    lifecycle.update(previous_state="lost", state="staged", sequence=2)
    assert_wire_rejected(lifecycle, "invalid lifecycle transition")

    lifecycle.update(previous_state="admitted", state="staged", sequence=0)
    assert_wire_rejected(lifecycle)


def test_strict_wire_types_match_json_schema_without_coercion() -> None:
    payload = request_wire()
    payload["constraints"]["resources"]["cpu_millicores"] = "2000"
    assert_wire_rejected(payload)

    with pytest.raises(ValidationError):
        ResourceVector(cpu_millicores="2000")
    with pytest.raises(ValidationError):
        ResourceVector(memory_bytes=False)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("request_id",), "request:001\n"),
        (("workload_manifest", "sha256"), HASH_A + "\n"),
        (("device_uri",), "chal://aivm/inference\n"),
    ],
)
def test_json_schema_and_reference_both_reject_terminal_newlines(
    path: tuple[str, ...],
    value: str,
) -> None:
    payload = request_wire()
    target = payload
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    assert_wire_rejected(payload)


@pytest.mark.parametrize("value", [1.0, -0.0])
def test_json_integral_numbers_match_schema_integer_semantics(value: float) -> None:
    payload = request_wire()
    payload["constraints"]["resources"]["cpu_millicores"] = value
    validate_schema_document(payload)
    validated = validate_document(payload)
    assert validated.constraints.resources.cpu_millicores == int(value)


def test_fractional_json_number_is_not_an_integer() -> None:
    payload = request_wire()
    payload["constraints"]["resources"]["cpu_millicores"] = 1.5
    assert_wire_rejected(payload)


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-07-16T12:00:00+00:00",
        "2026-07-16T12:00:00.000Z",
        "2026-07-16T12:00:00z",
    ],
)
def test_timestamps_have_one_cross_language_signing_encoding(timestamp: str) -> None:
    payload = request_wire()
    payload["issued_at"] = timestamp
    assert_wire_rejected(payload, "canonical UTC")


@pytest.mark.parametrize("field", ["command", "code", "marshal", "pickle"])
def test_request_rejects_inline_execution_material(field: str) -> None:
    payload = request_wire()
    payload["parameters"][field] = "do-something"
    assert_wire_rejected(payload, "Extra inputs are not permitted")


def test_request_rejects_unknown_inline_code_field() -> None:
    payload = request_wire()
    payload["inline_code"] = "print('unsafe')"
    assert_wire_rejected(payload, "Extra inputs are not permitted")


def test_rfc8785_digest_is_signature_independent_and_payload_bound() -> None:
    original = request()
    original_digest = document_sha256(original)
    changed_signature = request_wire()
    changed_signature["signature"]["value"] = ALTERNATE_SIGNATURE_VALUE
    assert document_sha256(from_wire(ChalRequest, changed_signature)) == original_digest

    changed_payload = request_wire()
    changed_payload["workload_manifest"]["sha256"] = HASH_B
    changed_request = from_wire(ChalRequest, changed_payload)
    assert changed_request.idempotency_key == original.idempotency_key
    assert document_sha256(changed_request) != original_digest
    assert b'"signature"' not in signing_bytes(original)


def test_request_digest_is_stable_across_python_hash_seeds(tmp_path: Path) -> None:
    path = tmp_path / "request.json"
    path.write_text(request().model_dump_json(by_alias=True), encoding="utf-8")
    code = (
        "from pathlib import Path; import json; "
        "from contracts.chal_vsource.v1.models import validate_document; "
        "from contracts.chal_vsource.v1.canonical import document_sha256; "
        f"p=json.loads(Path({str(path)!r}).read_text()); "
        "print(document_sha256(validate_document(p)))"
    )
    digests = []
    for seed in ("1", "2", "4", "99"):
        env = os.environ.copy()
        env["PYTHONHASHSEED"] = seed
        digests.append(
            subprocess.check_output(
                [sys.executable, "-c", code],
                cwd=Path(__file__).parents[1],
                env=env,
                text=True,
            ).strip()
        )
    assert digests == [digests[0]] * len(digests)


def test_capability_arrays_are_sorted_unique_and_prefixes_are_literal() -> None:
    capability = full_flow_documents()[3].model_dump(mode="json", by_alias=True)
    capability["actions"] = ["reserve", "execute"]
    with pytest.raises(ValidationError, match="lexicographically sorted"):
        validate_document(capability)

    capability = full_flow_documents()[3].model_dump(mode="json", by_alias=True)
    capability["constraints"]["resource_prefixes"] = ["chal://.*"]
    assert_wire_rejected(capability)

    assert device_uri_matches_prefix("chal://aivm/inference", "chal://aivm/")
    assert not device_uri_matches_prefix("chal://aivmx/inference", "chal://aivm/")


def test_signature_rejects_noncanonical_padding_bits() -> None:
    Signature(algorithm="ed25519", key_id="key:owner:001", value="A" * 86)
    with pytest.raises(ValidationError, match="canonically"):
        Signature(
            algorithm="ed25519",
            key_id="key:owner:001",
            value="A" * 85 + "B",
        )


def test_safe_integer_domain_and_nonfinite_metrics_fail_closed() -> None:
    lease = full_flow_documents()[5].model_dump(mode="json", by_alias=True)
    lease["fencing_token"] = MAX_SAFE_INTEGER + 1
    assert_wire_rejected(lease)

    telemetry = full_flow_documents()[8].model_dump(mode="json", by_alias=True)
    telemetry["latency_ms"] = float("inf")
    with pytest.raises(ValueError):
        validate_schema_document(telemetry)
    with pytest.raises(ValueError):
        validate_document(telemetry)


def test_inventory_is_allocatable_only_and_gpu_ids_are_object_keys() -> None:
    inventory = inventory_wire()
    inventory["resources"]["capacity"] = resources_wire()
    assert_wire_rejected(inventory)

    inventory = inventory_wire()
    inventory["resources"]["gpus"]["GPU unsafe"] = inventory["resources"][
        "gpus"
    ].pop("gpu:001")
    assert_wire_rejected(inventory)

    inventory = inventory_wire()
    inventory["resources"]["gpus"]["gpu:001\n"] = inventory["resources"][
        "gpus"
    ].pop("gpu:001")
    assert_wire_rejected(inventory)


def test_placement_binds_account_and_signed_inventory_identity() -> None:
    placement = full_flow_documents()[6].model_dump(mode="json", by_alias=True)
    placement["candidates"][0]["account_id"] = "account:other:001"
    placement["selected_candidate"]["account_id"] = "account:other:001"
    validate_schema_document(placement)
    with pytest.raises(ValidationError, match="decision account"):
        validate_document(placement)

    placement = full_flow_documents()[6].model_dump(mode="json", by_alias=True)
    placement["selected_candidate"]["eligible"] = False
    assert_wire_rejected(placement, "eligible candidate")

    placement = full_flow_documents()[6].model_dump(mode="json", by_alias=True)
    placement["selected_candidate"]["score"] = 0.5
    validate_schema_document(placement)
    with pytest.raises(ValidationError, match="exactly match"):
        validate_document(placement)


def test_lease_is_request_and_inventory_digest_bound_and_fenced() -> None:
    lease = full_flow_documents()[5].model_dump(mode="json", by_alias=True)
    assert lease["request_sha256"] == document_sha256(request())
    assert lease["inventory_id"] == "inventory:001"
    inventory = full_flow_documents()[4]
    assert lease["inventory_sha256"] == document_sha256(inventory)
    lease["fencing_token"] = 0
    assert_wire_rejected(lease)


def test_gpu_authority_and_selected_ids_are_consistent() -> None:
    lease = full_flow_documents()[5].model_dump(mode="json", by_alias=True)
    lease["resources"]["gpu_count"] = 0
    assert_wire_rejected(lease, "both be zero or positive")

    lease = full_flow_documents()[5].model_dump(mode="json", by_alias=True)
    lease["gpu_ids"] = []
    assert_wire_rejected(lease, "gpu_ids count")


def test_private_cell_allocation_reference_enforces_authority_joins() -> None:
    documents = full_flow_documents()
    request_model = documents[0]
    capability = documents[3]
    inventory = documents[4]
    lease = documents[5]
    placement = documents[6]
    validate_private_cell_allocation(
        request_model,
        capability,
        inventory,
        placement,
        lease,
        authenticated_subject_id=capability.subject_id,
    )
    with pytest.raises(ValueError, match="authenticated subject"):
        validate_private_cell_allocation(
            request_model,
            capability,
            inventory,
            placement,
            lease,
            authenticated_subject_id="node-agent:attacker",
        )

    capability_wire = capability.model_dump(mode="json", by_alias=True)
    capability_wire["constraints"]["resources"]["cpu_millicores"] = 1
    constrained = from_wire(CapabilityDocument, capability_wire)
    with pytest.raises(ValueError, match="capability limits"):
        validate_private_cell_allocation(
            request_model,
            constrained,
            inventory,
            placement,
            lease,
            authenticated_subject_id=constrained.subject_id,
        )

    lease_wire = lease.model_dump(mode="json", by_alias=True)
    lease_wire["resources"]["cpu_millicores"] = 3_000
    oversized = from_wire(LeaseDocument, lease_wire)
    with pytest.raises(ValueError, match="signed request"):
        validate_private_cell_allocation(
            request_model,
            capability,
            inventory,
            placement,
            oversized,
            authenticated_subject_id=capability.subject_id,
        )

    inventory_wire_payload = inventory.model_dump(mode="json", by_alias=True)
    inventory_wire_payload["resources"]["allocatable"]["cpu_millicores"] = 1_000
    constrained_inventory = from_wire(ResourceInventory, inventory_wire_payload)
    constrained_inventory_sha = document_sha256(constrained_inventory)
    placement_wire = placement.model_dump(mode="json", by_alias=True)
    placement_wire["candidates"][0]["inventory_sha256"] = constrained_inventory_sha
    placement_wire["selected_candidate"][
        "inventory_sha256"
    ] = constrained_inventory_sha
    constrained_placement = from_wire(PlacementDecision, placement_wire)
    lease_wire = lease.model_dump(mode="json", by_alias=True)
    lease_wire["inventory_sha256"] = constrained_inventory_sha
    constrained_lease = from_wire(LeaseDocument, lease_wire)
    with pytest.raises(ValueError, match="allocatable inventory"):
        validate_private_cell_allocation(
            request_model,
            capability,
            constrained_inventory,
            constrained_placement,
            constrained_lease,
            authenticated_subject_id=capability.subject_id,
        )

    lease_wire = lease.model_dump(mode="json", by_alias=True)
    lease_wire["transport"] = "internet_mtls_relay"
    wrong_transport = from_wire(LeaseDocument, lease_wire)
    with pytest.raises(ValueError, match="transports differ"):
        validate_private_cell_allocation(
            request_model,
            capability,
            inventory,
            placement,
            wrong_transport,
            authenticated_subject_id=capability.subject_id,
        )

    capability_wire = capability.model_dump(mode="json", by_alias=True)
    capability_wire["actions"] = ["execute", "inspect", "release"]
    no_reserve = from_wire(CapabilityDocument, capability_wire)
    with pytest.raises(ValueError, match="reserve and execute"):
        validate_private_cell_allocation(
            request_model,
            no_reserve,
            inventory,
            placement,
            lease,
            authenticated_subject_id=no_reserve.subject_id,
        )

    capability_wire = capability.model_dump(mode="json", by_alias=True)
    capability_wire["constraints"]["minimum_attestation"] = "hardware_verified"
    hardware_only = from_wire(CapabilityDocument, capability_wire)
    with pytest.raises(ValueError, match="attestation"):
        validate_private_cell_allocation(
            request_model,
            hardware_only,
            inventory,
            placement,
            lease,
            authenticated_subject_id=hardware_only.subject_id,
        )

    capability_wire = capability.model_dump(mode="json", by_alias=True)
    capability_wire["audience_node_ids"] = ["node:other:laptop"]
    wrong_audience = from_wire(CapabilityDocument, capability_wire)
    with pytest.raises(ValueError, match="capability audience"):
        validate_private_cell_allocation(
            request_model,
            wrong_audience,
            inventory,
            placement,
            lease,
            authenticated_subject_id=wrong_audience.subject_id,
        )

    capability_wire = capability.model_dump(mode="json", by_alias=True)
    capability_wire["constraints"]["workload_kinds"] = ["embedding"]
    wrong_workload = from_wire(CapabilityDocument, capability_wire)
    with pytest.raises(ValueError, match="workload"):
        validate_private_cell_allocation(
            request_model,
            wrong_workload,
            inventory,
            placement,
            lease,
            authenticated_subject_id=wrong_workload.subject_id,
        )

    capability_wire = capability.model_dump(mode="json", by_alias=True)
    capability_wire["constraints"]["resource_prefixes"] = ["chal://knowledge/"]
    wrong_prefix = from_wire(CapabilityDocument, capability_wire)
    with pytest.raises(ValueError, match="resource prefixes"):
        validate_private_cell_allocation(
            request_model,
            wrong_prefix,
            inventory,
            placement,
            lease,
            authenticated_subject_id=wrong_prefix.subject_id,
        )


def test_results_bind_the_exact_active_lease_revision() -> None:
    documents = full_flow_documents()
    response = documents[2]
    lease = documents[5]
    lifecycle = documents[7]
    validate_lease_bound_response(response, lease)
    validate_lease_bound_lifecycle(lifecycle, lease)

    renewed_wire = lease.model_dump(mode="json", by_alias=True)
    renewed_wire.update(
        fencing_token=lease.fencing_token + 1,
        renewal_sequence=lease.renewal_sequence + 1,
        renewals_remaining=lease.renewals_remaining - 1,
    )
    renewed = from_wire(LeaseDocument, renewed_wire)
    assert document_sha256(renewed) != document_sha256(lease)
    with pytest.raises(ValueError, match="exact fenced lease"):
        validate_lease_bound_response(response, renewed)
    with pytest.raises(ValueError, match="exact fenced lease"):
        validate_lease_bound_lifecycle(lifecycle, renewed)


def test_ttl_limits_are_structurally_enforced() -> None:
    request_payload = request_wire()
    request_payload["ttl_seconds"] = 3_601
    assert_wire_rejected(request_payload)

    inventory = inventory_wire(ttl_seconds=301)
    assert_wire_rejected(inventory)

    lease = full_flow_documents()[5].model_dump(mode="json", by_alias=True)
    lease["ttl_seconds"] = 901
    assert_wire_rejected(lease)


@pytest.mark.parametrize("label", ["prompt", "output", "token", "content"])
def test_telemetry_has_no_raw_or_secret_bearing_label_field(label: str) -> None:
    telemetry = full_flow_documents()[8].model_dump(mode="json", by_alias=True)
    telemetry["labels"][label] = "must-not-cross-the-boundary"
    assert_wire_rejected(telemetry, "Extra inputs are not permitted")


def test_error_frame_has_no_free_form_detail_field() -> None:
    payload = error_wire(document_sha256(request()))
    payload["safe_detail"] = "raw prompt or secret could leak here"
    assert_wire_rejected(payload, "Extra inputs are not permitted")
