"""Canonical CHAL/vSource v1 protocol models.

The models are intentionally strict and content-reference based. They freeze
the private-cell control-plane boundary before any remote scheduler or node
agent is implemented. Arbitrary code, shell commands, pickle, marshal, and raw
user content are not valid protocol fields.
"""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    WithJsonSchema,
    field_validator,
    model_validator,
)

from .canonical import document_sha256


Identifier = Annotated[
    str,
    Field(min_length=3, max_length=128, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._:-]+$"),
]
Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
MAX_SAFE_INTEGER = 9_007_199_254_740_991


def _normalize_json_integer(value: Any) -> Any:
    """Align strict Pydantic parsing with JSON Schema's integer semantics."""

    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


JsonInteger = Annotated[int, BeforeValidator(_normalize_json_integer)]
NonNegativeSafeInt = Annotated[
    JsonInteger,
    Field(ge=0, le=MAX_SAFE_INTEGER),
]
PositiveSafeInt = Annotated[
    JsonInteger,
    Field(ge=1, le=MAX_SAFE_INTEGER),
]
GpuCount = Annotated[JsonInteger, Field(ge=0, le=64)]


def _require_canonical_timestamp(value: Any) -> Any:
    if isinstance(value, str):
        try:
            parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError as exc:
            raise ValueError(
                "timestamp must use canonical UTC second encoding YYYY-MM-DDTHH:MM:SSZ"
            ) from exc
        if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
            raise ValueError("timestamp must use canonical UTC second encoding")
        return parsed.replace(tzinfo=timezone.utc)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp datetime must be timezone-aware")
        if value.utcoffset().total_seconds() != 0 or value.microsecond != 0:
            raise ValueError("timestamp datetime must be UTC with second precision")
        return value
    raise ValueError("timestamp must be a canonical UTC string or datetime")


CanonicalTimestamp = Annotated[
    datetime,
    BeforeValidator(_require_canonical_timestamp),
    WithJsonSchema(
        {
            "format": "date-time",
            "pattern": (
                r"^[0-9]{4}-(0[1-9]|1[0-2])-"
                r"(0[1-9]|[12][0-9]|3[01])T"
                r"([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z$"
            ),
            "type": "string",
        }
    ),
]
DeviceUri = Annotated[
    str,
    Field(
        min_length=10,
        max_length=256,
        pattern=r"^chal://[a-z0-9][a-z0-9._-]*(/[a-z0-9][a-z0-9._-]*)*$",
    ),
]
DeviceUriPrefix = Annotated[
    str,
    Field(
        min_length=11,
        max_length=257,
        pattern=r"^chal://[a-z0-9][a-z0-9._-]*(/[a-z0-9][a-z0-9._-]*)*/$",
    ),
]
Uri = Annotated[
    str,
    Field(
        min_length=8,
        max_length=512,
        pattern=r"^(artifact|aivm|chal|kc|mem)://[A-Za-z0-9][A-Za-z0-9._~:/?#@!$&'()*+,;=%-]*$",
    ),
]


def _require_canonical_sequence(values: list[Any], field_name: str) -> list[Any]:
    encoded = [
        value.value if isinstance(value, StrEnum) else str(value) for value in values
    ]
    if encoded != sorted(set(encoded)):
        raise ValueError(f"{field_name} must be unique and lexicographically sorted")
    return values


def device_uri_matches_prefix(device_uri: str, resource_prefix: str) -> bool:
    """Match a normalized CHAL URI by literal, segment-bounded prefix."""

    return device_uri.startswith(resource_prefix)


class StrictContract(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=False,
        strict=True,
        validate_assignment=True,
    )

    @field_validator("*", mode="after")
    @classmethod
    def require_timezone_on_datetimes(cls, value: Any) -> Any:
        if isinstance(value, datetime) and (
            value.tzinfo is None or value.utcoffset() is None
        ):
            raise ValueError("protocol timestamps must include a UTC offset")
        return value


class TrustZone(StrEnum):
    LOCAL_CONTROLLER = "local_controller"
    PERSONAL_CELL = "personal_cell"


class WorkloadKind(StrEnum):
    RETRIEVAL = "retrieval"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    INFERENCE = "inference"
    EVALUATION = "evaluation"
    SIMULATION = "simulation"
    RENDERING = "rendering"
    CHECKPOINTABLE_TRAINING = "checkpointable_training"


class TransportKind(StrEnum):
    LOCAL_PROCESS = "local_process"
    UNIX_SOCKET = "unix_socket"
    LAN_MTLS = "lan_mtls"
    INTERNET_MTLS_RELAY = "internet_mtls_relay"
    QUALIFIED_RDMA = "qualified_rdma"


class CapabilityAction(StrEnum):
    INSPECT = "inspect"
    RESERVE = "reserve"
    EXECUTE = "execute"
    CHECKPOINT = "checkpoint"
    CANCEL = "cancel"
    RELEASE = "release"
    READ_ARTIFACT = "read_artifact"
    WRITE_ARTIFACT = "write_artifact"


