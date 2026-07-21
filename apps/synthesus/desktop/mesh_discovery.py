"""Read-only discovery of enrolled mesh nodes, for the permissions UI.

Device rows used to be typed by hand: the owner had to reproduce a string like
`node:private-mesh:dakin-ms-7c95` exactly, and a typo silently produced a row
that matched nothing. The mesh already knows which nodes are enrolled, so this
module reads that registry and offers the nodes as *candidates*.

Two properties matter more than convenience, and both are structural here:

  Discovery never grants anything. This module has no write path — it cannot
  reach `DevicePolicyStore` at all. A discovered node is a suggestion; adding
  it still goes through `add_device`, which creates the row with every
  capability OFF. Being enrolled in the mesh means a node can speak mTLS to
  its peers. It does not mean the owner agreed to run work on it. Enrollment
  is not consent.

  A registry we cannot read produces an empty list and a reason, never a
  device. The failure mode to avoid is a settings screen that invents a
  plausible machine name; an owner who then grants it a capability has been
  told a lie by their own product. So every field below is copied out of a
  validated `MeshEnrollmentRecord`, and there is no fallback that fabricates.

Reading is genuinely read-only: `EnrollmentRegistry.__init__` CREATES the
registry file when it is absent, which is the wrong side effect for a desktop
window that merely renders a list. So the file is parsed directly and each
record is validated through `MeshEnrollmentRecord.from_wire`, which is the same
fail-closed shape check the mesh itself applies.
"""

from __future__ import annotations

import os
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Default location of the enrolled-node registry as the desktop expects to find
# it. Overridable by environment, and injectable for tests, because no test may
# depend on a real mesh existing on the machine running it.
MESH_REGISTRY_PATH = "~/.synthesus/mesh/enrollments.json"
MESH_REGISTRY_ENV = "SYNTHESUS_MESH_REGISTRY"

# Fallback bound, used only if the mesh module cannot be imported to supply its
# own. Reading a multi-megabyte file into the controller is refused either way.
_FALLBACK_MAX_REGISTRY_BYTES = 1024 * 1024

# Reasons the candidate list is empty. These are stable machine strings; the UI
# renders its own sentence for each, and an unrecognised one is shown verbatim
# rather than swallowed.
REASON_OK = None
REASON_NO_MESH_MODULE = "mesh_module_unavailable"
REASON_MISSING = "registry_missing"
REASON_UNREADABLE = "registry_unreadable"
REASON_EMPTY = "registry_empty"
REASON_ALL_KNOWN = "all_enrolled_nodes_already_listed"


def registry_path_from_environment(environ: Any = None) -> Path:
    """Configured registry path. Never validated here — absence is not an error."""

    source = os.environ if environ is None else environ
    raw = str(source.get(MESH_REGISTRY_ENV, "") or "").strip() or MESH_REGISTRY_PATH
    return Path(raw).expanduser()


def _short_fingerprint(digest: str) -> str:
    """Display form of a certificate fingerprint: first 16 hex characters.

    The full value is returned alongside it. This is for the row header, not
    for any comparison — nothing in the product ever compares the short form.
    """
    return digest[:16]


def _suggested_display_name(node_id: str) -> str:
    """Last segment of the node id, verbatim.

    Deliberately not prettified. `dakin-ms-7c95` is what the mesh calls the
    machine; turning it into "Dakin MS 7C95" would be this module inventing
    words about the owner's hardware. The field is a suggestion the owner can
    replace, so it should carry no guesses.
    """
    segment = node_id.rsplit(":", 1)[-1].strip()
    return (segment or node_id)[:128]


def _read_registry_bytes(path: Path, max_bytes: int) -> bytes:
    """Owner-only bounded read. Raises OSError/ValueError; callers degrade."""

    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("registry path is not a regular file")
    if info.st_uid != os.geteuid():
        raise ValueError("registry file is not owned by this user")
    if info.st_size > max_bytes:
        raise ValueError("registry file exceeds its size bound")
    return path.read_bytes()


