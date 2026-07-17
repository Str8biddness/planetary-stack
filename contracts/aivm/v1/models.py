"""Strict signed AIVM workload and artifact manifest models."""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    WithJsonSchema,
    field_validator,
    model_validator,
)

MAX_SAFE_INTEGER = 9_007_199_254_740_991
MAX_DEVICES = 32
MAX_WRITABLE_PATHS = 32
MAX_ARTIFACTS = 32
MAX_INPUTS = 64
MAX_OUTPUTS = 64
MAX_NETWORK_DESTINATIONS = 32
APPROVED_WRITABLE_ROOTS = ("/work", "/scratch", "/tmp/aivm")
RAW_HOST_DEVICE_PREFIXES = ("/dev/sd", "/dev/hd", "/dev/vd", "/dev/xvd", "/dev/nvme", "/dev/raw")
RAW_HOST_DEVICES = {"/dev/mem", "/dev/kmem", "/dev/port", "/dev/kmsg"}


def _normalize_json_integer(value: Any) -> Any:
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


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


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-I-JSON numeric value is not allowed: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate JSON key is not allowed: {key}")
        seen.add(key)
        result[key] = value
    return result


def _parse_strict_json(raw: str | bytes | bytearray) -> Any:
    try:
        return json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except json.JSONDecodeError as exc:
        raise ValueError("invalid JSON manifest") from exc


def _normalized_posix_path(value: str, *, field_name: str) -> str:
    if not value.startswith("/"):
        raise ValueError(f"{field_name} must be an absolute POSIX path")
    parts = value.split("/")
    if "" in parts[1:] or "." in parts or ".." in parts:
        raise ValueError(f"{field_name} must be normalized and cannot traverse")
    return value


def _is_path_at_or_under(path: str, root: str) -> bool:
    return path == root or path.startswith(root + "/")


JsonInteger = Annotated[int, BeforeValidator(_normalize_json_integer)]
SafeNonNegativeInt = Annotated[JsonInteger, Field(ge=0, le=MAX_SAFE_INTEGER)]
SafePositiveInt = Annotated[JsonInteger, Field(ge=1, le=MAX_SAFE_INTEGER)]
Identifier = Annotated[
    str,
    Field(min_length=3, max_length=128, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._:-]+$"),
]
Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
MediaType = Annotated[
    str,
    Field(min_length=3, max_length=128, pattern=r"^[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*$"),
]
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


class StrictContract(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=False,
        protected_namespaces=(),
        strict=True,
        validate_assignment=True,
    )

    @classmethod
    def model_validate_json_strict(cls, raw: str | bytes | bytearray) -> "StrictContract":
        return cls.model_validate(_parse_strict_json(raw))


class ArtifactKind(StrEnum):
    WORKLOAD_BUNDLE = "workload_bundle"
    INPUT = "input"
    MODEL = "model"
    PARAMETER = "parameter"
    CHECKPOINT = "checkpoint"
    OUTPUT_DECLARATION = "output_declaration"


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


class AIVMArtifactDescriptor(StrictContract):
    document_schema: Literal["planetary.aivm.artifact.v1"] = Field(alias="schema")
    artifact_id: Identifier
    uri: Annotated[
        str,
        Field(
            min_length=12,
            max_length=512,
            pattern=r"^(artifact|kc|aivm)://[A-Za-z0-9][A-Za-z0-9._~:/?#@!$&'()*+,;=%-]*$",
        ),
    ]
    kind: ArtifactKind
    sha256: Sha256
    size_bytes: SafeNonNegativeInt
    media_type: MediaType
    content_encoding: Literal["identity"]
    created_at: CanonicalTimestamp
    mount_path: Annotated[
        str,
        Field(min_length=1, max_length=256, pattern=r"^/[A-Za-z0-9._/-]+$"),
    ]
    readonly: Literal[True]

    @field_validator("mount_path")
    @classmethod
    def reject_path_traversal(cls, value: str) -> str:
        _normalized_posix_path(value, field_name="artifact mount_path")
        if value.startswith(("/proc", "/sys", "/dev", "/run", "/var", "/etc", "/home", "/root", "/tmp")):
            raise ValueError("artifact mount_path cannot target host roots")
        return value


