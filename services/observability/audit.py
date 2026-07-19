"""Append-only, owner-only structured audit log.

Design goals for gate F-110 observability:

* **Owner-only on disk.** The log directory is created and enforced at mode
  ``0700`` and each log file at mode ``0600``, owned by the current user.  A
  directory or file that is group/other accessible, a symlink, or owned by a
  different user is refused rather than silently used.
* **Append-only.** Records are written with ``O_APPEND`` one canonical JSON
  object per line.  The writer never truncates or rewrites earlier lines.
* **Canonical.** Each line is RFC 8785 (JCS) canonical JSON, so records are
  byte-stable and safe to hash or diff.
* **Secret-safe.** Every ``detail`` mapping is recursively scrubbed: any key
  matching the secret denylist (token, secret, key, password, authorization,
  ``bundle_base64``) or a raw prompt/user-content key is redacted, and the
  whole mapping is bounded in key count, nesting depth, and value size.  Raw
  prompt/user content is never persisted.

The module deliberately holds no network, subprocess, or third-party state.
"""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from threading import RLock
from typing import Any

import rfc8785

__all__ = [
    "AuditLogError",
    "AuditReader",
    "AuditRecord",
    "AuditWriter",
    "DetailTooLargeError",
    "EventCategory",
    "EventCode",
    "SecretRedactionError",
    "scrub_detail",
    "DENYLIST_KEY_SUBSTRINGS",
]


# --------------------------------------------------------------------------
# Stable event vocabulary
# --------------------------------------------------------------------------


class EventCategory(StrEnum):
    """Coarse event category recorded on every audit record."""

    SECURITY = "security"
    EXECUTION = "execution"
    LIFECYCLE = "lifecycle"
    TRANSPORT = "transport"
    CONTROL = "control"
    AUDIT = "audit"


class EventCode(StrEnum):
    """Stable, machine-readable event codes.

    These string values are a wire/format contract: once shipped they must not
    change meaning, only be appended to.  Callers and log consumers key off the
    exact string, so renaming an existing value is a breaking change.
    """

    # Authorization / security
    AUTH_ACCEPTED = "auth.accepted"
    AUTH_REJECTED = "auth.rejected"
    ADMISSION_REJECTED = "admission.rejected"
    SECRET_REDACTED = "audit.secret_redacted"

    # Job / execution lifecycle
    JOB_ACCEPTED = "job.accepted"
    JOB_COMPLETED = "job.completed"
    JOB_FAILED = "job.failed"
    JOB_CANCELLED = "job.cancelled"

    # Lease lifecycle
    LEASE_GRANTED = "lease.granted"
    LEASE_REVOKED = "lease.revoked"

    # Transport
    TRANSPORT_OBJECT_SENT = "transport.object_sent"
    TRANSPORT_OBJECT_RECEIVED = "transport.object_received"
    TRANSPORT_REPLAY_REJECTED = "transport.replay_rejected"


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class AuditLogError(Exception):
    """Base class for audit-log failures."""


class SecretRedactionError(AuditLogError):
    """Raised in strict mode when a detail field matches the secret denylist."""


class DetailTooLargeError(AuditLogError):
    """Raised when a detail mapping exceeds the configured bounds."""


# --------------------------------------------------------------------------
# Secret / content scrubbing
# --------------------------------------------------------------------------

# Case-insensitive substrings; a key that *contains* any of these is redacted.
# Over-redaction is the safe failure mode for an audit sink.
DENYLIST_KEY_SUBSTRINGS: tuple[str, ...] = (
    "token",
    "secret",
    "key",
    "password",
    "passwd",
    "authorization",
    "bundle_base64",
    "credential",
    "cookie",
    "session",
    # Raw prompt / user-content fields must never be written verbatim.
    "prompt",
    "user_content",
    "usercontent",
    "content",
    "message_text",
    "input_text",
    "output_text",
    "payload",
)

_REDACTED = "[REDACTED]"
_TRUNCATED_SUFFIX = "...[TRUNCATED]"

# Bounds applied to every detail mapping.
_MAX_KEYS = 32
_MAX_DEPTH = 4
_MAX_VALUE_CHARS = 512
_MAX_LIST_ITEMS = 32
_MAX_KEY_CHARS = 128


def _key_is_denied(key: str) -> bool:
    lowered = key.lower()
    return any(bad in lowered for bad in DENYLIST_KEY_SUBSTRINGS)