def discover_enrolled_nodes(
    registry_path: Path | str | None = None,
    *,
    known_device_ids: Any = (),
    now: datetime | None = None,
) -> dict[str, Any]:
    """Enrolled nodes that are not already device rows.

    Returns `{"candidates": [...], "reason": str | None, "registry_path": str}`.
    Never raises for a missing, empty, or malformed registry: the permissions
    window must still open when the mesh state is absent, and an owner with no
    mesh is a normal state, not an error.
    """

    path = Path(registry_path).expanduser() if registry_path else registry_path_from_environment()
    known = {str(value) for value in known_device_ids}
    current = (now or datetime.now(UTC)).astimezone(UTC)

    try:
        from services.unisync.mesh_authority import (  # noqa: PLC0415
            MAX_REGISTRY_BYTES,
            REGISTRY_SCHEMA,
            MeshEnrollmentRecord,
        )
        from services.unisync.mesh_common import parse_wire_time  # noqa: PLC0415
    except Exception as exc:
        # The desktop can be installed without the mesh services on the path.
        # That is a "cannot tell you" state, not a "there are none" state, and
        # it is reported as such.
        return _empty(path, REASON_NO_MESH_MODULE, str(exc))

    try:
        raw = _read_registry_bytes(path, MAX_REGISTRY_BYTES or _FALLBACK_MAX_REGISTRY_BYTES)
    except FileNotFoundError:
        return _empty(path, REASON_MISSING, "no enrollment registry at this path")
    except (OSError, ValueError) as exc:
        return _empty(path, REASON_UNREADABLE, str(exc))

    try:
        import json  # noqa: PLC0415

        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or payload.get("schema") != REGISTRY_SCHEMA:
            raise ValueError("enrollment registry schema is unsupported")
        records = payload.get("records")
        if not isinstance(records, list):
            raise ValueError("enrollment registry records must be a list")
        # from_wire is the mesh's own fail-closed validator. One bad record
        # invalidates the whole read: a registry we only partly understand is a
        # registry we do not understand.
        parsed = [MeshEnrollmentRecord.from_wire(item) for item in records]
    except Exception as exc:
        return _empty(path, REASON_UNREADABLE, str(exc))

    if not parsed:
        return _empty(path, REASON_EMPTY, "the mesh registry has no enrolled nodes")

    candidates: list[dict[str, Any]] = []
    for record in sorted(parsed, key=lambda item: (item.node_id, item.account_id)):
        if record.node_id in known:
            continue
        try:
            not_after = parse_wire_time(record.not_after)
        except Exception:
            # A record whose expiry we cannot parse is never presented as
            # available; it is presented as unusable, with the raw value shown.
            expired = True
        else:
            expired = current >= not_after
        revoked = record.status != "active"
        candidates.append(
            {
                "node_id": record.node_id,
                "account_id": record.account_id,
                "suggested_display_name": _suggested_display_name(record.node_id),
                "certificate_sha256": record.certificate_sha256,
                "certificate_sha256_short": _short_fingerprint(record.certificate_sha256),
                "sans": list(record.sans),
                "not_after": record.not_after,
                "expired": expired,
                "revoked": revoked,
                "revocation_reason": record.revocation_reason,
                # One field the UI can act on without re-deriving the rule.
                # An expired or revoked enrollment is still LISTED — hiding it
                # would leave the owner wondering where their node went — but
                # it is listed as unavailable.
                "available": not expired and not revoked,
            }
        )

    if not candidates:
        return _empty(path, REASON_ALL_KNOWN, "every enrolled node already has a device row")
    return {
        "candidates": candidates,
        "reason": REASON_OK,
        "detail": None,
        "registry_path": str(path),
    }


def _empty(path: Path, reason: str, detail: str) -> dict[str, Any]:
    return {
        "candidates": [],
        "reason": reason,
        "detail": detail,
        "registry_path": str(path),
    }