class AttestationLevel(StrEnum):
    UNVERIFIED = "unverified"
    SOFTWARE_VERIFIED = "software_verified"
    HARDWARE_VERIFIED = "hardware_verified"


class Signature(StrictContract):
    algorithm: Literal["ed25519"]
    key_id: Identifier
    value: Annotated[
        str,
        Field(min_length=86, max_length=86, pattern=r"^[A-Za-z0-9_-]{86}$"),
    ]

    @field_validator("value")
    @classmethod
    def require_canonical_ed25519_base64url(cls, value: str) -> str:
        try:
            decoded = base64.urlsafe_b64decode(value + "==")
        except (binascii.Error, ValueError) as exc:
            raise ValueError("signature must be canonical unpadded base64url") from exc
        canonical = base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii")
        if len(decoded) != 64 or canonical != value:
            raise ValueError("signature must encode exactly 64 bytes canonically")
        return value


class ContentReference(StrictContract):
    uri: Uri
    sha256: Sha256
    size_bytes: NonNegativeSafeInt
    media_type: Annotated[str, Field(min_length=3, max_length=128)]
    classification: Literal["public", "private", "restricted"]


class ResourceVector(StrictContract):
    cpu_millicores: NonNegativeSafeInt
    memory_bytes: NonNegativeSafeInt
    gpu_count: GpuCount
    gpu_memory_bytes: NonNegativeSafeInt
    storage_bytes: NonNegativeSafeInt
    ingress_bps: NonNegativeSafeInt
    egress_bps: NonNegativeSafeInt

    @model_validator(mode="after")
    def require_consistent_gpu_authority(self) -> "ResourceVector":
        if (self.gpu_count == 0) != (self.gpu_memory_bytes == 0):
            raise ValueError("gpu_count and gpu_memory_bytes must both be zero or positive")
        return self


class HostResourceVector(StrictContract):
    cpu_millicores: NonNegativeSafeInt
    memory_bytes: NonNegativeSafeInt
    storage_bytes: NonNegativeSafeInt
    ingress_bps: NonNegativeSafeInt
    egress_bps: NonNegativeSafeInt


class RequestConstraints(StrictContract):
    resources: ResourceVector
    latency_budget_ms: Annotated[JsonInteger, Field(ge=1, le=3_600_000)]
    grounding_required: bool
    template_leakage_allowed: Literal[False]
    network_access: Literal["none", "artifact_plane_only"]
    checkpoint_required: bool


class WorkloadParameters(StrictContract):
    """Allowlisted scalar tuning knobs; inputs remain content references."""

    batch_size: Annotated[JsonInteger, Field(ge=1, le=65_536)] | None
    max_tokens: Annotated[JsonInteger, Field(ge=1, le=1_000_000)] | None
    temperature: Annotated[
        float,
        Field(ge=0.0, le=2.0, allow_inf_nan=False),
    ] | None
    top_k: Annotated[JsonInteger, Field(ge=1, le=1_000_000)] | None
    seed: NonNegativeSafeInt | None
    precision: Literal["auto", "fp32", "fp16", "bf16", "int8", "int4"] | None
    checkpoint_interval_seconds: Annotated[
        JsonInteger,
        Field(ge=1, le=86_400),
    ] | None
    replica_count: Annotated[JsonInteger, Field(ge=1, le=1_024)] | None
    chunk_size: Annotated[JsonInteger, Field(ge=1, le=1_000_000)] | None
    width: Annotated[JsonInteger, Field(ge=1, le=32_768)] | None
    height: Annotated[JsonInteger, Field(ge=1, le=32_768)] | None
    steps: Annotated[JsonInteger, Field(ge=1, le=1_000_000)] | None
    deterministic: bool


class ChalRequest(StrictContract):
    schema_id: Literal["planetary.chal.request.v1"] = Field(
        ...,
        alias="schema",
    )
    request_id: Identifier
    trace_id: Identifier
    parent_request_id: Identifier | None
    issued_at: CanonicalTimestamp
    ttl_seconds: Annotated[JsonInteger, Field(ge=1, le=3_600)]
    idempotency_key: Identifier
    account_id: Identifier
    capability_id: Identifier
    device_uri: DeviceUri
    workload_kind: WorkloadKind
    workload_manifest: ContentReference
    inputs: list[ContentReference] = Field(max_length=128)
    parameters: WorkloadParameters
    constraints: RequestConstraints
    signature: Signature