def scrub_detail(
    detail: Mapping[str, Any],
    *,
    strict: bool = False,
    max_keys: int = _MAX_KEYS,
    max_depth: int = _MAX_DEPTH,
    max_value_chars: int = _MAX_VALUE_CHARS,
) -> dict[str, Any]:
    """Return a bounded, secret-scrubbed copy of ``detail``.

    Any key matching :data:`DENYLIST_KEY_SUBSTRINGS` has its value replaced with
    ``"[REDACTED]"`` (or, when ``strict`` is set, raises
    :class:`SecretRedactionError`).  Long strings are truncated, nested mappings
    and lists are bounded and recursively scrubbed, and unsupported value types
    are coerced to a bounded ``repr``.  The input is never mutated.
    """

    if not isinstance(detail, Mapping):
        raise DetailTooLargeError("detail must be a mapping")
    return _scrub_mapping(
        detail,
        strict=strict,
        max_keys=max_keys,
        max_depth=max_depth,
        max_value_chars=max_value_chars,
        depth=1,
    )


def _scrub_mapping(
    mapping: Mapping[str, Any],
    *,
    strict: bool,
    max_keys: int,
    max_depth: int,
    max_value_chars: int,
    depth: int,
) -> dict[str, Any]:
    if depth > max_depth:
        raise DetailTooLargeError(f"detail nesting exceeds max depth {max_depth}")
    if len(mapping) > max_keys:
        raise DetailTooLargeError(
            f"detail has {len(mapping)} keys; max is {max_keys}"
        )
    out: dict[str, Any] = {}
    for raw_key, value in mapping.items():
        if not isinstance(raw_key, str):
            raise DetailTooLargeError("detail keys must be strings")
        if len(raw_key) > _MAX_KEY_CHARS:
            raise DetailTooLargeError("detail key exceeds max length")
        if _key_is_denied(raw_key):
            if strict:
                raise SecretRedactionError(
                    f"detail key {raw_key!r} matches the secret denylist"
                )
            out[raw_key] = _REDACTED
            continue
        out[raw_key] = _scrub_value(
            value,
            strict=strict,
            max_keys=max_keys,
            max_depth=max_depth,
            max_value_chars=max_value_chars,
            depth=depth,
        )
    return out


def _scrub_value(
    value: Any,
    *,
    strict: bool,
    max_keys: int,
    max_depth: int,
    max_value_chars: int,
    depth: int,
) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        # I-JSON safe integer range; larger values become strings.
        if -(2**53) < value < 2**53:
            return value
        return _bound_str(str(value), max_value_chars)
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        return _bound_str(value, max_value_chars)
    if isinstance(value, Mapping):
        return _scrub_mapping(
            value,
            strict=strict,
            max_keys=max_keys,
            max_depth=max_depth,
            max_value_chars=max_value_chars,
            depth=depth + 1,
        )
    if isinstance(value, (list, tuple)):
        if depth + 1 > max_depth:
            raise DetailTooLargeError("detail nesting exceeds max depth")
        if len(value) > _MAX_LIST_ITEMS:
            raise DetailTooLargeError("detail list exceeds max items")
        return [
            _scrub_value(
                item,
                strict=strict,
                max_keys=max_keys,
                max_depth=max_depth,
                max_value_chars=max_value_chars,
                depth=depth + 1,
            )
            for item in value
        ]
    # Unknown type: coerce to a bounded repr so we never emit opaque objects.
    return _bound_str(repr(value), max_value_chars)


def _bound_str(value: str, max_value_chars: int) -> str:
    if len(value) <= max_value_chars:
        return value
    keep = max(0, max_value_chars - len(_TRUNCATED_SUFFIX))
    return value[:keep] + _TRUNCATED_SUFFIX


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AuditRecord:
    """A single parsed audit record."""

    code: str
    category: str
    ts: str
    detail: dict[str, Any]

    def to_canonical_json(self) -> bytes:
        payload = {
            "code": str(self.code),
            "category": str(self.category),
            "ts": self.ts,
            "detail": self.detail,
        }
        return rfc8785.dumps(payload)


# --------------------------------------------------------------------------
# Owner-only path enforcement
# --------------------------------------------------------------------------


def _enforce_owner_only(path: Path, *, want_dir: bool, expected_mode: int) -> None:
    """Refuse anything not a same-user, non-symlink, owner-only node."""

    st = os.lstat(path)  # lstat: never follow a symlink into an attacker path.
    if stat.S_ISLNK(st.st_mode):
        raise AuditLogError(f"{path} is a symlink; refusing")
    if want_dir and not stat.S_ISDIR(st.st_mode):
        raise AuditLogError(f"{path} is not a directory")
    if not want_dir and not stat.S_ISREG(st.st_mode):
        raise AuditLogError(f"{path} is not a regular file")
    if st.st_uid != os.getuid():
        raise AuditLogError(f"{path} is not owned by the current user")
    perm = stat.S_IMODE(st.st_mode)
    if perm & (stat.S_IRWXG | stat.S_IRWXO):
        raise AuditLogError(
            f"{path} is group/other accessible (mode {perm:#o}); refusing"
        )
    if perm != expected_mode:
        # Tighten to the exact expected mode rather than trust a looser one.
        os.chmod(path, expected_mode)


