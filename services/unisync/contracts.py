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
from typing import Callable, Protocol

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


def _require_sha256(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not HEX_SHA256_RE.fullmatch(value):
        raise InvalidTransferContextError(f"{field_name} must be a lowercase SHA-256 hex digest")
    return value


def _require_safe_id(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not SAFE_ID_RE.fullmatch(value):
        raise InvalidTransferContextError(f"{field_name} is missing or contains unsupported characters")
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
        _require_safe_id(self.selected_transport, "selected_transport")
        _require_safe_id(self.source_node_id, "source_node_id")
        _require_safe_id(self.destination_node_id, "destination_node_id")
        _require_sha256(self.object_sha256, "object_sha256")
        if not isinstance(self.fencing_token, int) or self.fencing_token <= 0:
            raise InvalidTransferContextError("fencing_token must be a positive integer")
        if not isinstance(self.byte_length, int) or self.byte_length < 0:
            raise InvalidTransferContextError("byte_length must be a non-negative integer")
        _format_wire_timestamp(self.expires_at)

    @classmethod
    def from_wire(cls, payload: dict[str, object]) -> "TransferContext":
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
            missing = sorted(required - set(payload))
            extra = sorted(set(payload) - required)
            raise InvalidTransferContextError(f"transfer_context fields differ; missing={missing} extra={extra}")
        return cls(
            account_id=str(payload["account_id"]),
            request_sha256=str(payload["request_sha256"]),
            lease_sha256=str(payload["lease_sha256"]),
            fencing_token=int(payload["fencing_token"]),
            selected_transport=str(payload["selected_transport"]),
            source_node_id=str(payload["source_node_id"]),
            destination_node_id=str(payload["destination_node_id"]),
            object_sha256=str(payload["object_sha256"]),
            byte_length=int(payload["byte_length"]),
            expires_at=_parse_wire_timestamp(str(payload["expires_at"])),
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

    def validate_transfer(self, context: TransferContext) -> None:
        """Raise AuthorizationError or a domain-specific exception to deny."""


def require_authorized(
    context: TransferContext,
    *,
    validator: AuthorizationLeaseValidator | None,
    transport_id: str,
    max_total_bytes: int,
) -> None:
    context.validate_for_transport(transport_id, max_total_bytes=max_total_bytes)
    if validator is None:
        raise AuthorizationError("Unisync requires an injected authorization/lease validator")
    try:
        validator.validate_transfer(context)
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
        if self.byte_length < 0:
            raise InvalidTransferContextError("descriptor byte_length must be non-negative")
        if self.media_type != "application/vnd.planetary.unisync.task-descriptor+json":
            raise InvalidTransferContextError("unsupported task descriptor media type")


def validate_task_descriptor_bytes(payload: bytes, *, expected: TaskDescriptorRef) -> None:
    if len(payload) != expected.byte_length:
        raise InvalidTransferContextError("task descriptor length does not match reference")
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected.descriptor_sha256:
        raise InvalidTransferContextError("task descriptor digest does not match reference")
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidTransferContextError("task descriptor must be UTF-8 JSON") from exc
    _reject_banned_descriptor_fields(document)


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