class ResponseGrant(StrictContract):
    """Controller authority for ONE computed response to travel home.

    A lease authorizes delivery TO a leased node, so it cannot carry a result
    back to the requester; and a computed result's digest cannot be named in a
    request signed before the work ran. A grant closes both gaps without
    weakening either rule: it is a separate controller-signed document that
    authorizes exactly one bounded response, from one named responder, to one
    named destination, answering one exact request digest.

    The response digest is deliberately absent — that is the concession, and it
    is irreducible: nobody can hash a computation that has not happened. What is
    bound instead is everything around it, so the unconstrained value sits in a
    single narrow place surrounded by owner-signed values.

    Deliberately NOT part of `ChalRequest`: adding a field there would change
    the canonical bytes of every request ever signed, invalidating existing
    signatures and recorded evidence digests.
    """

    schema_id: Literal["planetary.chal.response_grant.v1"] = Field(
        ...,
        alias="schema",
    )
    grant_id: Identifier
    account_id: Identifier
    # The exact signed request this response answers.
    request_sha256: Sha256
    # The lease under which the forward leg ran, so a grant cannot be paired
    # with an unrelated placement.
    lease_id: Identifier
    lease_sha256: Sha256
    fencing_token: Annotated[JsonInteger, Field(ge=1)]
    # Exactly one node may fill it, and exactly one may receive it.
    responder_node_id: Identifier
    destination_node_id: Identifier
    # Hard ceiling and an exact media type. No wildcards, no lists.
    max_byte_length: Annotated[JsonInteger, Field(ge=1, le=8 * 1024 * 1024)]
    media_type: Annotated[str, Field(min_length=3, max_length=128)]
    transport: TransportKind
    issued_at: CanonicalTimestamp
    ttl_seconds: Annotated[JsonInteger, Field(ge=1, le=3_600)]
    signature: Signature

    @model_validator(mode="after")
    def require_distinct_endpoints(self) -> "ResponseGrant":
        if self.responder_node_id == self.destination_node_id:
            raise ValueError("response grant endpoints must differ")
        return self


class ErrorCode(StrEnum):
    INVALID_REQUEST = "invalid_request"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    CAPABILITY_EXPIRED = "capability_expired"
    CAPABILITY_REVOKED = "capability_revoked"
    NO_PLACEMENT = "no_placement"
    LEASE_CONFLICT = "lease_conflict"
    LEASE_EXPIRED = "lease_expired"
    NODE_UNAVAILABLE = "node_unavailable"
    TRANSPORT_UNAVAILABLE = "transport_unavailable"
    RESOURCE_EXHAUSTED = "resource_exhausted"
    WORKLOAD_REJECTED = "workload_rejected"
    WORKLOAD_FAILED = "workload_failed"
    INTEGRITY_FAILURE = "integrity_failure"
    ATTESTATION_FAILED = "attestation_failed"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    INTERNAL_ERROR = "internal_error"


class ErrorFrame(StrictContract):
    schema_id: Literal["planetary.chal.error.v1"] = Field(
        ...,
        alias="schema",
    )
    error_id: Identifier
    request_id: Identifier
    request_sha256: Sha256
    trace_id: Identifier
    code: ErrorCode
    retryable: bool
    diagnostic_id: Identifier | None
    retry_after_ms: Annotated[JsonInteger, Field(ge=1, le=3_600_000)] | None
    device_uri: DeviceUri | None
    signature: Signature

    @model_validator(mode="after")
    def validate_retry_fields(self) -> "ErrorFrame":
        if not self.retryable and self.retry_after_ms is not None:
            raise ValueError("non-retryable errors cannot specify retry_after_ms")
        return self


class ResponseStatus(StrEnum):
    SUCCEEDED = "succeeded"
    DEGRADED = "degraded"
    REJECTED = "rejected"
    FAILED = "failed"


class ChalResponse(StrictContract):
    schema_id: Literal["planetary.chal.response.v1"] = Field(
        ...,
        alias="schema",
    )
    response_id: Identifier
    request_id: Identifier
    request_sha256: Sha256
    trace_id: Identifier
    account_id: Identifier
    node_id: Identifier
    device_uri: DeviceUri
    lease_id: Identifier
    lease_sha256: Sha256
    fencing_token: PositiveSafeInt
    status: ResponseStatus
    completed_at: CanonicalTimestamp
    outputs: list[ContentReference] = Field(max_length=128)
    telemetry_ids: list[Identifier] = Field(max_length=256)
    error: ErrorFrame | None
    signature: Signature

    @model_validator(mode="after")
    def require_error_for_non_success(self) -> "ChalResponse":
        if self.status == ResponseStatus.SUCCEEDED and self.error is not None:
            raise ValueError("successful responses cannot contain an error")
        if self.status != ResponseStatus.SUCCEEDED and self.error is None:
            raise ValueError("non-success responses require an error frame")
        if self.error is not None and (
            self.error.request_id != self.request_id
            or self.error.request_sha256 != self.request_sha256
            or self.error.trace_id != self.trace_id
        ):
            raise ValueError("response error must identify the same request and trace")
        return self


class CapabilityConstraints(StrictContract):
    resources: ResourceVector
    minimum_attestation: AttestationLevel
    workload_kinds: list[WorkloadKind] = Field(
        min_length=1,
        json_schema_extra={"uniqueItems": True, "x-canonical-order": "lexicographic"},
    )
    transports: list[TransportKind] = Field(
        min_length=1,
        json_schema_extra={"uniqueItems": True, "x-canonical-order": "lexicographic"},
    )
    resource_prefixes: list[DeviceUriPrefix] = Field(
        min_length=1,
        max_length=128,
        json_schema_extra={"uniqueItems": True, "x-canonical-order": "lexicographic"},
    )

    @field_validator("workload_kinds", "transports", "resource_prefixes")
    @classmethod
    def require_canonical_arrays(cls, values: list[Any], info: Any) -> list[Any]:
        return _require_canonical_sequence(values, info.field_name)


