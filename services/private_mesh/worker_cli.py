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
_JOB_V2_FIELDS = _JOB_FIELDS | {"executor"}
_EXECUTOR_FIELDS = frozenset(
    {
        "profile",
        "artifact_sha256s",
        "image_ref",
        "image_digest",
        "model_artifact_id",
        "document_artifact_id",
        "output_id",
    }
)
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_IMAGE_DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
AIVM_STATE_SUBDIRS = ("state", "artifacts", "results", "authority")
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


def _validated_executor_spec(spec: object) -> dict[str, Any]:
    if not isinstance(spec, dict) or set(spec) != _EXECUTOR_FIELDS:
        raise ValueError("executor spec fields differ from the fixed schema")
    if spec["profile"] != "text-classification.v1":
        raise ValueError("unsupported executor profile")
    digests = spec["artifact_sha256s"]
    if (
        not isinstance(digests, list)
        or not digests
        or len(digests) > 8
        or len(set(digests)) != len(digests)
        or not all(isinstance(item, str) and _SHA256_RE.fullmatch(item) for item in digests)
    ):
        raise ValueError("executor artifact digests must be a bounded unique list")
    if not isinstance(spec["image_ref"], str) or "@sha256:" not in spec["image_ref"]:
        raise ValueError("executor image_ref must be an immutable reference")
    if not isinstance(spec["image_digest"], str) or not _IMAGE_DIGEST_RE.fullmatch(
        spec["image_digest"]
    ):
        raise ValueError("executor image_digest must be a canonical digest")
    if spec["image_ref"].rsplit("@", 1)[1] != spec["image_digest"]:
        raise ValueError("executor image_ref digest must match image_digest")
    for name in ("model_artifact_id", "document_artifact_id", "output_id"):
        value = spec[name]
        if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
            raise ValueError(f"executor {name} must be a canonical identifier")
    return spec