class RuntimeImage(StrictContract):
    image_id: Identifier
    digest: Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]
    media_type: MediaType
    user: Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z_][a-z0-9_-]*$")]
    privileged: Literal[False]
    host_network: Literal[False]
    host_pid: Literal[False]
    host_ipc: Literal[False]
    devices: list[Annotated[str, Field(min_length=1, max_length=128)]]

    @field_validator("devices")
    @classmethod
    def require_bounded_devices(cls, value: list[str]) -> list[str]:
        if len(value) > MAX_DEVICES:
            raise ValueError("devices exceeds bounded collection limit")
        if value != sorted(set(value)):
            raise ValueError("devices must be unique and lexicographically sorted")
        for device in value:
            _normalized_posix_path(device, field_name="runtime devices")
            if not device.startswith("/dev/"):
                raise ValueError("runtime devices must be normalized /dev paths")
            if device in {"*", "all", "/dev", "/dev/kvm"} or device in RAW_HOST_DEVICES:
                raise ValueError("runtime devices must be explicitly bounded")
            if any(device.startswith(prefix) for prefix in RAW_HOST_DEVICE_PREFIXES):
                raise ValueError("runtime devices must not expose raw host block devices")
        return value


class ResourceBudget(StrictContract):
    cpu_millicores: Annotated[JsonInteger, Field(ge=1, le=128_000)]
    memory_bytes: Annotated[JsonInteger, Field(ge=67_108_864, le=MAX_SAFE_INTEGER)]
    time_limit_seconds: Annotated[JsonInteger, Field(ge=1, le=86_400)]
    process_limit: Annotated[JsonInteger, Field(ge=1, le=4096)]
    open_file_limit: Annotated[JsonInteger, Field(ge=0, le=1_048_576)]
    output_bytes: SafeNonNegativeInt
    scratch_bytes: SafeNonNegativeInt
    gpu_count: Annotated[JsonInteger, Field(ge=0, le=64)]
    gpu_memory_bytes: SafeNonNegativeInt

    @model_validator(mode="after")
    def require_bounded_resources(self) -> "ResourceBudget":
        if (self.gpu_count == 0) != (self.gpu_memory_bytes == 0):
            raise ValueError("gpu_count and gpu_memory_bytes must both be zero or positive")
        if self.output_bytes == 0 and self.scratch_bytes == 0:
            raise ValueError("at least one bounded output or scratch byte budget is required")
        return self


class FilesystemPolicy(StrictContract):
    rootfs: Literal["readonly"]
    writable_paths: list[Annotated[str, Field(min_length=1, max_length=256, pattern=r"^/[A-Za-z0-9._/-]+$")]]
    host_mounts: list[Annotated[str, Field(min_length=1, max_length=256)]]

    @model_validator(mode="after")
    def require_safe_filesystem(self) -> "FilesystemPolicy":
        if self.host_mounts:
            raise ValueError("host mounts are not allowed in AIVM v1 admission")
        if len(self.writable_paths) > MAX_WRITABLE_PATHS:
            raise ValueError("writable_paths exceeds bounded collection limit")
        if self.writable_paths != sorted(set(self.writable_paths)):
            raise ValueError("writable_paths must be unique and lexicographically sorted")
        for path in self.writable_paths:
            _normalized_posix_path(path, field_name="writable_paths")
            if not any(_is_path_at_or_under(path, root) for root in APPROVED_WRITABLE_ROOTS):
                raise ValueError("writable_paths must stay inside admitted scratch roots")
        return self


class NetworkDestination(StrictContract):
    protocol: Literal["http", "https", "tcp"]
    host: Annotated[str, Field(min_length=1, max_length=253)]
    port: Annotated[JsonInteger, Field(ge=1, le=65535)]

    @field_validator("host")
    @classmethod
    def reject_wildcard_or_ambiguous_host(cls, value: str) -> str:
        if value in {"*", "0.0.0.0", "::", "::/0", "0.0.0.0/0"}:
            raise ValueError("network host cannot be a wildcard")
        if any(token in value for token in ("/", "\\", " ", "\t", "\n", "\r")):
            raise ValueError("network host must be a host name or IP literal")
        if value.startswith(".") or value.endswith(".") or ".." in value:
            raise ValueError("network host must be normalized")
        return value.lower()

    @property
    def policy_key(self) -> str:
        return f"{self.protocol}://{self.host}:{self.port}"