class CapabilityDocument(StrictContract):
    schema_id: Literal["planetary.chal.capability.v1"] = Field(
        ...,
        alias="schema",
    )
    capability_id: Identifier
    issuer_id: Identifier
    subject_id: Identifier
    account_id: Identifier
    audience_node_ids: list[Identifier] = Field(
        min_length=1,
        max_length=128,
        json_schema_extra={"uniqueItems": True, "x-canonical-order": "lexicographic"},
    )
    actions: list[CapabilityAction] = Field(
        min_length=1,
        json_schema_extra={"uniqueItems": True, "x-canonical-order": "lexicographic"},
    )
    constraints: CapabilityConstraints
    not_before: CanonicalTimestamp
    ttl_seconds: Annotated[JsonInteger, Field(ge=1, le=3_600)]
    nonce: Annotated[
        str,
        Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"),
    ]
    revocation_epoch: NonNegativeSafeInt
    delegable: Literal[False]
    signature: Signature

    @field_validator("audience_node_ids", "actions")
    @classmethod
    def require_canonical_arrays(cls, values: list[Any], info: Any) -> list[Any]:
        return _require_canonical_sequence(values, info.field_name)


class CpuDescriptor(StrictContract):
    architecture: Literal["x86_64", "aarch64", "riscv64"]
    logical_cores: Annotated[JsonInteger, Field(ge=1, le=4096)]
    features: list[
        Annotated[str, Field(max_length=64, pattern=r"^[a-z0-9][a-z0-9._-]*$")]
    ] = Field(
        json_schema_extra={"uniqueItems": True, "x-canonical-order": "lexicographic"},
    )

    @field_validator("features")
    @classmethod
    def require_canonical_features(cls, values: list[str]) -> list[str]:
        return _require_canonical_sequence(values, "features")


class GpuDescriptor(StrictContract):
    vendor: Annotated[str, Field(min_length=1, max_length=64)]
    model: Annotated[str, Field(min_length=1, max_length=128)]
    allocatable_memory_bytes: NonNegativeSafeInt
    compute_apis: list[Literal["cuda", "metal", "opencl", "rocm", "vulkan"]] = (
        Field(
            min_length=1,
            json_schema_extra={
                "uniqueItems": True,
                "x-canonical-order": "lexicographic",
            },
        )
    )

    @field_validator("compute_apis")
    @classmethod
    def require_canonical_compute_apis(cls, values: list[str]) -> list[str]:
        return _require_canonical_sequence(values, "compute_apis")


class NodeResources(StrictContract):
    allocatable: HostResourceVector
    cpu: CpuDescriptor
    gpus: dict[Identifier, GpuDescriptor] = Field(
        max_length=64,
        json_schema_extra={"additionalProperties": False},
    )


class NodeHealth(StrEnum):
    READY = "ready"
    DRAINING = "draining"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class NodeLabels(StrictContract):
    power_class: Literal["battery", "consumer", "workstation", "server"] | None
    thermal_policy: Literal["quiet", "balanced", "performance"] | None
    network_scope: Literal["local", "trusted_lan", "mtls_relay"] | None


class ResourceInventory(StrictContract):
    schema_id: Literal["planetary.vsource.inventory.v1"] = Field(
        ...,
        alias="schema",
    )
    inventory_id: Identifier
    node_id: Identifier
    account_id: Identifier
    trust_zone: Literal["personal_cell"]
    public_key_fingerprint: Sha256
    attestation: AttestationLevel
    observed_at: CanonicalTimestamp
    ttl_seconds: Annotated[JsonInteger, Field(ge=1, le=300)]
    health: NodeHealth
    resources: NodeResources
    transports: list[TransportKind] = Field(
        min_length=1,
        json_schema_extra={"uniqueItems": True, "x-canonical-order": "lexicographic"},
    )
    workload_kinds: list[WorkloadKind] = Field(
        min_length=1,
        json_schema_extra={"uniqueItems": True, "x-canonical-order": "lexicographic"},
    )
    labels: NodeLabels
    signature: Signature

    @field_validator("transports", "workload_kinds")
    @classmethod
    def require_canonical_arrays(cls, values: list[Any], info: Any) -> list[Any]:
        return _require_canonical_sequence(values, info.field_name)