# --------------------------------------------------------------------------
# Writer
# --------------------------------------------------------------------------

_DIR_MODE = 0o700
_FILE_MODE = 0o600


class AuditWriter:
    """Append-only owner-only canonical-JSON audit writer.

    Parameters
    ----------
    directory:
        Owner-only directory (created at mode ``0700`` if absent) that holds the
        log file.
    filename:
        Log file basename inside ``directory`` (created at mode ``0600``).
    strict_secrets:
        When true, a detail field matching the denylist raises
        :class:`SecretRedactionError` instead of being scrubbed to
        ``"[REDACTED]"``.
    clock:
        Callable returning a timezone-aware :class:`datetime`; defaults to
        ``datetime.now(timezone.utc)``.  Injected for deterministic tests.
    """

    def __init__(
        self,
        directory: str | os.PathLike[str],
        *,
        filename: str = "audit.log",
        strict_secrets: bool = False,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if os.sep in filename or (os.altsep and os.altsep in filename) or filename in (
            "",
            ".",
            "..",
        ):
            raise AuditLogError(f"invalid audit filename {filename!r}")
        self._dir = Path(directory)
        self._path = self._dir / filename
        self._strict = strict_secrets
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = RLock()
        self._prepare()

    @property
    def path(self) -> Path:
        return self._path

    def _prepare(self) -> None:
        # Directory: create owner-only or verify an existing owner-only dir.
        if not self._dir.exists():
            self._dir.mkdir(mode=_DIR_MODE, parents=True, exist_ok=True)
        _enforce_owner_only(self._dir, want_dir=True, expected_mode=_DIR_MODE)

        # File: create with O_CREAT|O_EXCL semantics via os.open, forcing 0600.
        if not self._path.exists():
            fd = os.open(
                self._path,
                os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW,
                _FILE_MODE,
            )
            try:
                os.fchmod(fd, _FILE_MODE)  # defeat a permissive umask.
            finally:
                os.close(fd)
        _enforce_owner_only(self._path, want_dir=False, expected_mode=_FILE_MODE)

    def write(
        self,
        code: EventCode | str,
        category: EventCategory | str,
        detail: Mapping[str, Any] | None = None,
    ) -> AuditRecord:
        """Scrub, canonicalize, and append one audit record; return it."""

        scrubbed = scrub_detail(detail or {}, strict=self._strict)
        now = self._clock()
        if now.tzinfo is None:
            raise AuditLogError("clock must return a timezone-aware datetime")
        ts = (
            now.astimezone(timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
            + "Z"
        )
        record = AuditRecord(
            code=str(code),
            category=str(category),
            ts=ts,
            detail=scrubbed,
        )
        line = record.to_canonical_json() + b"\n"
        if b"\n" in line[:-1]:  # canonical JSON never contains a raw newline.
            raise AuditLogError("record serialized to a multi-line payload")
        with self._lock:
            fd = os.open(
                self._path,
                os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW,
                _FILE_MODE,
            )
            try:
                os.write(fd, line)
                os.fsync(fd)
            finally:
                os.close(fd)
        return record


# --------------------------------------------------------------------------
# Reader
# --------------------------------------------------------------------------


class AuditReader:
    """Reads an audit log back into parsed :class:`AuditRecord` objects."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = Path(path)

    def records(self) -> list[AuditRecord]:
        """Parse every non-empty line; raise on a malformed record."""

        out: list[AuditRecord] = []
        with open(self._path, "r", encoding="utf-8") as handle:
            for lineno, raw in enumerate(handle, start=1):
                line = raw.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise AuditLogError(
                        f"{self._path}:{lineno}: malformed audit line"
                    ) from exc
                if not isinstance(obj, dict):
                    raise AuditLogError(
                        f"{self._path}:{lineno}: audit line is not an object"
                    )
                missing = {"code", "category", "ts", "detail"} - obj.keys()
                if missing:
                    raise AuditLogError(
                        f"{self._path}:{lineno}: missing fields {sorted(missing)}"
                    )
                detail = obj["detail"]
                if not isinstance(detail, dict):
                    raise AuditLogError(
                        f"{self._path}:{lineno}: detail is not an object"
                    )
                out.append(
                    AuditRecord(
                        code=obj["code"],
                        category=obj["category"],
                        ts=obj["ts"],
                        detail=detail,
                    )
                )
        return out