def _stage_mesh_artifacts(state_dir: Path, digests: list[str]) -> Path:
    """Copy digest-verified mesh-inbox objects into the flat executor CAS.

    Objects reach the inbox only through the lease-bound Unisync mTLS
    transfer boundary; staging re-verifies each digest and the executor
    verifies every input a third time before mounting it read-only.
    """

    from services.unisync.mesh_node_cli import INBOX_DIR
    from services.unisync.storage import ContentAddressedStore

    inbox = ContentAddressedStore(state_dir / INBOX_DIR)
    artifact_dir = state_dir / "aivm" / "artifacts"
    artifact_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(artifact_dir, 0o700)
    for digest in digests:
        payload = inbox.read_bytes(digest)
        target = artifact_dir / digest
        try:
            fd = os.open(
                target,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
        except FileExistsError:
            existing = target.read_bytes()
            if hashlib.sha256(existing).hexdigest() != digest:
                raise ValueError("staged artifact store is corrupt") from None
            continue
        try:
            os.write(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)
    return artifact_dir


class RequestBoundManifestVerifier:
    """Bind the AIVM manifest to the signature-verified CHAL request digest.

    The node agent verifies the controller signature over the request before
    execution, and the request pins the exact workload bundle digest; the
    canonical manifest bytes must hash to that digest, chaining manifest
    authenticity to the controller signature without a second signer.
    """

    def __init__(self, expected_bundle_sha256: str) -> None:
        if not _SHA256_RE.fullmatch(expected_bundle_sha256):
            raise ValueError("expected bundle digest must be canonical")
        self._expected = expected_bundle_sha256

    def verify_manifest(self, manifest: Any, payload: bytes) -> Any:
        from aivm.admission import DocumentVerification
        from contracts.aivm.v1 import canonical_document_bytes

        digest = hashlib.sha256(canonical_document_bytes(manifest)).hexdigest()
        if digest != self._expected:
            return DocumentVerification(
                ok=False,
                status="rejected",
                error="manifest does not match the signed request bundle digest",
            )
        return DocumentVerification(
            ok=True, status="verified", key_id=manifest.signer_key_id
        )


def _build_workload_executor(
    *,
    state_dir: Path,
    spec: dict[str, Any],
    account_id: str,
    node_id: str,
    expected_bundle_sha256: str,
) -> Any:
    runtime_packages = (
        Path(__file__).resolve().parents[2] / "apps" / "synthesus" / "runtime" / "packages"
    )
    if str(runtime_packages) not in sys.path:
        sys.path.insert(0, str(runtime_packages))
    from aivm.admission import (
        AIVMAdmissionController,
        AdmissionPolicy,
        HostIsolationCapabilities,
        StaticHostCapabilityProbe,
    )
    from aivm.execution import (
        ExecutorPolicy,
        PersistentExecutionAuthority,
        PodmanExecutor,
        text_classification_entrypoint,
    )
    from aivm.execution.chal_adapter import ChalWorkloadExecutor

    aivm_root = state_dir / "aivm"
    for name in AIVM_STATE_SUBDIRS:
        directory = aivm_root / name
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
    artifact_dir = _stage_mesh_artifacts(state_dir, spec["artifact_sha256s"])
    entrypoint = text_classification_entrypoint(
        model_artifact_id=spec["model_artifact_id"],
        document_artifact_id=spec["document_artifact_id"],
        output_id=spec["output_id"],
    )
    logical_image = f"aivm-text-classify@{spec['image_digest']}"
    authority = PersistentExecutionAuthority(
        aivm_root / "authority", verifier_id=f"verifier:{node_id.split(':', 1)[-1]}"
    )
    executor = PodmanExecutor(
        ExecutorPolicy(
            state_dir=aivm_root / "state",
            artifact_dir=artifact_dir,
            result_dir=aivm_root / "results",
            trusted_images={logical_image: spec["image_ref"]},
            trusted_entrypoints={entrypoint.entrypoint_id: entrypoint},
            account_id=account_id,
            node_id=node_id,
            stdout_limit_bytes=4096,
        ),
        authority_verifier=authority,
    )
    policy = AdmissionPolicy(
        allowed_runtime_images=frozenset({logical_image}),
        allowed_entrypoints=frozenset({entrypoint.entrypoint_id}),
        max_cpu_millicores=4_000,
        max_memory_bytes=4 * 1024 * 1024 * 1024,
        max_time_limit_seconds=900,
        max_process_limit=256,
        max_open_file_limit=4096,
        max_output_bytes=65_536,
        max_scratch_bytes=0,
        max_gpu_count=0,
        max_gpu_memory_bytes=0,
        allowed_devices=frozenset(),
        allowed_network_destinations=frozenset(),
        max_devices=0,
        max_writable_paths=0,
        max_artifacts=8,
        max_inputs=8,
        max_outputs=8,
        max_network_destinations=0,
    )
    probe = StaticHostCapabilityProbe(
        HostIsolationCapabilities(
            os_enforced_backend=True,
            cgroup_control=True,
            namespaces=True,
            no_new_privileges=True,
            container_runtime=True,
            guard_available=True,
        )
    )
    admission = AIVMAdmissionController(
        verifier=RequestBoundManifestVerifier(expected_bundle_sha256),
        policy=policy,
        host_probe=probe,
    )
    return ChalWorkloadExecutor(
        executor=executor,
        authority=authority,
        admission=admission,
        artifact_dir=artifact_dir,
    )


def execute_job(*, state_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    executor_spec: dict[str, Any] | None = None
    if payload.get("schema") == "planetary.private_mesh.ssh_job.v2":
        if set(payload) != _JOB_V2_FIELDS:
            raise ValueError("job fields differ from the fixed physical-smoke schema")
        if payload["executor"] is not None:
            executor_spec = _validated_executor_spec(payload["executor"])
        payload = {
            key: value for key, value in payload.items() if key != "executor"
        }
    elif set(payload) != _JOB_FIELDS:
        raise ValueError("job fields differ from the fixed physical-smoke schema")
    elif payload["schema"] != "planetary.private_mesh.ssh_job.v1":
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
    workload_executor = None
    if executor_spec is not None:
        workload_executor = _build_workload_executor(
            state_dir=state_dir,
            spec=executor_spec,
            account_id=account_id,
            node_id=node_id,
            expected_bundle_sha256=hashlib.sha256(bundle).hexdigest(),
        )
    agent = NodeAgent(
        account_id=account_id,
        node_id=node_id,
        inventory=payload["inventory"],
        verifier=verifier,
        signer=identity.signer,
        clock=clock,
        workload_executor=workload_executor,
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
    import signal
    def _sig_handler(signum: int, frame: Any) -> None:
        sys.exit(128 + signum)
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, _sig_handler)

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