class NetworkPolicy(StrictContract):
    mode: Literal["deny", "allowlist"]
    allowlist: list[NetworkDestination]

    @model_validator(mode="after")
    def require_bounded_network(self) -> "NetworkPolicy":
        if self.mode == "deny" and self.allowlist:
            raise ValueError("deny network mode cannot carry allowlist entries")
        if self.mode == "allowlist":
            if not self.allowlist:
                raise ValueError("allowlist network mode requires bounded descriptors")
            if len(self.allowlist) > MAX_NETWORK_DESTINATIONS:
                raise ValueError("network allowlist exceeds bounded collection limit")
            keys = [destination.policy_key for destination in self.allowlist]
            if keys != sorted(set(keys)):
                raise ValueError("network allowlist must be unique and lexicographically sorted")
        return self


class AIVMWorkloadManifest(StrictContract):
    document_schema: Literal["planetary.aivm.workload.v1"] = Field(alias="schema")
    manifest_id: Identifier
    account_id: Identifier
    workload_id: Identifier
    issued_at: CanonicalTimestamp
    expires_at: CanonicalTimestamp
    signer_key_id: Identifier
    runtime_image: RuntimeImage
    entrypoint_id: Annotated[
        str,
        Field(min_length=3, max_length=128, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._:-]+$"),
    ]
    resources: ResourceBudget
    filesystem: FilesystemPolicy
    network: NetworkPolicy
    artifacts: list[AIVMArtifactDescriptor]
    inputs: list[Identifier]
    outputs: list[Identifier]
    signature: Signature

    @field_validator("entrypoint_id")
    @classmethod
    def reject_shell_entrypoints(cls, value: str) -> str:
        lowered = value.lower()
        unsafe = ("sh", "bash", "shell", "cmd", "powershell", "eval", "exec", "pickle", "marshal", "bytecode")
        if lowered in unsafe or any(token in value for token in (" ", "/", "\\", ";", "&", "|", "$", "`")):
            raise ValueError("entrypoint_id must be an identifier, not a shell command")
        return value

    @model_validator(mode="after")
    def require_manifest_consistency(self) -> "AIVMWorkloadManifest":
        if self.expires_at <= self.issued_at:
            raise ValueError("expires_at must be after issued_at")
        if (self.expires_at - self.issued_at).total_seconds() > 86_400:
            raise ValueError("AIVM workload TTL cannot exceed one day")
        if len(self.artifacts) > MAX_ARTIFACTS:
            raise ValueError("artifacts exceeds bounded collection limit")
        if len(self.inputs) > MAX_INPUTS:
            raise ValueError("inputs exceeds bounded collection limit")
        if len(self.outputs) > MAX_OUTPUTS:
            raise ValueError("outputs exceeds bounded collection limit")
        if self.signer_key_id != self.signature.key_id:
            raise ValueError("signer_key_id must match signature.key_id")
        artifact_ids = [artifact.artifact_id for artifact in self.artifacts]
        if artifact_ids != sorted(set(artifact_ids)):
            raise ValueError("artifacts must be unique and sorted by artifact_id")
        artifact_uris = [artifact.uri for artifact in self.artifacts]
        if len(artifact_uris) != len(set(artifact_uris)):
            raise ValueError("artifact URIs must be unique")
        artifact_mounts = [artifact.mount_path for artifact in self.artifacts]
        if len(artifact_mounts) != len(set(artifact_mounts)):
            raise ValueError("artifact mount paths must be unique")
        if self.inputs != sorted(set(self.inputs)):
            raise ValueError("inputs must be unique and lexicographically sorted")
        if self.outputs != sorted(set(self.outputs)):
            raise ValueError("outputs must be unique and lexicographically sorted")
        known_ids = set(artifact_ids)
        missing = [artifact_id for artifact_id in self.inputs if artifact_id not in known_ids]
        if missing:
            raise ValueError(f"inputs reference unknown artifacts: {missing}")
        return self