class LeaseState(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    RELEASED = "released"
    EXPIRED = "expired"
    REVOKED = "revoked"


class LeaseRevocationReason(StrEnum):
    OWNER_REQUEST = "owner_request"
    POLICY_CHANGE = "policy_change"
    CAPABILITY_REVOKED = "capability_revoked"
    NODE_HEALTH = "node_health"
    INTEGRITY_FAILURE = "integrity_failure"
    LEASE_SUPERSEDED = "lease_superseded"


class LeaseDocument(StrictContract):
    schema_id: Literal["planetary.vsource.lease.v1"] = Field(
        ...,
        alias="schema",
    )
    lease_id: Identifier
    placement_id: Identifier
    request_id: Identifier
    request_sha256: Sha256
    capability_id: Identifier
    node_id: Identifier
    inventory_id: Identifier
    inventory_sha256: Sha256
    account_id: Identifier
    transport: TransportKind
    resources: ResourceVector
    gpu_ids: list[Identifier] = Field(
        max_length=64,
        json_schema_extra={"uniqueItems": True, "x-canonical-order": "lexicographic"},
    )
    state: LeaseState
    not_before: CanonicalTimestamp
    ttl_seconds: Annotated[JsonInteger, Field(ge=1, le=900)]
    fencing_token: PositiveSafeInt
    renewal_sequence: Annotated[JsonInteger, Field(ge=0, le=1024)]
    renewals_remaining: Annotated[JsonInteger, Field(ge=0, le=1024)]
    revocation_reason: LeaseRevocationReason | None
    signature: Signature

    @model_validator(mode="after")
    def validate_lease(self) -> "LeaseDocument":
        if self.state == LeaseState.REVOKED and not self.revocation_reason:
            raise ValueError("revoked leases require revocation_reason")
        if self.state != LeaseState.REVOKED and self.revocation_reason is not None:
            raise ValueError("only revoked leases may specify revocation_reason")
        _require_canonical_sequence(self.gpu_ids, "gpu_ids")
        if len(self.gpu_ids) != self.resources.gpu_count:
            raise ValueError("gpu_ids count must equal resources.gpu_count")
        return self


class PlacementCandidate(StrictContract):
    node_id: Identifier
    account_id: Identifier
    inventory_id: Identifier
    inventory_sha256: Sha256
    eligible: bool
    score: Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
    reasons: list[
        Annotated[str, Field(max_length=64, pattern=r"^[a-z0-9][a-z0-9._-]*$")]
    ] = Field(
        max_length=32,
        json_schema_extra={"uniqueItems": True, "x-canonical-order": "lexicographic"},
    )

    @field_validator("reasons")
    @classmethod
    def require_canonical_reasons(cls, values: list[str]) -> list[str]:
        return _require_canonical_sequence(values, "reasons")


class PlacementResult(StrEnum):
    PLACED = "placed"
    UNPLACED = "unplaced"


class PlacementDecision(StrictContract):
    schema_id: Literal["planetary.vsource.placement.v1"] = Field(
        ...,
        alias="schema",
    )
    placement_id: Identifier
    request_id: Identifier
    request_sha256: Sha256
    trace_id: Identifier
    account_id: Identifier
    scheduler_id: Identifier
    scheduler_scope: Literal["same_account_private_cell"]
    transport: TransportKind
    decided_at: CanonicalTimestamp
    result: PlacementResult
    selected_candidate: PlacementCandidate | None
    candidates: list[PlacementCandidate] = Field(min_length=1, max_length=256)
    policy_version: Identifier
    rejection_error: ErrorFrame | None
    signature: Signature

    @model_validator(mode="after")
    def validate_decision(self) -> "PlacementDecision":
        candidate_keys = [
            (candidate.node_id, candidate.inventory_id, candidate.inventory_sha256)
            for candidate in self.candidates
        ]
        if len(candidate_keys) != len(set(candidate_keys)):
            raise ValueError("placement candidates require unique inventory bindings")
        if any(candidate.account_id != self.account_id for candidate in self.candidates):
            raise ValueError("placement candidates must belong to the decision account")
        if self.result == PlacementResult.PLACED:
            if self.selected_candidate is None or not self.selected_candidate.eligible:
                raise ValueError("placed decision must select an eligible candidate")
            selected_key = (
                self.selected_candidate.node_id,
                self.selected_candidate.inventory_id,
                self.selected_candidate.inventory_sha256,
            )
            if selected_key not in candidate_keys:
                raise ValueError("selected candidate must be present in candidates")
            if self.selected_candidate not in self.candidates:
                raise ValueError("selected candidate must exactly match its candidate entry")
            if self.selected_candidate.account_id != self.account_id:
                raise ValueError("selected candidate must belong to the decision account")
            if self.rejection_error is not None:
                raise ValueError("placed decision cannot contain rejection_error")
        else:
            if self.selected_candidate is not None:
                raise ValueError("unplaced decision cannot select a node")
            if self.rejection_error is None:
                raise ValueError("unplaced decision requires rejection_error")
            if (
                self.rejection_error.request_id != self.request_id
                or self.rejection_error.request_sha256 != self.request_sha256
                or self.rejection_error.trace_id != self.trace_id
            ):
                raise ValueError("placement error must identify the same request and trace")
        return self


class LifecycleState(StrEnum):
    ADMITTED = "admitted"
    STAGED = "staged"
    RUNNING = "running"
    CHECKPOINTED = "checkpointed"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EVICTED = "evicted"
    LOST = "lost"


_LIFECYCLE_TRANSITIONS: dict[LifecycleState, set[LifecycleState]] = {
    LifecycleState.ADMITTED: {
        LifecycleState.STAGED,
        LifecycleState.CANCELLED,
        LifecycleState.FAILED,
    },
    LifecycleState.STAGED: {
        LifecycleState.RUNNING,
        LifecycleState.CANCELLED,
        LifecycleState.FAILED,
    },
    LifecycleState.RUNNING: {
        LifecycleState.CHECKPOINTED,
        LifecycleState.COMPLETED,
        LifecycleState.FAILED,
        LifecycleState.CANCELLED,
        LifecycleState.EVICTED,
        LifecycleState.LOST,
    },
    LifecycleState.CHECKPOINTED: {
        LifecycleState.RUNNING,
        LifecycleState.COMPLETED,
        LifecycleState.FAILED,
        LifecycleState.CANCELLED,
        LifecycleState.EVICTED,
        LifecycleState.LOST,
    },
    LifecycleState.EVICTED: {
        LifecycleState.STAGED,
        LifecycleState.FAILED,
        LifecycleState.CANCELLED,
    },
    LifecycleState.LOST: set(),
    LifecycleState.COMPLETED: set(),
    LifecycleState.FAILED: set(),
    LifecycleState.CANCELLED: set(),
}


def validate_lifecycle_transition(
    previous: LifecycleState | None,
    current: LifecycleState,
) -> None:
    if previous is None:
        if current != LifecycleState.ADMITTED:
            raise ValueError("the first lifecycle event must be admitted")
        return
    if current not in _LIFECYCLE_TRANSITIONS[previous]:
        raise ValueError(f"invalid lifecycle transition: {previous} -> {current}")


class LifecycleEvent(StrictContract):
    schema_id: Literal["planetary.vsource.lifecycle.v1"] = Field(
        ...,
        alias="schema",
    )
    event_id: Identifier
    sequence: NonNegativeSafeInt
    workload_id: Identifier
    request_id: Identifier
    request_sha256: Sha256
    trace_id: Identifier
    placement_id: Identifier
    lease_id: Identifier
    lease_sha256: Sha256
    fencing_token: PositiveSafeInt
    node_id: Identifier
    inventory_id: Identifier
    inventory_sha256: Sha256
    account_id: Identifier
    previous_state: LifecycleState | None
    state: LifecycleState
    occurred_at: CanonicalTimestamp
    checkpoint: ContentReference | None
    outputs: list[ContentReference] = Field(max_length=128)
    error: ErrorFrame | None
    signature: Signature

    @model_validator(mode="after")
    def validate_event(self) -> "LifecycleEvent":
        validate_lifecycle_transition(self.previous_state, self.state)
        if self.previous_state is None and self.sequence != 0:
            raise ValueError("the first lifecycle event must use sequence zero")
        if self.previous_state is not None and self.sequence == 0:
            raise ValueError("non-initial lifecycle events require a positive sequence")
        if self.state == LifecycleState.COMPLETED and not self.outputs:
            raise ValueError("completed lifecycle event requires output references")
        if self.state in {LifecycleState.FAILED, LifecycleState.LOST} and not self.error:
            raise ValueError(f"{self.state} lifecycle event requires an error")
        if self.state == LifecycleState.CHECKPOINTED and not self.checkpoint:
            raise ValueError("checkpointed lifecycle event requires checkpoint reference")
        if self.error is not None and (
            self.error.request_id != self.request_id
            or self.error.request_sha256 != self.request_sha256
            or self.error.trace_id != self.trace_id
        ):
            raise ValueError("lifecycle error must identify the same request and trace")
        return self


class TelemetryPhase(StrEnum):
    ADMISSION = "admission"
    QUEUE = "queue"
    TRANSFER = "transfer"
    EXECUTION = "execution"
    CHECKPOINT = "checkpoint"
    VERIFICATION = "verification"
    RELEASE = "release"


class TelemetryLabels(StrictContract):
    """Bounded operational dimensions; user content has no label field."""

    backend: Literal[
        "local_process",
        "aivm_container",
        "aivm_microvm",
        "aivm_wasm",
    ] | None
    route: Literal[
        "fast_path",
        "grounded_path",
        "deep_reasoning_path",
        "quad_brain_path",
        "safety_path",
    ] | None
    accelerator: Literal["cpu", "cuda", "metal", "rocm", "vulkan"] | None
    degradation_code: Literal[
        "deadline_pressure",
        "node_draining",
        "resource_pressure",
        "transport_fallback",
        "verification_pending",
    ] | None
    verification: Literal["unverified", "verified", "rejected"] | None


class TelemetryEvent(StrictContract):
    schema_id: Literal["planetary.chal.telemetry.v1"] = Field(
        ...,
        alias="schema",
    )
    telemetry_id: Identifier
    request_id: Identifier
    request_sha256: Sha256
    trace_id: Identifier
    workload_id: Identifier | None
    node_id: Identifier | None
    recorded_at: CanonicalTimestamp
    phase: TelemetryPhase
    status: Literal["ok", "degraded", "failed"]
    measurement_kind: Literal["measured", "estimated"]
    latency_ms: Annotated[
        float,
        Field(ge=0.0, le=31_536_000_000.0, allow_inf_nan=False),
    ]
    queue_ms: Annotated[
        float,
        Field(ge=0.0, le=31_536_000_000.0, allow_inf_nan=False),
    ]
    usage: ResourceVector
    input_sha256: Sha256 | None
    output_sha256: Sha256 | None
    contains_user_content: Literal[False]
    labels: TelemetryLabels
    error_id: Identifier | None
    signature: Signature

    @model_validator(mode="after")
    def validate_status_error(self) -> "TelemetryEvent":
        if self.status == "failed" and not self.error_id:
            raise ValueError("failed telemetry requires error_id")
        return self


_RESOURCE_VECTOR_FIELDS = (
    "cpu_millicores",
    "memory_bytes",
    "gpu_count",
    "gpu_memory_bytes",
    "storage_bytes",
    "ingress_bps",
    "egress_bps",
)
_HOST_RESOURCE_FIELDS = (
    "cpu_millicores",
    "memory_bytes",
    "storage_bytes",
    "ingress_bps",
    "egress_bps",
)
_ATTESTATION_RANK = {
    AttestationLevel.UNVERIFIED: 0,
    AttestationLevel.SOFTWARE_VERIFIED: 1,
    AttestationLevel.HARDWARE_VERIFIED: 2,
}


def resource_vector_within(requested: ResourceVector, limit: ResourceVector) -> bool:
    """Return whether every requested resource component is within its limit."""

    return all(
        getattr(requested, field) <= getattr(limit, field)
        for field in _RESOURCE_VECTOR_FIELDS
    )


def validate_lease_bound_response(
    response: ChalResponse,
    lease: LeaseDocument,
) -> None:
    """Require a result to identify the exact active fenced lease revision."""

    if lease.state != LeaseState.ACTIVE:
        raise ValueError("response requires an active lease")
    if (
        response.request_id != lease.request_id
        or response.request_sha256 != lease.request_sha256
        or response.account_id != lease.account_id
        or response.node_id != lease.node_id
        or response.lease_id != lease.lease_id
        or response.lease_sha256 != document_sha256(lease)
        or response.fencing_token != lease.fencing_token
    ):
        raise ValueError("response does not match the exact fenced lease revision")


def validate_lease_bound_lifecycle(
    event: LifecycleEvent,
    lease: LeaseDocument,
) -> None:
    """Require a lifecycle event to identify the exact active lease revision."""

    if lease.state != LeaseState.ACTIVE:
        raise ValueError("lifecycle event requires an active lease")
    if (
        event.request_id != lease.request_id
        or event.request_sha256 != lease.request_sha256
        or event.account_id != lease.account_id
        or event.node_id != lease.node_id
        or event.placement_id != lease.placement_id
        or event.lease_id != lease.lease_id
        or event.lease_sha256 != document_sha256(lease)
        or event.fencing_token != lease.fencing_token
        or event.inventory_id != lease.inventory_id
        or event.inventory_sha256 != lease.inventory_sha256
    ):
        raise ValueError("lifecycle event does not match the exact fenced lease revision")


def validate_private_cell_allocation(
    request: ChalRequest,
    capability: CapabilityDocument,
    inventory: ResourceInventory,
    placement: PlacementDecision,
    lease: LeaseDocument,
    *,
    authenticated_subject_id: str,
) -> None:
    """Reference validator for the normative same-account allocation joins."""

    account_ids = {
        request.account_id,
        capability.account_id,
        inventory.account_id,
        placement.account_id,
        lease.account_id,
    }
    if len(account_ids) != 1:
        raise ValueError("request, capability, inventory, placement, and lease accounts differ")

    request_sha256 = document_sha256(request)
    inventory_sha256 = document_sha256(inventory)
    if request.capability_id != capability.capability_id:
        raise ValueError("request does not identify the supplied capability")
    if authenticated_subject_id != capability.subject_id:
        raise ValueError("authenticated subject does not match the capability subject")
    if lease.capability_id != capability.capability_id:
        raise ValueError("lease does not identify the supplied capability")
    if placement.request_id != request.request_id or lease.request_id != request.request_id:
        raise ValueError("placement or lease request_id does not match the request")
    if (
        placement.request_sha256 != request_sha256
        or lease.request_sha256 != request_sha256
    ):
        raise ValueError("placement or lease request digest does not match")

    if placement.result != PlacementResult.PLACED or placement.selected_candidate is None:
        raise ValueError("allocation requires a placed eligible candidate")
    if lease.state not in {LeaseState.PENDING, LeaseState.ACTIVE}:
        raise ValueError("new allocation requires a pending or active lease")
    selected = placement.selected_candidate
    if (
        selected.node_id != inventory.node_id
        or selected.inventory_id != inventory.inventory_id
        or selected.inventory_sha256 != inventory_sha256
        or lease.node_id != inventory.node_id
        or lease.inventory_id != inventory.inventory_id
        or lease.inventory_sha256 != inventory_sha256
        or lease.placement_id != placement.placement_id
    ):
        raise ValueError("placement or lease does not bind the supplied inventory")
    if inventory.health != NodeHealth.READY:
        raise ValueError("new allocation requires ready inventory")
    if _ATTESTATION_RANK[inventory.attestation] < _ATTESTATION_RANK[
        capability.constraints.minimum_attestation
    ]:
        raise ValueError("selected inventory does not meet capability attestation")

    required_actions = {CapabilityAction.RESERVE, CapabilityAction.EXECUTE}
    if not required_actions.issubset(set(capability.actions)):
        raise ValueError("capability must grant reserve and execute actions")
    if inventory.node_id not in capability.audience_node_ids:
        raise ValueError("selected node is outside the capability audience")
    if request.workload_kind not in capability.constraints.workload_kinds:
        raise ValueError("request workload is outside capability constraints")
    if request.workload_kind not in inventory.workload_kinds:
        raise ValueError("selected inventory does not support the workload")
    if not any(
        device_uri_matches_prefix(request.device_uri, prefix)
        for prefix in capability.constraints.resource_prefixes
    ):
        raise ValueError("request device is outside capability resource prefixes")
    if placement.transport != lease.transport:
        raise ValueError("placement and lease transports differ")
    if lease.transport not in capability.constraints.transports:
        raise ValueError("selected transport is outside capability constraints")
    if lease.transport not in inventory.transports:
        raise ValueError("selected inventory does not support the transport")

    if not resource_vector_within(
        request.constraints.resources,
        capability.constraints.resources,
    ):
        raise ValueError("request resources exceed capability limits")
    if not resource_vector_within(lease.resources, request.constraints.resources):
        raise ValueError("lease resources exceed the signed request")
    for field in _HOST_RESOURCE_FIELDS:
        if getattr(lease.resources, field) > getattr(
            inventory.resources.allocatable,
            field,
        ):
            raise ValueError(f"lease {field} exceeds signed allocatable inventory")

    gpu_memory = 0
    for gpu_id in lease.gpu_ids:
        gpu = inventory.resources.gpus.get(gpu_id)
        if gpu is None:
            raise ValueError("lease references a GPU absent from signed inventory")
        gpu_memory += gpu.allocatable_memory_bytes
    if gpu_memory < lease.resources.gpu_memory_bytes:
        raise ValueError("lease GPU memory exceeds selected signed GPU inventory")


SchemaModel: TypeAlias = type[StrictContract]

SCHEMA_EXPORTS: dict[str, SchemaModel] = {
    "capability.schema.json": CapabilityDocument,
    "chal-request.schema.json": ChalRequest,
    "chal-response.schema.json": ChalResponse,
    "error.schema.json": ErrorFrame,
    "inventory.schema.json": ResourceInventory,
    "lease.schema.json": LeaseDocument,
    "lifecycle.schema.json": LifecycleEvent,
    "placement.schema.json": PlacementDecision,
    "telemetry.schema.json": TelemetryEvent,
}
SCHEMA_MODELS: dict[str, SchemaModel] = {
    "planetary.chal.capability.v1": CapabilityDocument,
    "planetary.chal.error.v1": ErrorFrame,
    "planetary.chal.request.v1": ChalRequest,
    "planetary.chal.response.v1": ChalResponse,
    "planetary.chal.telemetry.v1": TelemetryEvent,
    "planetary.vsource.inventory.v1": ResourceInventory,
    "planetary.vsource.lease.v1": LeaseDocument,
    "planetary.vsource.lifecycle.v1": LifecycleEvent,
    "planetary.vsource.placement.v1": PlacementDecision,
}


def validate_document(data: dict[str, Any]) -> StrictContract:
    if not isinstance(data, dict):
        raise TypeError("contract document must be a mapping")
    schema = data.get("schema")
    model = SCHEMA_MODELS.get(str(schema))
    if model is None:
        raise ValueError(f"unsupported CHAL/vSource schema: {schema!r}")
    encoded = json.dumps(data, allow_nan=False, separators=(",", ":"))
    return model.model_validate_json(encoded)


__all__ = [
    "AttestationLevel",
    "CapabilityAction",
    "CapabilityDocument",
    "CanonicalTimestamp",
    "ChalRequest",
    "ChalResponse",
    "ContentReference",
    "CpuDescriptor",
    "ErrorCode",
    "ErrorFrame",
    "GpuDescriptor",
    "HostResourceVector",
    "JsonInteger",
    "LeaseDocument",
    "LeaseRevocationReason",
    "LeaseState",
    "LifecycleEvent",
    "LifecycleState",
    "MAX_SAFE_INTEGER",
    "NodeHealth",
    "NodeLabels",
    "NodeResources",
    "PlacementCandidate",
    "PlacementDecision",
    "PlacementResult",
    "RequestConstraints",
    "ResourceInventory",
    "ResponseGrant",
    "ResourceVector",
    "ResponseStatus",
    "SCHEMA_EXPORTS",
    "SCHEMA_MODELS",
    "Signature",
    "TelemetryEvent",
    "TelemetryLabels",
    "TelemetryPhase",
    "TransportKind",
    "TrustZone",
    "WorkloadKind",
    "WorkloadParameters",
    "device_uri_matches_prefix",
    "resource_vector_within",
    "validate_document",
    "validate_lease_bound_lifecycle",
    "validate_lease_bound_response",
    "validate_lifecycle_transition",
    "validate_private_cell_allocation",
]
