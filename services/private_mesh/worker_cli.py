"""Node-local CLI for the private-mesh physical smoke gate.

The CLI has no listener and accepts no entrypoint or command field.  SSH is
used only by the coordinator to invoke this fixed program during the physical
smoke test; production object movement remains the Unisync mTLS boundary.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from contracts.chal_vsource.v1.canonical import document_sha256
from contracts.chal_vsource.v1.models import ResourceInventory
from services.private_mesh.node_agent import Ed25519DocumentVerifier, NodeAgent
from services.vsource import Ed25519DocumentSigner, KeyRecord, sign_contract_document


MAX_JOB_BYTES = 2 * 1024 * 1024
MAX_IDENTITY_BYTES = 4 * 1024
KEY_FILE = "node-ed25519.key"
IDENTITY_FILE = "identity.json"
_IDENTIFIER_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{2,127}$")
_IDENTITY_FIELDS = frozenset(
    {"schema", "account_id", "node_id", "key_id", "authenticated_subject_id"}
)
_JOB_FIELDS = frozenset(
    {
        "schema",
        "account_id",
        "node_id",
        "audience",
        "keys",
        "inventory",
        "request",
        "capability",
        "lease",
        "bundle_base64",
    }
)
_KEY_FIELDS = frozenset(
    {
        "key_id",
        "public_key_base64",
        "account_id",
        "audiences",
        "subject_id",
        "node_id",
    }
)


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC).replace(microsecond=0)


class MemoryKeyResolver:
    def __init__(self, records: list[KeyRecord]) -> None:
        self._records: dict[str, KeyRecord] = {}
        for record in records:
            if record.key_id in self._records:
                raise ValueError(f"duplicate enrolled key_id: {record.key_id}")
            self._records[record.key_id] = record

    def resolve_key(self, key_id: str) -> KeyRecord | None:
        return self._records.get(key_id)


@dataclass(frozen=True)
class NodeIdentity:
    account_id: str
    node_id: str
    key_id: str
    authenticated_subject_id: str
    signer: Ed25519DocumentSigner


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"duplicate JSON key: {key}")
        output[key] = value
    return output


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-I-JSON numeric constant: {value}")


def _strict_json(raw: str | bytes) -> dict[str, Any]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="strict")
    payload = json.loads(
        raw,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_constant,
    )
    if not isinstance(payload, dict):
        raise ValueError("JSON input must be an object")
    json.dumps(payload, allow_nan=False, separators=(",", ":"))
    return payload


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: object, *, expected_bytes: int | None = None) -> bytes:
    if not isinstance(value, str) or "=" in value:
        raise ValueError("base64url values must be unpadded strings")
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * ((4 - len(value) % 4) % 4))
    except (binascii.Error, ValueError) as exc:
        raise ValueError("invalid base64url value") from exc
    if _b64url_encode(decoded) != value:
        raise ValueError("non-canonical base64url value")
    if expected_bytes is not None and len(decoded) != expected_bytes:
        raise ValueError(f"base64url value must encode {expected_bytes} bytes")
    return decoded


def _wire_time(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_state_dir(path: Path) -> Path:
    path = path.expanduser()
    if path.exists() and path.is_symlink():
        raise ValueError("state directory must not be a symlink")
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    metadata = path.lstat()
    mode = stat.S_IMODE(metadata.st_mode)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or mode != 0o700
    ):
        raise ValueError(
            "state directory must be an owner-controlled mode-0700 directory"
        )
    return path


def implementation_sha256() -> str:
    """Digest the fixed node boundary used by the physical smoke gate."""

    digest = hashlib.sha256()
    for path in (Path(__file__), Path(__file__).with_name("node_agent.py")):
        payload = path.read_bytes()
        digest.update(path.name.encode("ascii"))
        digest.update(b"\0")
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _write_exclusive(path: Path, payload: bytes, mode: int) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, mode)
    try:
        written = 0
        while written < len(payload):
            count = os.write(descriptor, payload[written:])
            if count <= 0:
                raise OSError("short write while creating node identity")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_private_file(path: Path, *, expected_size: int | None = None) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != os.getuid()
        ):
            raise ValueError("node identity files must be regular mode-0600 files")
        if expected_size is not None and metadata.st_size != expected_size:
            raise ValueError(f"node identity file must contain exactly {expected_size} bytes")
        if metadata.st_size > MAX_IDENTITY_BYTES:
            raise ValueError("node identity file exceeds its size bound")
        payload = bytearray()
        while len(payload) <= MAX_IDENTITY_BYTES:
            chunk = os.read(descriptor, min(4096, MAX_IDENTITY_BYTES + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
        if len(payload) != metadata.st_size:
            raise ValueError("node identity file changed while it was read")
        return bytes(payload)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _load_or_create_identity(
    state_dir: Path,
    *,
    account_id: str,
    node_id: str,
    authenticated_subject_id: str | None,
    create: bool = True,
) -> NodeIdentity:
    directory = _safe_state_dir(state_dir)
    safe_node = hashlib.sha256(node_id.encode("utf-8")).hexdigest()[:20]
    expected_prefix = {
        "schema": "planetary.private_mesh.node_identity.v1",
        "account_id": account_id,
        "node_id": node_id,
        "key_id": f"key:private-mesh-node:{safe_node}",
    }
    key_path = directory / KEY_FILE
    identity_path = directory / IDENTITY_FILE
    if key_path.exists() != identity_path.exists():
        raise ValueError("node identity state is incomplete")
    if not key_path.exists():
        if not create:
            raise ValueError("node identity has not been enrolled")
        if not authenticated_subject_id:
            raise ValueError("enrollment requires an authenticated subject")
        expected = {
            **expected_prefix,
            "authenticated_subject_id": authenticated_subject_id,
        }
        private_key = Ed25519PrivateKey.generate()
        key_bytes = private_key.private_bytes(
            Encoding.Raw,
            PrivateFormat.Raw,
            NoEncryption(),
        )
        _write_exclusive(key_path, key_bytes, 0o600)
        _write_exclusive(
            identity_path,
            (json.dumps(expected, sort_keys=True, separators=(",", ":")) + "\n").encode(),
            0o600,
        )
        _fsync_directory(directory)
    identity_bytes = _read_private_file(identity_path)
    key_bytes = _read_private_file(key_path, expected_size=32)
    stored = _strict_json(identity_bytes)
    if set(stored) != _IDENTITY_FIELDS:
        raise ValueError("node identity has unexpected fields")
    if any(stored.get(key) != value for key, value in expected_prefix.items()):
        raise ValueError("node identity does not match the requested account and node")
    stored_subject = stored.get("authenticated_subject_id")
    if not isinstance(stored_subject, str) or not stored_subject:
        raise ValueError("node identity has no authenticated subject binding")
    if authenticated_subject_id is not None and stored_subject != authenticated_subject_id:
        raise ValueError("node identity subject binding cannot be changed")
    private_key = Ed25519PrivateKey.from_private_bytes(key_bytes)
    return NodeIdentity(
        account_id=account_id,
        node_id=node_id,
        key_id=expected_prefix["key_id"],
        authenticated_subject_id=stored_subject,
        signer=Ed25519DocumentSigner(expected_prefix["key_id"], private_key),
    )


def _host_memory_bytes() -> int:
    try:
        return int(os.sysconf("SC_PHYS_PAGES")) * int(os.sysconf("SC_PAGE_SIZE"))
    except (OSError, ValueError):
        return 512 * 1024 * 1024


def _architecture() -> str:
    value = platform.machine().lower()
    if value in {"x86_64", "amd64"}:
        return "x86_64"
    if value in {"aarch64", "arm64"}:
        return "arm64"
    if value == "riscv64":
        return "riscv64"
    raise ValueError(f"unsupported contract architecture: {value!r}")


def _require_identifier(name: str, value: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{name} must be a canonical contract identifier")


def enroll_node(
    *,
    state_dir: Path,
    account_id: str,
    node_id: str,
    authenticated_subject_id: str,
) -> dict[str, Any]:
    _require_identifier("account_id", account_id)
    _require_identifier("node_id", node_id)
    _require_identifier("authenticated_subject_id", authenticated_subject_id)
    architecture = _architecture()
    cpu_count = max(1, os.cpu_count() or 1)
    if cpu_count > 4096:
        raise ValueError("logical CPU count exceeds the frozen contract bound")
    directory = _safe_state_dir(state_dir)
    disk_free = shutil.disk_usage(directory).free
    memory_bytes = _host_memory_bytes()
    identity = _load_or_create_identity(
        state_dir,
        account_id=account_id,
        node_id=node_id,
        authenticated_subject_id=authenticated_subject_id,
    )
    now = SystemClock().now()
    public_key = identity.signer.private_key.public_key().public_bytes(
        Encoding.Raw,
        PublicFormat.Raw,
    )
    fingerprint = hashlib.sha256(public_key).hexdigest()
    payload = {
        "schema": "planetary.vsource.inventory.v1",
        "inventory_id": f"inventory:{hashlib.sha256(node_id.encode()).hexdigest()[:24]}",
        "node_id": node_id,
        "account_id": account_id,
        "trust_zone": "personal_cell",
        "public_key_fingerprint": fingerprint,
        "attestation": "unverified",
        "observed_at": _wire_time(now),
        "ttl_seconds": 300,
        "health": "ready",
        "resources": {
            "allocatable": {
                "cpu_millicores": cpu_count * 1_000,
                "memory_bytes": memory_bytes,
                "storage_bytes": disk_free,
                "ingress_bps": 0,
                "egress_bps": 0,
            },
            "cpu": {
                "architecture": architecture,
                "logical_cores": cpu_count,
                "features": [],
            },
            "gpus": {},
        },
        "transports": ["local_process"],
        "workload_kinds": ["evaluation"],
        "labels": {
            "power_class": "consumer",
            "thermal_policy": "balanced",
            "network_scope": "trusted_lan",
        },
    }
    inventory = sign_contract_document(ResourceInventory, payload, identity.signer)
    return {
        "schema": "planetary.private_mesh.enrollment.v1",
        "hostname": platform.node(),
        "implementation_sha256": implementation_sha256(),
        "architecture": architecture,
        "logical_cores": cpu_count,
        "account_id": account_id,
        "node_id": node_id,
        "key_id": identity.key_id,
        "public_key_base64": _b64url_encode(public_key),
        "public_key_fingerprint": fingerprint,
        "inventory_sha256": document_sha256(inventory),
        "inventory": inventory.model_dump(mode="json", by_alias=True),
    }


def _key_record(payload: object) -> KeyRecord:
    if not isinstance(payload, dict) or set(payload) != _KEY_FIELDS:
        raise ValueError("key enrollment record has unexpected fields")
    audiences = payload["audiences"]
    if (
        not isinstance(audiences, list)
        or not audiences
        or any(not isinstance(value, str) for value in audiences)
        or audiences != sorted(set(audiences))
    ):
        raise ValueError("key audiences must be a non-empty canonical string array")
    for optional in ("subject_id", "node_id"):
        if payload[optional] is not None and not isinstance(payload[optional], str):
            raise ValueError(f"{optional} must be a string or null")
    for required in ("key_id", "account_id"):
        if not isinstance(payload[required], str):
            raise ValueError(f"{required} must be a string")
    return KeyRecord(
        key_id=payload["key_id"],
        public_key=_b64url_decode(payload["public_key_base64"], expected_bytes=32),
        account_id=payload["account_id"],
        audiences=tuple(audiences),
        subject_id=payload["subject_id"],
        node_id=payload["node_id"],
    )


def execute_job(*, state_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    if set(payload) != _JOB_FIELDS:
        raise ValueError("job fields differ from the fixed physical-smoke schema")
    if payload["schema"] != "planetary.private_mesh.ssh_job.v1":
        raise ValueError("unsupported private-mesh physical-smoke job schema")
    account_id = payload["account_id"]
    node_id = payload["node_id"]
    audience = payload["audience"]
    if not all(isinstance(value, str) for value in (account_id, node_id, audience)):
        raise ValueError("job identity fields must be strings")
    if audience != node_id:
        raise ValueError("job audience must exactly equal the enrolled node")
    identity = _load_or_create_identity(
        state_dir,
        account_id=account_id,
        node_id=node_id,
        authenticated_subject_id=None,
        create=False,
    )
    keys = payload["keys"]
    if not isinstance(keys, list) or not keys:
        raise ValueError("job requires enrolled public keys")
    resolver = MemoryKeyResolver([_key_record(item) for item in keys])
    local_record = resolver.resolve_key(identity.key_id)
    local_public = identity.signer.private_key.public_key().public_bytes(
        Encoding.Raw,
        PublicFormat.Raw,
    )
    if (
        local_record is None
        or local_record.account_id != account_id
        or local_record.node_id != node_id
        or local_record.public_key_bytes() != local_public
    ):
        raise ValueError("job enrollment does not bind the node-local private key")
    bundle = _b64url_decode(payload["bundle_base64"])
    clock = SystemClock()
    verifier = Ed25519DocumentVerifier(resolver, clock, audience)
    agent = NodeAgent(
        account_id=account_id,
        node_id=node_id,
        inventory=payload["inventory"],
        verifier=verifier,
        signer=identity.signer,
        clock=clock,
    )
    admission = agent.admit_lease(
        payload["lease"],
        payload["request"],
        payload["capability"],
        authenticated_subject_id=identity.authenticated_subject_id,
    )
    response: dict[str, Any] = {
        "schema": "planetary.private_mesh.ssh_result.v1",
        "hostname": platform.node(),
        "node_id": node_id,
        "admission": {
            "status": admission.status.value,
            "accepted": admission.accepted,
            "reason": admission.reason,
            "lease_id": admission.lease_id,
            "lease_sha256": admission.lease_sha256,
            "request_sha256": admission.request_sha256,
            "lifecycle_event": (
                admission.lifecycle_event.model_dump(mode="json", by_alias=True)
                if admission.lifecycle_event is not None
                else None
            ),
            "error": (
                admission.error.model_dump(mode="json", by_alias=True)
                if admission.error is not None
                else None
            ),
        },
        "execution": None,
    }
    if not admission.accepted:
        return response
    assert admission.lease_id is not None
    assert admission.lease_sha256 is not None
    lease = payload["lease"]
    if not isinstance(lease, dict) or isinstance(lease.get("fencing_token"), bool):
        raise ValueError("job lease must expose an integer fencing token")
    execution = agent.execute(
        lease_id=admission.lease_id,
        lease_sha256=admission.lease_sha256,
        fencing_token=lease["fencing_token"],
        bundle=bundle,
    )
    response["execution"] = {
        "status": execution.status.value,
        "accepted": execution.accepted,
        "reason": execution.reason,
        "response": (
            execution.response.model_dump(mode="json", by_alias=True)
            if execution.response is not None
            else None
        ),
        "lifecycle_events": [
            event.model_dump(mode="json", by_alias=True)
            for event in execution.lifecycle_events
        ],
        "report_base64": (
            _b64url_encode(execution.report) if execution.report is not None else None
        ),
        "error": (
            execution.error.model_dump(mode="json", by_alias=True)
            if execution.error is not None
            else None
        ),
    }
    return response


def _read_stdin_job() -> dict[str, Any]:
    raw = sys.stdin.buffer.read(MAX_JOB_BYTES + 1)
    if len(raw) > MAX_JOB_BYTES:
        raise ValueError("physical-smoke job exceeds the input limit")
    return _strict_json(raw)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    enroll = subparsers.add_parser("enroll")
    enroll.add_argument("--state-dir", type=Path, required=True)
    enroll.add_argument("--account-id", required=True)
    enroll.add_argument("--node-id", required=True)
    enroll.add_argument("--authenticated-subject-id", required=True)
    execute = subparsers.add_parser("execute")
    execute.add_argument("--state-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "enroll":
            result = enroll_node(
                state_dir=arguments.state_dir,
                account_id=arguments.account_id,
                node_id=arguments.node_id,
                authenticated_subject_id=arguments.authenticated_subject_id,
            )
        else:
            result = execute_job(
                state_dir=arguments.state_dir,
                payload=_read_stdin_job(),
            )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "schema": "planetary.private_mesh.cli_error.v1",
                    "ok": False,
                    "error": type(exc).__name__,
                    "message": str(exc)[:256],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
