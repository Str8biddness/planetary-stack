"""Shared fail-closed primitives for the Unisync private-mesh mTLS gate.

These helpers implement the strict JSON, identifier, filesystem-mode, and
encoding rules every mesh module must apply identically.  They grant no
authority and carry no secrets.
"""

from __future__ import annotations

import base64
import binascii
import ipaddress
import json
import os
import re
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MAX_PRIVATE_FILE_BYTES = 16 * 1024
IDENTIFIER_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{2,127}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SERIAL_HEX_RE = re.compile(r"^[0-9a-f]{2,40}$")
DNS_SAN_RE = re.compile(
    r"^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?)+$"
)
MAX_SANS = 8


class MeshSecurityError(Exception):
    """A mesh enrollment, registry, or job input failed a fail-closed check."""


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MeshSecurityError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise MeshSecurityError(f"non-I-JSON numeric constant: {value}")


def strict_json(raw: str | bytes) -> dict[str, Any]:
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise MeshSecurityError("JSON input must be UTF-8") from exc
    try:
        payload = json.loads(
            raw,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except MeshSecurityError:
        raise
    except (ValueError, TypeError) as exc:
        raise MeshSecurityError("input is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise MeshSecurityError("JSON input must be an object")
    try:
        json.dumps(payload, allow_nan=False, separators=(",", ":"))
    except ValueError as exc:
        raise MeshSecurityError("JSON input contains non-finite numbers") from exc
    return payload


def compact_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, allow_nan=False, sort_keys=True, separators=(",", ":"))


def b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def b64url_decode(value: object, *, expected_bytes: int | None = None, max_bytes: int | None = None) -> bytes:
    if not isinstance(value, str) or "=" in value:
        raise MeshSecurityError("base64url values must be unpadded strings")
    if max_bytes is not None and len(value) > (max_bytes * 4) // 3 + 4:
        raise MeshSecurityError("base64url value exceeds its size bound")
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * ((4 - len(value) % 4) % 4))
    except (binascii.Error, ValueError) as exc:
        raise MeshSecurityError("invalid base64url value") from exc
    if b64url_encode(decoded) != value:
        raise MeshSecurityError("non-canonical base64url value")
    if expected_bytes is not None and len(decoded) != expected_bytes:
        raise MeshSecurityError(f"base64url value must encode {expected_bytes} bytes")
    if max_bytes is not None and len(decoded) > max_bytes:
        raise MeshSecurityError("base64url value exceeds its size bound")
    return decoded


def wire_time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise MeshSecurityError("timestamps must be timezone-aware")
    return value.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_wire_time(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise MeshSecurityError("timestamps must be UTC second precision with a Z suffix")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise MeshSecurityError("timestamps must use YYYY-MM-DDTHH:MM:SSZ") from exc


def require_identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
        raise MeshSecurityError(f"{name} must be a canonical contract identifier")
    return value


def require_sha256(name: str, value: object) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise MeshSecurityError(f"{name} must be a lowercase SHA-256 hex digest")
    return value


def normalize_san(value: object) -> str:
    """Validate one SAN as either a literal IP address or a lowercase DNS name."""

    if not isinstance(value, str) or not value or len(value) > 253:
        raise MeshSecurityError("SAN entries must be nonempty strings of bounded length")
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        lowered = value.lower()
        if not DNS_SAN_RE.fullmatch(lowered):
            raise MeshSecurityError(f"SAN entry is neither an IP address nor a safe DNS name: {value!r}")
        return lowered


def normalize_san_set(values: object) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)) or not values:
        raise MeshSecurityError("at least one SAN is required")
    if len(values) > MAX_SANS:
        raise MeshSecurityError("too many SAN entries")
    normalized = [normalize_san(value) for value in values]
    if len(set(normalized)) != len(normalized):
        raise MeshSecurityError("duplicate SAN entries are not allowed")
    return tuple(sorted(normalized))


def safe_owned_directory(path: Path, *, create: bool = True) -> Path:
    """Require (and optionally create) an owner-controlled mode-0700 directory."""

    path = path.expanduser()
    if path.is_symlink():
        raise MeshSecurityError("mesh state directory must not be a symlink")
    if create:
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise MeshSecurityError("mesh state directory does not exist") from exc
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise MeshSecurityError(
            "mesh state directory must be an owner-controlled mode-0700 directory"
        )
    return path


def write_exclusive_private(path: Path, payload: bytes) -> None:
    """Create a new mode-0600 regular file; never follow or overwrite anything."""

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise MeshSecurityError(f"mesh state file already exists: {path.name}") from exc
    try:
        written = 0
        while written < len(payload):
            count = os.write(descriptor, payload[written:])
            if count <= 0:
                raise OSError("short write while creating mesh state")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def read_private_file(
    path: Path,
    *,
    expected_size: int | None = None,
    max_bytes: int = MAX_PRIVATE_FILE_BYTES,
) -> bytes:
    """Read a regular owner-only mode-0600 file with a hard size bound."""

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError as exc:
        raise MeshSecurityError(f"mesh state file is missing: {path.name}") from exc
    except OSError as exc:
        raise MeshSecurityError(f"mesh state file is unreadable: {path.name}") from exc
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != os.getuid()
        ):
            raise MeshSecurityError("mesh state files must be regular owner-only mode-0600 files")
        if max_bytes <= 0:
            raise MeshSecurityError("private file size bound must be positive")
        if metadata.st_size > max_bytes:
            raise MeshSecurityError("mesh state file exceeds its size bound")
        if expected_size is not None and metadata.st_size != expected_size:
            raise MeshSecurityError(f"mesh state file must contain exactly {expected_size} bytes")
        payload = bytearray()
        while len(payload) <= max_bytes:
            chunk = os.read(descriptor, min(4096, max_bytes + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
        if len(payload) != metadata.st_size:
            raise MeshSecurityError("mesh state file changed while it was read")
        return bytes(payload)
    finally:
        os.close(descriptor)


def fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
