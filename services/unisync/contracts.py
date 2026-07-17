"""Narrow Unisync transport contracts.

The public contracts bind bytes to a CHAL/vSource transfer context.  Authority
comes only from an injected validator supplied by the controller/scheduler
integration layer.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Literal, Protocol

from .errors import (
    AuthorizationError,
    BackpressureError,
    CancellationError,
    DeadlineExceededError,
    ExpiredContextError,
    InvalidTransferContextError,
    TotalSizeExceededError,
)

HEX_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:@/-]{0,191}$")
MAX_SAFE_INTEGER = (2**53) - 1
MAX_TASK_DESCRIPTOR_BYTES = 64 * 1024
LOCAL_PROCESS_TRANSPORT = "local_process"
LAN_MTLS_TRANSPORT = "lan_mtls"
INTERNET_RELAY_TRANSPORT = "internet_mtls_relay"
VALID_TRANSPORT_IDS = frozenset(
    {
        LOCAL_PROCESS_TRANSPORT,
        LAN_MTLS_TRANSPORT,
        INTERNET_RELAY_TRANSPORT,
    }
)
PeerRole = Literal["source", "destination"]

BANNED_DESCRIPTOR_KEYS = {
    "bytecode",
    "command",
    "credential",
    "eval",
    "executable",
    "marshal",
    "output",
    "pickle",
    "prompt",
    "raw_output",
    "raw_prompt",
    "secret",
    "shell",
    "token",
    "trust_bypass",
}

TASK_DESCRIPTOR_SCHEMA = "planetary.unisync.task_descriptor.v1"
TASK_DESCRIPTOR_FIELDS = frozenset({"schema", "task_id", "artifact_sha256", "byte_length"})


def _require_json_object(value: object, field_name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise InvalidTransferContextError(f"{field_name} must be a JSON object")
    return value


def _require_sha256(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not HEX_SHA256_RE.fullmatch(value):
        raise InvalidTransferContextError(f"{field_name} must be a lowercase SHA-256 hex digest")
    return value


def _require_safe_id(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not SAFE_ID_RE.fullmatch(value):
        raise InvalidTransferContextError(f"{field_name} is missing or contains unsupported characters")
    return value


def _require_transport_id(value: str) -> str:
    _require_safe_id(value, "selected_transport")
    if value not in VALID_TRANSPORT_IDS:
        raise InvalidTransferContextError(f"selected_transport must be one of {sorted(VALID_TRANSPORT_IDS)}")
    return value


def _require_wire_string(payload: dict[str, object], field_name: str) -> str:
    value = payload[field_name]
    if not isinstance(value, str):
        raise InvalidTransferContextError(f"{field_name} must be a string")
    return value


def _require_safe_integer(value: object, field_name: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise InvalidTransferContextError(f"{field_name} must be an integer")
    if value < minimum:
        raise InvalidTransferContextError(f"{field_name} is below the allowed range")
    if value > MAX_SAFE_INTEGER:
        raise InvalidTransferContextError(f"{field_name} exceeds the I-JSON safe integer range")
    return value


def _parse_wire_timestamp(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise InvalidTransferContextError("expires_at must be UTC second precision with a Z suffix")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise InvalidTransferContextError("expires_at must use YYYY-MM-DDTHH:MM:SSZ") from exc
    return parsed


def _format_wire_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise InvalidTransferContextError("expires_at must be timezone-aware")
    return value.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True, slots=True)
class TransferContext:
    """All control-plane fields Unisync must bind before moving bytes."""

    account_id: str
    request_sha256: str
    lease_sha256: str
    fencing_token: int
    selected_transport: str
    source_node_id: str
    destination_node_id: str
    object_sha256: str
    byte_length: int
    expires_at: datetime

    def __post_init__(self) -> None:
        _require_safe_id(self.account_id, "account_id")
        _require_sha256(self.request_sha256, "request_sha256")
        _require_sha256(self.lease_sha256, "lease_sha256")
        _require_transport_id(self.selected_transport)
        _require_safe_id(self.source_node_id, "source_node_id")
        _require_safe_id(self.destination_node_id, "destination_node_id")
        _require_sha256(self.object_sha256, "object_sha256")
        if not isinstance(self.fencing_token, int) or isinstance(self.fencing_token, bool) or self.fencing_token <= 0:
            raise InvalidTransferContextError("fencing_token must be a positive integer")
        if self.fencing_token > MAX_SAFE_INTEGER:
            raise InvalidTransferContextError("fencing_token exceeds the I-JSON safe integer range")
        if not isinstance(self.byte_length, int) or isinstance(self.byte_length, bool) or self.byte_length < 0:
            raise InvalidTransferContextError("byte_length must be a non-negative integer")
        if self.byte_length > MAX_SAFE_INTEGER:
            raise InvalidTransferContextError("byte_length exceeds the I-JSON safe integer range")
        _format_wire_timestamp(self.expires_at)

    @classmethod
    def from_wire(cls, payload: object) -> "TransferContext":
        payload = _require_json_object(payload, "transfer_context")
        required = {
            "account_id",
            "request_sha256",
            "lease_sha256",
            "fencing_token",
            "selected_transport",
            "source_node_id",
            "destination_node_id",
            "object_sha256",
            "byte_length",
            "expires_at",
        }
        if set(payload) != required:
            if any(not isinstance(key, str) for key in payload):
                raise InvalidTransferContextError("transfer_context keys must be strings")
            missing = sorted(required - set(payload))
            extra = sorted(set(payload) - required)
            raise InvalidTransferContextError(f"transfer_context fields differ; missing={missing} extra={extra}")
        return cls(
            account_id=_require_wire_string(payload, "account_id"),
            request_sha256=_require_wire_string(payload, "request_sha256"),
            lease_sha256=_require_wire_string(payload, "lease_sha256"),
            fencing_token=_require_safe_integer(payload["fencing_token"], "fencing_token", minimum=1),
            selected_transport=_require_wire_string(payload, "selected_transport"),
            source_node_id=_require_wire_string(payload, "source_node_id"),
            destination_node_id=_require_wire_string(payload, "destination_node_id"),
            object_sha256=_require_wire_string(payload, "object_sha256"),
            byte_length=_require_safe_integer(payload["byte_length"], "byte_length"),
            expires_at=_parse_wire_timestamp(_require_wire_string(payload, "expires_at")),
        )

    def to_wire(self) -> dict[str, object]:
        return {
            "account_id": self.account_id,
            "request_sha256": self.request_sha256,
            "lease_sha256": self.lease_sha256,
            "fencing_token": self.fencing_token,
            "selected_transport": self.selected_transport,
            "source_node_id": self.source_node_id,
            "destination_node_id": self.destination_node_id,
            "object_sha256": self.object_sha256,
            "byte_length": self.byte_length,
            "expires_at": _format_wire_timestamp(self.expires_at),
        }

    @property
    def transfer_id(self) -> str:
        encoded = json.dumps(self.to_wire(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def receipt_sha256(self, object_sha256: str | None = None) -> str:
        payload = {
            "receipt_type": "planetary.unisync.receipt.v1",
            "transfer_context": self.to_wire(),
            "object_sha256": object_sha256 or self.object_sha256,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def is_expired(self, now: datetime | None = None) -> bool:
        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        return current.astimezone(UTC) >= self.expires_at.astimezone(UTC)

    def validate_for_transport(self, transport_id: str, *, max_total_bytes: int) -> None:
        if self.selected_transport != transport_id:
            raise AuthorizationError(
                f"transfer selected {self.selected_transport!r}, not this transport {transport_id!r}"
            )
        if self.byte_length > max_total_bytes:
            raise TotalSizeExceededError("declared transfer byte_length exceeds configured total cap")
        if self.is_expired():
            raise ExpiredContextError("transfer context expired")


class AuthorizationLeaseValidator(Protocol):
    """Injected CHAL/vSource active-lease validator."""

    def validate_transfer(self, context: TransferContext, peer_identity: "AuthenticatedPeerIdentity | None" = None) -> None:
        """Raise AuthorizationError or a domain-specific exception to deny."""


@dataclass(frozen=True, slots=True)
class AuthenticatedPeerIdentity:
    """TLS-authenticated peer identity bound to enrollment, not to frame input."""

    account_id: str
    node_id: str
    sans: tuple[str, ...]
    certificate_sha256: str
    public_key_sha256: str

    def __post_init__(self) -> None:
        _require_safe_id(self.account_id, "peer account_id")
        _require_safe_id(self.node_id, "peer node_id")
        if not self.sans:
            raise InvalidTransferContextError("peer certificate must have at least one SAN")
        for san in self.sans:
            if not isinstance(san, str) or not san or len(san) > 253:
                raise InvalidTransferContextError("peer SAN is invalid")
        _require_sha256(self.certificate_sha256, "certificate_sha256")
        _require_sha256(self.public_key_sha256, "public_key_sha256")


def require_authorized(
    context: TransferContext,
    *,
    validator: AuthorizationLeaseValidator | None,
    transport_id: str,
    max_total_bytes: int,
    peer_identity: AuthenticatedPeerIdentity | None = None,
    expected_peer_role: PeerRole | None = None,
) -> None:
    context.validate_for_transport(transport_id, max_total_bytes=max_total_bytes)
    if peer_identity is not None:
        if peer_identity.account_id != context.account_id:
            raise AuthorizationError("authenticated peer account does not match transfer context")
        if expected_peer_role == "source" and peer_identity.node_id != context.source_node_id:
            raise AuthorizationError("authenticated peer is not the transfer source node")
        if expected_peer_role == "destination" and peer_identity.node_id != context.destination_node_id:
            raise AuthorizationError("authenticated peer is not the transfer destination node")
    if validator is None:
        raise AuthorizationError("Unisync requires an injected authorization/lease validator")
    try:
        validator.validate_transfer(context, peer_identity)
    except AuthorizationError:
        raise
    except Exception as exc:
        raise AuthorizationError(f"authorization/lease validator rejected transfer: {exc}") from exc


@dataclass(frozen=True, slots=True)
class TaskDescriptorRef:
    """Content-addressed task descriptor reference.

    Descriptor bytes must be validated before transport.  This reference does
    not convey authority; the transfer context and injected validator do that.
    """

    descriptor_sha256: str
    byte_length: int
    media_type: str = "application/vnd.planetary.unisync.task-descriptor+json"

    def __post_init__(self) -> None:
        _require_sha256(self.descriptor_sha256, "descriptor_sha256")
        if not isinstance(self.byte_length, int) or isinstance(self.byte_length, bool) or self.byte_length < 0:
            raise InvalidTransferContextError("descriptor byte_length must be non-negative")
        if self.byte_length > MAX_SAFE_INTEGER:
            raise InvalidTransferContextError("descriptor byte_length exceeds the I-JSON safe integer range")
        if self.media_type != "application/vnd.planetary.unisync.task-descriptor+json":
            raise InvalidTransferContextError("unsupported task descriptor media type")


def validate_task_descriptor_bytes(payload: bytes, *, expected: TaskDescriptorRef) -> None:
    if len(payload) != expected.byte_length:
        raise InvalidTransferContextError("task descriptor length does not match reference")
    if len(payload) > MAX_TASK_DESCRIPTOR_BYTES:
        raise InvalidTransferContextError("task descriptor exceeds bounded size")
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected.descriptor_sha256:
        raise InvalidTransferContextError("task descriptor digest does not match reference")
    try:
        document = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_descriptor_keys,
            parse_constant=_reject_non_finite_descriptor_number,
        )
    except InvalidTransferContextError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidTransferContextError("task descriptor must be UTF-8 JSON") from exc
    _validate_task_descriptor_document(document)


def _reject_duplicate_descriptor_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidTransferContextError(f"duplicate task descriptor key {key!r}")
        result[key] = value
    return result


def _reject_non_finite_descriptor_number(value: str) -> None:
    raise InvalidTransferContextError(f"task descriptor contains non-I-JSON number {value!r}")


def _reject_banned_descriptor_fields(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).lower()
            if lowered in BANNED_DESCRIPTOR_KEYS:
                raise InvalidTransferContextError(f"task descriptor may not carry {lowered!r}")
            _reject_banned_descriptor_fields(child)
    elif isinstance(value, list):
        for child in value:
            _reject_banned_descriptor_fields(child)


def _validate_task_descriptor_document(document: object) -> None:
    if not isinstance(document, dict):
        raise InvalidTransferContextError("task descriptor must be a JSON object")
    _reject_banned_descriptor_fields(document)
    fields = set(document)
    if fields != TASK_DESCRIPTOR_FIELDS:
        missing = sorted(TASK_DESCRIPTOR_FIELDS - fields)
        extra = sorted(fields - TASK_DESCRIPTOR_FIELDS)
        raise InvalidTransferContextError(f"task descriptor schema fields differ; missing={missing} extra={extra}")
    if document["schema"] != TASK_DESCRIPTOR_SCHEMA:
        raise InvalidTransferContextError("task descriptor schema is unsupported")
    _require_safe_id(document["task_id"], "task_id")  # type: ignore[arg-type]
    _require_sha256(document["artifact_sha256"], "artifact_sha256")  # type: ignore[arg-type]
    _require_safe_integer(document["byte_length"], "byte_length")
    _validate_ijson_value(document)


def _validate_ijson_value(value: object) -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int) and not isinstance(value, bool):
        if abs(value) > MAX_SAFE_INTEGER:
            raise InvalidTransferContextError("task descriptor integer exceeds the I-JSON safe range")
        return
    if isinstance(value, float):
        raise InvalidTransferContextError("task descriptor floats are not accepted")
    if isinstance(value, list):
        for child in value:
            _validate_ijson_value(child)
        return
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise InvalidTransferContextError("task descriptor keys must be strings")
            _validate_ijson_value(child)
        return
    raise InvalidTransferContextError("task descriptor contains unsupported JSON value")


@dataclass(frozen=True, slots=True)
class TransferProgress:
    context: TransferContext
    bytes_transferred: int
    total_bytes: int
    chunk_index: int
    resumed_from: int = 0
    complete: bool = False


@dataclass(frozen=True, slots=True)
class TransferResult:
    context: TransferContext
    object_sha256: str
    bytes_transferred: int
    resumed_from: int
    transport_id: str
    verified_receipt_sha256: str = ""


class CancellationToken:
    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def raise_if_cancelled(self) -> None:
        if self._cancelled:
            raise CancellationError("transfer cancelled")


class Deadline:
    def __init__(self, expires_monotonic: float) -> None:
        self._expires_monotonic = expires_monotonic

    @classmethod
    def after(cls, seconds: float) -> "Deadline":
        return cls(time.monotonic() + seconds)

    @property
    def remaining_seconds(self) -> float:
        return self._expires_monotonic - time.monotonic()

    def raise_if_expired(self) -> None:
        if self.remaining_seconds <= 0:
            raise DeadlineExceededError("transfer deadline exceeded")


class BackpressureController:
    """Synchronous bounded in-flight byte accounting."""

    def __init__(self, max_inflight_bytes: int) -> None:
        if max_inflight_bytes <= 0:
            raise ValueError("max_inflight_bytes must be positive")
        self._max_inflight_bytes = max_inflight_bytes
        self._inflight_bytes = 0

    @property
    def inflight_bytes(self) -> int:
        return self._inflight_bytes

    def acquire(self, byte_count: int) -> None:
        if byte_count < 0:
            raise ValueError("byte_count must be non-negative")
        if byte_count > self._max_inflight_bytes:
            raise BackpressureError("chunk exceeds maximum in-flight byte budget")
        if self._inflight_bytes + byte_count > self._max_inflight_bytes:
            raise BackpressureError("receiver backpressure refused additional bytes")
        self._inflight_bytes += byte_count

    def release(self, byte_count: int) -> None:
        self._inflight_bytes = max(0, self._inflight_bytes - byte_count)


ProgressCallback = Callable[[TransferProgress], None]


class ObjectTransport(Protocol):
    transport_id: str

    def upload_object(
        self,
        *,
        context: TransferContext,
        source_root: Path,
        destination_root: Path,
        cancellation: CancellationToken | None = None,
        deadline: Deadline | None = None,
        progress: ProgressCallback | None = None,
    ) -> TransferResult:
        """Move one content-addressed object by bytes only."""


class TaskDescriptorTransport(Protocol):
    transport_id: str

    def upload_task_descriptor(
        self,
        *,
        context: TransferContext,
        descriptor: TaskDescriptorRef,
        source_root: Path,
        destination_root: Path,
        cancellation: CancellationToken | None = None,
        deadline: Deadline | None = None,
        progress: ProgressCallback | None = None,
    ) -> TransferResult:
        """Move a content-addressed task descriptor after descriptor validation."""
