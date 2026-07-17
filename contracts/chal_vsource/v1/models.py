"""Canonical CHAL/vSource v1 protocol models.

The models are intentionally strict and content-reference based. They freeze
the private-cell control-plane boundary before any remote scheduler or node
agent is implemented. Arbitrary code, shell commands, pickle, marshal, and raw
user content are not valid protocol fields.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


Identifier = Annotated[
    str,
    Field(min_length=3, max_length=128, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._:-]+$"),
]
Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Uri = Annotated[
    str,
    Field(
        min_length=8,
        max_length=512,
        pattern=r"^(artifact|aivm|chal|kc|mem)://[A-Za-z0-9][A-Za-z0-9._~:/?#@!$&'()*+,;=%-]*$",
    ),
]
_RESOURCE_FIELDS = (
    "cpu_millicores",
    "memory_bytes",
    "gpu_count",
    "gpu_memory_bytes",
    "storage_bytes",
    "ingress_bps",
    "egress_bps",
)


class StrictContract(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=False,
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


class Signature(StrictContract):
    algorithm: Literal["ed25519"] = "ed25519"
    key_id: Identifier
    value: Annotated[
        str,
        Field(min_length=86, max_length=86, pattern=r"^[A-Za-z0-9_-]{86}$"),
    ]


class ContentReference(StrictContract):
    uri: Uri
    sha256: Sha256
    size_bytes: Annotated[int, Field(ge=0)]
    media_type: Annotated[str, Field(min_length=3, max_length=128)]
    classification: Literal["public", "private", "restricted"] = "private"


class ResourceVector(StrictContract):
    cpu_millicores: Annotated[int, Field(ge=0)] = 0
    memory_bytes: Annotated[int, Field(ge=0)] = 0
    gpu_count: Annotated[int, Field(ge=0)] = 0
    gpu_memory_bytes: Annotated[int, Field(ge=0)] = 0
    storage_bytes: Annotated[int, Field(ge=0)] = 0
    ingress_bps: Annotated[int, Field(ge=0)] = 0
    egress_bps: Annotated[int, Field(ge=0)] = 0


class RequestConstraints(StrictContract):
    resources: ResourceVector
    latency_budget_ms: Annotated[int, Field(ge=1, le=3_600_000)]
    deadline: datetime
    grounding_required: bool = False
    template_leakage_allowed: Literal[False] = False
    network_access: Literal["none", "artifact_plane_only"] = "none"
    checkpoint_required: bool = False


class WorkloadParameters(StrictContract):
    """Allowlisted scalar tuning knobs; inputs remain content references."""

    batch_size: Annotated[int, Field(ge=1, le=65_536)] | None = None
    max_tokens: Annotated[int, Field(ge=1, le=1_000_000)] | None = None
    temperature: Annotated[float, Field(ge=0.0, le=2.0)] | None = None
    top_k: Annotated[int, Field(ge=1, le=1_000_000)] | None = None
    seed: Annotated[int, Field(ge=0, le=9_223_372_036_854_775_807)] | None = None
    precision: Literal["auto", "fp32", "fp16", "bf16", "int8", "int4"] | None = (
        None
    )
    checkpoint_interval_seconds: Annotated[int, Field(ge=1, le=86_400)] | None = (
        None
    )
    replica_count: Annotated[int, Field(ge=1, le=1_024)] | None = None
    chunk_size: Annotated[int, Field(ge=1, le=1_000_000)] | None = None
    width: Annotated[int, Field(ge=1, le=32_768)] | None = None
    height: Annotated[int, Field(ge=1, le=32_768)] | None = None
    steps: Annotated[int, Field(ge=1, le=1_000_000)] | None = None
    deterministic: bool = False


class ChalRequest(StrictContract):
    schema_id: Literal["planetary.chal.request.v1"] = Field(
        "planetary.chal.request.v1",
        alias="schema",
    )
    request_id: Identifier
    trace_id: Identifier
    parent_request_id: Identifier | None = None
    issued_at: datetime
    expires_at: datetime
    idempotency_key: Identifier
    account_id: Identifier
    capability_id: Identifier
    device_uri: Annotated[str, Field(pattern=r"^chal://[A-Za-z0-9._~:/-]+$")]
    workload_kind: WorkloadKind
    workload_manifest: ContentReference
    inputs: list[ContentReference] = Field(default_factory=list, max_length=128)
    parameters: WorkloadParameters = Field(default_factory=WorkloadParameters)
    constraints: RequestConstraints

    @model_validator(mode="after")
    def validate_time_window(self) -> "ChalRequest":
        if self.expires_at <= self.issued_at:
            raise ValueError("request expires_at must be after issued_at")
        if self.expires_at - self.issued_at > timedelta(hours=1):
            raise ValueError("request lifetime cannot exceed one hour")
        if self.constraints.deadline <= self.issued_at:
            raise ValueError("request deadline must be after issued_at")
        if self.constraints.deadline > self.expires_at:
            raise ValueError("request deadline cannot exceed request expiry")
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
        "planetary.chal.error.v1",
        alias="schema",
    )
    error_id: Identifier
    request_id: Identifier
    trace_id: Identifier
    code: ErrorCode
    retryable: bool
    safe_detail: Annotated[str, Field(min_length=1, max_length=512)]
    retry_after_ms: Annotated[int, Field(ge=1, le=3_600_000)] | None = None
    device_uri: Annotated[
        str,
        Field(pattern=r"^chal://[A-Za-z0-9._~:/-]+$"),
    ] | None = None

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
        "planetary.chal.response.v1",
        alias="schema",
    )
    response_id: Identifier
    request_id: Identifier
    trace_id: Identifier
    device_uri: Annotated[str, Field(pattern=r"^chal://[A-Za-z0-9._~:/-]+$")]
    status: ResponseStatus
    completed_at: datetime
    outputs: list[ContentReference] = Field(default_factory=list, max_length=128)
    telemetry_ids: list[Identifier] = Field(default_factory=list, max_length=256)
    error: ErrorFrame | None = None

    @model_validator(mode="after")
    def require_error_for_non_success(self) -> "ChalResponse":
        if self.status == ResponseStatus.SUCCEEDED and self.error is not None:
            raise ValueError("successful responses cannot contain an error")
        if self.status != ResponseStatus.SUCCEEDED and self.error is None:
            raise ValueError("non-success responses require an error frame")
        return self


class CapabilityConstraints(StrictContract):
    resources: ResourceVector
    workload_kinds: set[WorkloadKind] = Field(min_length=1)
    transports: set[TransportKind] = Field(min_length=1)
    resource_patterns: list[Annotated[str, Field(pattern=r"^chal://")]] = Field(
        min_length=1,
        max_length=128,
    )


class CapabilityDocument(StrictContract):
    schema_id: Literal["planetary.chal.capability.v1"] = Field(
        "planetary.chal.capability.v1",
        alias="schema",
    )
    capability_id: Identifier
    issuer_id: Identifier
    subject_id: Identifier
    account_id: Identifier
    audience_node_ids: set[Identifier] = Field(min_length=1, max_length=128)
    actions: set[CapabilityAction] = Field(min_length=1)
    constraints: CapabilityConstraints
    not_before: datetime
    expires_at: datetime
    nonce: Annotated[
        str,
        Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"),
    ]
    revocation_epoch: Annotated[int, Field(ge=0)]
    delegable: Literal[False] = False
    signature: Signature

    @model_validator(mode="after")
    def validate_time_window(self) -> "CapabilityDocument":
        if self.expires_at <= self.not_before:
            raise ValueError("capability expires_at must be after not_before")
        if self.expires_at - self.not_before > timedelta(hours=1):
            raise ValueError("capability lifetime cannot exceed one hour")
        return self


class CpuDescriptor(StrictContract):
    architecture: Literal["x86_64", "aarch64", "riscv64"]
    logical_cores: Annotated[int, Field(ge=1, le=4096)]
    features: set[Annotated[str, Field(max_length=64)]] = Field(default_factory=set)


class GpuDescriptor(StrictContract):
    gpu_id: Identifier
    vendor: Annotated[str, Field(min_length=1, max_length=64)]
    model: Annotated[str, Field(min_length=1, max_length=128)]
    memory_bytes: Annotated[int, Field(ge=1)]
    compute_apis: set[Literal["cuda", "rocm", "vulkan", "metal", "opencl"]]


class NodeResources(StrictContract):
    capacity: ResourceVector
    allocatable: ResourceVector
    cpu: CpuDescriptor
    gpus: list[GpuDescriptor] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def allocatable_does_not_exceed_capacity(self) -> "NodeResources":
        for name in _RESOURCE_FIELDS:
            if getattr(self.allocatable, name) > getattr(self.capacity, name):
                raise ValueError(f"allocatable {name} exceeds capacity")
        if self.allocatable.gpu_count > len(self.gpus):
            raise ValueError("allocatable gpu_count exceeds described GPUs")
        return self


class NodeHealth(StrEnum):
    READY = "ready"
    DRAINING = "draining"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class ResourceInventory(StrictContract):
    schema_id: Literal["planetary.vsource.inventory.v1"] = Field(
        "planetary.vsource.inventory.v1",
        alias="schema",
    )
    inventory_id: Identifier
    node_id: Identifier
    account_id: Identifier
    trust_zone: Literal["personal_cell"] = "personal_cell"
    public_key_fingerprint: Sha256
    attestation: Literal["unverified", "software_verified", "hardware_verified"]
    observed_at: datetime
    expires_at: datetime
    health: NodeHealth
    resources: NodeResources
    transports: set[TransportKind] = Field(min_length=1)
    workload_kinds: set[WorkloadKind] = Field(min_length=1)
    labels: dict[str, Annotated[str, Field(max_length=128)]] = Field(
        default_factory=dict,
        max_length=64,
    )
    signature: Signature

    @model_validator(mode="after")
    def validate_freshness(self) -> "ResourceInventory":
        if self.expires_at <= self.observed_at:
            raise ValueError("inventory expires_at must be after observed_at")
        if self.expires_at - self.observed_at > timedelta(minutes=5):
            raise ValueError("inventory lifetime cannot exceed five minutes")
        return self


class LeaseState(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    RELEASED = "released"
    EXPIRED = "expired"
    REVOKED = "revoked"


class LeaseDocument(StrictContract):
    schema_id: Literal["planetary.vsource.lease.v1"] = Field(
        "planetary.vsource.lease.v1",
        alias="schema",
    )
    lease_id: Identifier
    placement_id: Identifier
    request_id: Identifier
    capability_id: Identifier
    node_id: Identifier
    account_id: Identifier
    resources: ResourceVector
    state: LeaseState
    not_before: datetime
    expires_at: datetime
    fencing_token: Annotated[int, Field(ge=1)]
    renewable: bool = False
    renewal_count: Annotated[int, Field(ge=0)] = 0
    max_renewals: Annotated[int, Field(ge=0, le=1024)] = 0
    revocation_reason: Annotated[str, Field(max_length=256)] | None = None
    signature: Signature

    @model_validator(mode="after")
    def validate_lease(self) -> "LeaseDocument":
        if self.expires_at <= self.not_before:
            raise ValueError("lease expires_at must be after not_before")
        if self.expires_at - self.not_before > timedelta(minutes=15):
            raise ValueError("lease lifetime cannot exceed fifteen minutes")
        if self.renewal_count > self.max_renewals:
            raise ValueError("lease renewal_count exceeds max_renewals")
        if not self.renewable and self.max_renewals:
            raise ValueError("non-renewable leases must set max_renewals to zero")
        if self.state == LeaseState.REVOKED and not self.revocation_reason:
            raise ValueError("revoked leases require revocation_reason")
        return self


class PlacementCandidate(StrictContract):
    node_id: Identifier
    eligible: bool
    score: Annotated[float, Field(ge=0.0, le=1.0)]
    reasons: list[Annotated[str, Field(max_length=128)]] = Field(
        default_factory=list,
        max_length=32,
    )


class PlacementResult(StrEnum):
    PLACED = "placed"
    UNPLACED = "unplaced"


class PlacementDecision(StrictContract):
    schema_id: Literal["planetary.vsource.placement.v1"] = Field(
        "planetary.vsource.placement.v1",
        alias="schema",
    )
    placement_id: Identifier
    request_id: Identifier
    trace_id: Identifier
    account_id: Identifier
    scheduler_id: Identifier
    scheduler_scope: Literal["same_account_private_cell"] = (
        "same_account_private_cell"
    )
    decided_at: datetime
    result: PlacementResult
    selected_node_id: Identifier | None = None
    candidates: list[PlacementCandidate] = Field(min_length=1, max_length=256)
    policy_version: Identifier
    rejection_error: ErrorFrame | None = None

    @model_validator(mode="after")
    def validate_decision(self) -> "PlacementDecision":
        eligible_nodes = {
            candidate.node_id for candidate in self.candidates if candidate.eligible
        }
        if self.result == PlacementResult.PLACED:
            if self.selected_node_id not in eligible_nodes:
                raise ValueError("placed decision must select an eligible candidate")
            if self.rejection_error is not None:
                raise ValueError("placed decision cannot contain rejection_error")
        else:
            if self.selected_node_id is not None:
                raise ValueError("unplaced decision cannot select a node")
            if self.rejection_error is None:
                raise ValueError("unplaced decision requires rejection_error")
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
    LifecycleState.LOST: {
        LifecycleState.STAGED,
        LifecycleState.FAILED,
        LifecycleState.CANCELLED,
    },
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
        "planetary.vsource.lifecycle.v1",
        alias="schema",
    )
    event_id: Identifier
    sequence: Annotated[int, Field(ge=0)]
    workload_id: Identifier
    request_id: Identifier
    trace_id: Identifier
    placement_id: Identifier
    lease_id: Identifier
    node_id: Identifier
    account_id: Identifier
    previous_state: LifecycleState | None = None
    state: LifecycleState
    occurred_at: datetime
    checkpoint: ContentReference | None = None
    outputs: list[ContentReference] = Field(default_factory=list, max_length=128)
    error: ErrorFrame | None = None

    @model_validator(mode="after")
    def validate_event(self) -> "LifecycleEvent":
        validate_lifecycle_transition(self.previous_state, self.state)
        if self.state == LifecycleState.COMPLETED and not self.outputs:
            raise ValueError("completed lifecycle event requires output references")
        if self.state in {LifecycleState.FAILED, LifecycleState.LOST} and not self.error:
            raise ValueError(f"{self.state} lifecycle event requires an error")
        if self.state == LifecycleState.CHECKPOINTED and not self.checkpoint:
            raise ValueError("checkpointed lifecycle event requires checkpoint reference")
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

    backend: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    route: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    region: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    accelerator: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    degradation_reason: Annotated[str, Field(min_length=1, max_length=128)] | None = (
        None
    )
    verification: Literal["unverified", "verified", "rejected"] | None = None


class TelemetryEvent(StrictContract):
    schema_id: Literal["planetary.chal.telemetry.v1"] = Field(
        "planetary.chal.telemetry.v1",
        alias="schema",
    )
    telemetry_id: Identifier
    request_id: Identifier
    trace_id: Identifier
    workload_id: Identifier | None = None
    node_id: Identifier | None = None
    recorded_at: datetime
    phase: TelemetryPhase
    status: Literal["ok", "degraded", "failed"]
    measurement_kind: Literal["measured", "estimated"]
    latency_ms: Annotated[float, Field(ge=0.0)] = 0.0
    queue_ms: Annotated[float, Field(ge=0.0)] = 0.0
    usage: ResourceVector = Field(default_factory=ResourceVector)
    input_sha256: Sha256 | None = None
    output_sha256: Sha256 | None = None
    contains_user_content: Literal[False] = False
    labels: TelemetryLabels = Field(default_factory=TelemetryLabels)
    error_id: Identifier | None = None

    @model_validator(mode="after")
    def validate_status_error(self) -> "TelemetryEvent":
        if self.status == "failed" and not self.error_id:
            raise ValueError("failed telemetry requires error_id")
        return self


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
    str(model.model_fields["schema_id"].default): model
    for model in SCHEMA_EXPORTS.values()
}


def validate_document(data: dict[str, Any]) -> StrictContract:
    if not isinstance(data, dict):
        raise TypeError("contract document must be a mapping")
    schema = data.get("schema")
    model = SCHEMA_MODELS.get(str(schema))
    if model is None:
        raise ValueError(f"unsupported CHAL/vSource schema: {schema!r}")
    return model.model_validate(data)


__all__ = [
    "CapabilityAction",
    "CapabilityDocument",
    "ChalRequest",
    "ChalResponse",
    "ContentReference",
    "CpuDescriptor",
    "ErrorCode",
    "ErrorFrame",
    "GpuDescriptor",
    "LeaseDocument",
    "LeaseState",
    "LifecycleEvent",
    "LifecycleState",
    "NodeHealth",
    "NodeResources",
    "PlacementCandidate",
    "PlacementDecision",
    "PlacementResult",
    "RequestConstraints",
    "ResourceInventory",
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
    "validate_document",
    "validate_lifecycle_transition",
]
