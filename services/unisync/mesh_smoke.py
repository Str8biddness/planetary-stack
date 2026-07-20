"""Two-node real-TCP Unisync mTLS smoke coordinator.

The coordinator provisions node-local TLS enrollment over a pinned
administrative carrier, allocates a scheduler-signed ``lan_mtls`` vSource
lease through the durable local control plane, and then drives one bounded
content-addressed object from the source node to the destination node over an
actual private-LAN TCP mTLS socket.

Carrier discipline is explicit and auditable:

- The pinned SSH (or local subprocess rehearsal) carrier is bootstrap control
  only: it starts fixed node CLIs; the source node generates the opaque object
  inside its local content-addressed store.
- The workload bytes reach the destination node exclusively through the
  Unisync ``lan_mtls`` socket; the destination never receives them over SSH.

The harness is configuration-driven; it embeds no addresses, aliases,
usernames, or machine paths.  It emits an exclusive mode-0600 JSON transcript
plus persistent registry and SQLite state.  It never transmits or records any
private key.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shlex
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from contracts.chal_vsource.v1.canonical import document_sha256
from contracts.chal_vsource.v1.models import (
    CapabilityDocument,
    ChalRequest,
    LeaseRevocationReason,
    LeaseState,
    ResourceInventory,
)
from services.private_mesh.ssh_smoke import NodeTarget, SshCarrier
from services.vsource import (
    Ed25519DocumentSigner,
    KeyRecord,
    LocalVSourceControlPlane,
    VSourceStatus,
    sign_contract_document,
)

from .contracts import TransferContext
from .mesh_common import (
    MeshSecurityError,
    b64url_decode,
    b64url_encode,
    normalize_san,
    normalize_san_set,
    require_identifier,
    strict_json,
    wire_time,
)
from .mesh_authority import (
    EnrollmentRegistry,
    IssuedCertificate,
    MeshCertificateAuthority,
    MeshEnrollmentRecord,
)
from .mesh_lease import SignedLeaseValidator, parse_signed_lease
from .mesh_node_cli import (
    ENROLL_INIT_SCHEMA,
    ENROLL_INSTALL_RESULT_SCHEMA,
    ENROLL_INSTALL_SCHEMA,
    MAX_OBJECT_BYTES,
    PREPARE_ARTIFACT_SCHEMA,
    PREPARE_RESULT_SCHEMA,
    PREPARE_SCHEMA,
    SEND_RESULT_SCHEMA,
    SEND_SCHEMA,
    SERVE_READY_SCHEMA,
    SERVE_RESULT_SCHEMA,
    SERVE_SCHEMA,
    implementation_sha256,
)
from .tls import _literal_allowed_address

CONFIG_SCHEMA = "planetary.unisync.mesh_mtls_smoke_config.v1"
EVIDENCE_SCHEMA = "planetary.unisync.mesh_mtls_smoke_evidence.v1"
ERROR_SCHEMA = "planetary.unisync.mesh_mtls_smoke_error.v1"
NODE_CLI_MODULE = "services.unisync.mesh_node_cli"
MAX_CONFIG_BYTES = 256 * 1024
MAX_CARRIER_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_OUTPUT_LINE_BYTES = 1024 * 1024

_CONFIG_FIELDS = frozenset(
    {
        "schema",
        "account_id",
        "subject_id",
        "carrier",
        "known_hosts",
        "identity_file",
        "timeout_seconds",
        "object_bytes",
        "lease_ttl_seconds",
        "registry_dir",
        "state_db",
        "output",
        "source",
        "destination",
        "prepare_mode",
    }
)
_PREPARE_MODES = frozenset({"random", "workload_model", "workload_document", "existing"})
_NODE_FIELDS = frozenset(
    {
        "node_id",
        "python",
        "repo",
        "state_dir",
        "tls_sans",
        "ssh_alias",
        "ssh_host_fingerprint",
    }
)
_DESTINATION_FIELDS = _NODE_FIELDS | {
    "bind_address",
    "port",
    "server_hostname",
    "declared_vpn_cidrs",
}
_ENROLL_INIT_FIELDS = frozenset(
    {
        "schema",
        "hostname",
        "account_id",
        "node_id",
        "sans",
        "csr_pem",
        "tls_public_key_sha256",
        "contract",
        "inventory",
        "inventory_sha256",
        "implementation_sha256",
    }
)
_CONTRACT_FIELDS = frozenset(
    {"key_id", "public_key_base64", "public_key_fingerprint", "account_id", "node_id"}
)


@dataclass(frozen=True)
class MeshNodeConfig:
    node_id: str
    python: str
    repo: str
    state_dir: str
    tls_sans: tuple[str, ...]
    ssh_alias: str | None
    ssh_host_fingerprint: str | None


@dataclass(frozen=True)
class MeshSmokeConfig:
    account_id: str
    subject_id: str
    carrier: str
    known_hosts: Path | None
    identity_file: Path | None
    timeout_seconds: int
    object_bytes: int
    lease_ttl_seconds: int
    registry_dir: Path
    state_db: Path
    output: Path
    source: MeshNodeConfig
    destination: MeshNodeConfig
    bind_address: str
    port: int
    server_hostname: str
    declared_vpn_cidrs: tuple[str, ...]
    prepare_mode: str = "random"
    existing_object_sha256: str = ""


def _require_bounded_int(value: object, name: str, low: int, high: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise MeshSecurityError(f"{name} must be an integer between {low} and {high}")
    return value


def _require_path_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.startswith("/") or ".." in Path(value).parts:
        raise MeshSecurityError(f"{name} must be a safe absolute path")
    return value


def _parse_node(payload: object, *, label: str, fields: frozenset[str], carrier: str) -> tuple[MeshNodeConfig, dict[str, Any]]:
    if not isinstance(payload, dict) or set(payload) != fields:
        raise MeshSecurityError(f"{label} node configuration has unexpected fields")
    node_id = require_identifier(f"{label}.node_id", payload["node_id"])
    sans = normalize_san_set(payload["tls_sans"])
    alias = payload["ssh_alias"]
    fingerprint = payload["ssh_host_fingerprint"]
    if carrier == "ssh":
        if not isinstance(alias, str) or not isinstance(fingerprint, str):
            raise MeshSecurityError(f"{label} requires ssh_alias and ssh_host_fingerprint")
    else:
        if alias is not None or fingerprint is not None:
            raise MeshSecurityError(f"{label} must not declare SSH settings for a local run")
    node = MeshNodeConfig(
        node_id=node_id,
        python=_require_path_string(payload["python"], f"{label}.python"),
        repo=_require_path_string(payload["repo"], f"{label}.repo"),
        state_dir=_require_path_string(payload["state_dir"], f"{label}.state_dir"),
        tls_sans=sans,
        ssh_alias=alias,
        ssh_host_fingerprint=fingerprint,
    )
    return node, dict(payload)


def parse_config(payload: dict[str, Any]) -> MeshSmokeConfig:
    if set(payload) != _CONFIG_FIELDS:
        raise MeshSecurityError("mesh smoke configuration has unexpected fields")
    if payload["schema"] != CONFIG_SCHEMA:
        raise MeshSecurityError("mesh smoke configuration schema is unsupported")
    carrier = payload["carrier"]
    if carrier not in {"ssh", "local"}:
        raise MeshSecurityError("carrier must be 'ssh' or 'local'")
    account_id = require_identifier("account_id", payload["account_id"])
    subject_id = require_identifier("subject_id", payload["subject_id"])
    source, _ = _parse_node(
        payload["source"], label="source", fields=_NODE_FIELDS, carrier=carrier
    )
    destination, destination_raw = _parse_node(
        payload["destination"],
        label="destination",
        fields=_DESTINATION_FIELDS,
        carrier=carrier,
    )
    if source.node_id == destination.node_id:
        raise MeshSecurityError("source and destination node IDs must differ")
    if source.state_dir == destination.state_dir:
        raise MeshSecurityError("source and destination state directories must differ")
    vpn_cidrs = destination_raw["declared_vpn_cidrs"]
    if not isinstance(vpn_cidrs, list) or any(not isinstance(v, str) for v in vpn_cidrs):
        raise MeshSecurityError("declared_vpn_cidrs must be a list of strings")
    bind_address = destination_raw["bind_address"]
    if not isinstance(bind_address, str):
        raise MeshSecurityError("bind_address must be a string")
    _literal_allowed_address(bind_address, declared_vpn_cidrs=tuple(vpn_cidrs))
    if normalize_san(bind_address) not in destination.tls_sans:
        raise MeshSecurityError("bind_address must be one of the destination TLS SANs")
    server_hostname = normalize_san(destination_raw["server_hostname"])
    if server_hostname not in destination.tls_sans:
        raise MeshSecurityError("server_hostname must be one of the destination TLS SANs")
    known_hosts = payload["known_hosts"]
    identity_file = payload["identity_file"]
    if carrier == "ssh" and not isinstance(known_hosts, str):
        raise MeshSecurityError("ssh carrier requires known_hosts")
    if known_hosts is not None and not isinstance(known_hosts, str):
        raise MeshSecurityError("known_hosts must be a path string or null")
    if identity_file is not None and not isinstance(identity_file, str):
        raise MeshSecurityError("identity_file must be a path string or null")
    return MeshSmokeConfig(
        account_id=account_id,
        subject_id=subject_id,
        carrier=carrier,
        known_hosts=Path(known_hosts) if known_hosts is not None else None,
        identity_file=Path(identity_file) if identity_file is not None else None,
        timeout_seconds=_require_bounded_int(payload["timeout_seconds"], "timeout_seconds", 5, 300),
        object_bytes=_require_bounded_int(payload["object_bytes"], "object_bytes", 1, MAX_OBJECT_BYTES),
        lease_ttl_seconds=_require_bounded_int(payload["lease_ttl_seconds"], "lease_ttl_seconds", 30, 900),
        registry_dir=Path(_require_path_string(payload["registry_dir"], "registry_dir")),
        state_db=Path(_require_path_string(payload["state_db"], "state_db")),
        output=Path(_require_path_string(payload["output"], "output")),
        source=source,
        destination=destination,
        bind_address=bind_address,
        port=_require_bounded_int(destination_raw["port"], "destination.port", 0, 65535),
        server_hostname=server_hostname,
        declared_vpn_cidrs=tuple(vpn_cidrs),
        prepare_mode=_require_prepare_mode(payload["prepare_mode"]),
    )


def _require_prepare_mode(value: object) -> str:
    if value not in _PREPARE_MODES:
        raise MeshSecurityError("prepare_mode must name a supported mechanism")
    return value


class ServeHandle:
    """Bounded line-oriented view of one running serve subprocess."""

    def __init__(self, process: subprocess.Popen[bytes], *, timeout_seconds: float) -> None:
        self._process = process
        self._timeout = timeout_seconds
        self._lines: Queue[bytes] = Queue()
        self._stderr = bytearray()
        self._overflow = False
        self._threads = [
            Thread(target=self._drain_stdout, daemon=True),
            Thread(target=self._drain_stderr, daemon=True),
        ]
        for thread in self._threads:
            thread.start()

    def _drain_stdout(self) -> None:
        assert self._process.stdout is not None
        total = 0
        pending = bytearray()
        while True:
            chunk = os.read(self._process.stdout.fileno(), 65_536)
            if not chunk:
                break
            total += len(chunk)
            pending.extend(chunk)
            if total > MAX_CARRIER_OUTPUT_BYTES or len(pending) > MAX_OUTPUT_LINE_BYTES:
                self._overflow = True
                self._process.kill()
                return
            while b"\n" in pending:
                line, _, remainder = pending.partition(b"\n")
                if len(line) > MAX_OUTPUT_LINE_BYTES:
                    self._overflow = True
                    self._process.kill()
                    return
                self._lines.put(bytes(line))
                pending = bytearray(remainder)
        if pending:
            self._lines.put(bytes(pending))

    def _drain_stderr(self) -> None:
        assert self._process.stderr is not None
        while True:
            chunk = os.read(self._process.stderr.fileno(), 65_536)
            if not chunk:
                return
            if len(self._stderr) + len(chunk) > MAX_CARRIER_OUTPUT_BYTES:
                self._overflow = True
                self._process.kill()
                return
            self._stderr.extend(chunk)

    def _next_line(self, timeout: float) -> dict[str, Any]:
        try:
            line = self._lines.get(timeout=timeout)
        except Empty as exc:
            self.kill()
            raise MeshSecurityError("serve process produced no output in time") from exc
        if self._overflow:
            raise MeshSecurityError("serve process exceeded its output bound")
        return strict_json(line)

    def ready(self) -> dict[str, Any]:
        return self._next_line(self._timeout)

    def result(self) -> dict[str, Any]:
        try:
            returncode = self._process.wait(timeout=self._timeout + 10)
        except subprocess.TimeoutExpired as exc:
            self.kill()
            raise MeshSecurityError("serve process exceeded its time limit") from exc
        for thread in self._threads:
            thread.join(timeout=5)
        if self._overflow:
            raise MeshSecurityError("serve process exceeded its output bound")
        payload = self._next_line(1.0)
        if returncode != 0:
            message = payload.get("message", "serve command failed")
            raise MeshSecurityError(f"serve process failed: {message}")
        return payload

    def kill(self) -> None:
        try:
            self._process.kill()
            self._process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass


class SshMeshCarrier(SshCarrier):
    """Pinned OpenSSH bootstrap carrier for the fixed mesh node CLI."""

    kind = "ssh_stdio"

    def _target(self, node: MeshNodeConfig) -> NodeTarget:
        assert node.ssh_alias is not None and node.ssh_host_fingerprint is not None
        return NodeTarget.parse(
            "|".join(
                [
                    node.node_id,
                    node.ssh_alias,
                    node.ssh_host_fingerprint,
                    node.python,
                    node.repo,
                    node.state_dir,
                ]
            )
        )

    def verify_node(self, node: MeshNodeConfig) -> dict[str, Any]:
        return self.verify_pinned_host(self._target(node))

    def _mesh_command(self, node: MeshNodeConfig, arguments: list[str]) -> str:
        fixed = [node.python, "-m", NODE_CLI_MODULE, *arguments]
        return (
            f"cd {shlex.quote(node.repo)} && "
            f"env PYTHONPATH=. {' '.join(shlex.quote(value) for value in fixed)}"
        )

    def run_cli(
        self,
        node: MeshNodeConfig,
        arguments: list[str],
        *,
        stdin: bytes | None = None,
    ) -> dict[str, Any]:
        argv = [*self._base_argv(self._target(node).ssh_alias), self._mesh_command(node, arguments)]
        returncode, stdout, _stderr = self._run_bounded_process(argv, stdin=stdin)
        payload = strict_json(stdout.strip()) if stdout.strip() else {}
        if returncode != 0:
            message = payload.get("message", "mesh node command failed")
            raise MeshSecurityError(f"node {node.node_id} rejected the command: {message}")
        return payload

    def start_serve(
        self,
        node: MeshNodeConfig,
        arguments: list[str],
        *,
        stdin: bytes,
        timeout_seconds: float,
    ) -> ServeHandle:
        argv = [*self._base_argv(self._target(node).ssh_alias), self._mesh_command(node, arguments)]
        with tempfile.TemporaryFile() as input_file:
            input_file.write(stdin)
            input_file.seek(0)
            process = subprocess.Popen(
                argv,
                stdin=input_file,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        return ServeHandle(process, timeout_seconds=timeout_seconds)


class LocalMeshCarrier:
    """Single-host rehearsal carrier: local argv subprocesses, shell=False."""

    kind = "local_process"

    def __init__(self, *, timeout_seconds: int) -> None:
        self.timeout_seconds = timeout_seconds

    def _argv(self, node: MeshNodeConfig, arguments: list[str]) -> list[str]:
        python = Path(node.python)
        repo = Path(node.repo)
        if not python.is_file() or not os.access(python, os.X_OK):
            raise MeshSecurityError("node python interpreter is not executable")
        if not (repo / "services" / "unisync" / "mesh_node_cli.py").is_file():
            raise MeshSecurityError("node repo does not contain the mesh node CLI")
        return [str(python), "-m", NODE_CLI_MODULE, *arguments]

    def _env(self, node: MeshNodeConfig) -> dict[str, str]:
        return {**os.environ, "PYTHONPATH": node.repo}

    def verify_node(self, node: MeshNodeConfig) -> dict[str, Any]:
        self._argv(node, ["--help"])
        return {"carrier": self.kind, "node_id": node.node_id, "repo": node.repo}

    def run_cli(
        self,
        node: MeshNodeConfig,
        arguments: list[str],
        *,
        stdin: bytes | None = None,
    ) -> dict[str, Any]:
        completed = subprocess.run(
            self._argv(node, arguments),
            input=stdin if stdin is not None else b"",
            capture_output=True,
            cwd=node.repo,
            env=self._env(node),
            timeout=self.timeout_seconds + 10,
        )
        if len(completed.stdout) > MAX_CARRIER_OUTPUT_BYTES:
            raise MeshSecurityError("node command exceeded its output bound")
        payload = strict_json(completed.stdout.strip()) if completed.stdout.strip() else {}
        if completed.returncode != 0:
            message = payload.get("message", "mesh node command failed")
            raise MeshSecurityError(f"node {node.node_id} rejected the command: {message}")
        return payload

    def start_serve(
        self,
        node: MeshNodeConfig,
        arguments: list[str],
        *,
        stdin: bytes,
        timeout_seconds: float,
    ) -> ServeHandle:
        with tempfile.TemporaryFile() as input_file:
            input_file.write(stdin)
            input_file.seek(0)
            process = subprocess.Popen(
                self._argv(node, arguments),
                stdin=input_file,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=node.repo,
                env=self._env(node),
            )
        return ServeHandle(process, timeout_seconds=timeout_seconds)


class HybridMeshCarrier:
    """Desktop-as-destination carrier: the local node (``ssh_alias is None``)
    runs its mesh CLI as a local subprocess while the remote node (``ssh_alias``
    set) runs over the pinned SSH carrier.

    This is the physical result-return topology: the coordinating desktop runs
    the lease-bound mTLS ``serve`` receiver locally and a remote worker runs
    ``send`` over the LAN. Exactly one node is local and one is remote, so the
    transfer spans two distinct physical machines with a single pinned SSH
    endpoint (the worker); the destination is this host itself.
    """

    kind = "hybrid_local_ssh"

    def __init__(
        self, *, known_hosts: Path, identity_file: Path | None, timeout_seconds: int
    ) -> None:
        self._local = LocalMeshCarrier(timeout_seconds=timeout_seconds)
        self._ssh = SshMeshCarrier(
            known_hosts=known_hosts,
            identity_file=identity_file,
            timeout_seconds=timeout_seconds,
        )

    def _carrier_for(self, node: MeshNodeConfig) -> Any:
        return self._local if node.ssh_alias is None else self._ssh

    def verify_node(self, node: MeshNodeConfig) -> dict[str, Any]:
        return self._carrier_for(node).verify_node(node)

    def run_cli(
        self, node: MeshNodeConfig, arguments: list[str], *, stdin: bytes | None = None
    ) -> dict[str, Any]:
        return self._carrier_for(node).run_cli(node, arguments, stdin=stdin)

    def start_serve(
        self,
        node: MeshNodeConfig,
        arguments: list[str],
        *,
        stdin: bytes,
        timeout_seconds: float,
    ) -> ServeHandle:
        return self._carrier_for(node).start_serve(
            node, arguments, stdin=stdin, timeout_seconds=timeout_seconds
        )


def _signer(key_id: str) -> Ed25519DocumentSigner:
    return Ed25519DocumentSigner(key_id, Ed25519PrivateKey.generate())


def _signer_public_bytes(signer: Ed25519DocumentSigner) -> bytes:
    return signer.private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


class _MemoryResolver:
    def __init__(self) -> None:
        self._records: dict[str, KeyRecord] = {}

    def add(self, record: KeyRecord) -> None:
        if record.key_id in self._records:
            raise MeshSecurityError(f"duplicate trust record: {record.key_id}")
        self._records[record.key_id] = record

    def resolve_key(self, key_id: str) -> KeyRecord | None:
        return self._records.get(key_id)


class _SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC).replace(microsecond=0)


def _require_accepted(label: str, result: Any) -> None:
    if not result.accepted or result.status not in {
        VSourceStatus.ACCEPTED,
        VSourceStatus.IDEMPOTENT_REPLAY,
    }:
        raise MeshSecurityError(f"{label} was rejected: {result.status} {result.reason}")


def _revoke_failed_lease(
    service: LocalVSourceControlPlane,
    lease: Any,
) -> None:
    """Best-effort terminal transition that never masks the original failure."""

    try:
        current = service.get_lease(lease.lease_id)
        if current is None or current.state != LeaseState.ACTIVE:
            return
        current_sha256 = document_sha256(current)
        service.revoke_lease(
            lease.lease_id,
            lease_sha256=current_sha256,
            fencing_token=current.fencing_token,
            renewal_sequence=current.renewal_sequence,
            revocation_reason=LeaseRevocationReason.INTEGRITY_FAILURE,
        )
    except BaseException:
        return


def _wire_model(model_type: Any, payload: object) -> Any:
    return model_type.model_validate_json(
        json.dumps(payload, allow_nan=False, separators=(",", ":"))
    )


def _validate_enroll_init(
    node: MeshNodeConfig,
    payload: dict[str, Any],
    *,
    account_id: str,
) -> dict[str, Any]:
    if set(payload) != _ENROLL_INIT_FIELDS or payload["schema"] != ENROLL_INIT_SCHEMA:
        raise MeshSecurityError(f"node {node.node_id} returned unexpected enrollment fields")
    if payload["account_id"] != account_id or payload["node_id"] != node.node_id:
        raise MeshSecurityError("node enrollment identity does not match the target")
    if payload["implementation_sha256"] != implementation_sha256():
        raise MeshSecurityError("remote node implementation differs from the coordinator")
    if tuple(payload["sans"]) != node.tls_sans:
        raise MeshSecurityError("node enrollment SANs do not match the configuration")
    contract = payload["contract"]
    if not isinstance(contract, dict) or set(contract) != _CONTRACT_FIELDS:
        raise MeshSecurityError("node contract record has unexpected fields")
    if contract["account_id"] != account_id or contract["node_id"] != node.node_id:
        raise MeshSecurityError("node contract identity does not match the target")
    public_key = b64url_decode(contract["public_key_base64"], expected_bytes=32)
    if hashlib.sha256(public_key).hexdigest() != contract["public_key_fingerprint"]:
        raise MeshSecurityError("node contract public-key fingerprint is invalid")
    inventory = _wire_model(ResourceInventory, payload["inventory"])
    if (
        inventory.account_id != account_id
        or inventory.node_id != node.node_id
        or inventory.signature.key_id != contract["key_id"]
        or inventory.public_key_fingerprint != contract["public_key_fingerprint"]
        or [transport.value for transport in inventory.transports] != ["lan_mtls"]
        or inventory.attestation.value != "unverified"
    ):
        raise MeshSecurityError("node inventory violates the mesh mTLS gate profile")
    if document_sha256(inventory) != payload["inventory_sha256"]:
        raise MeshSecurityError("node inventory digest is invalid")
    return {"contract_public_key": public_key, "inventory": inventory}


def _resources() -> dict[str, int]:
    return {
        "cpu_millicores": 100,
        "memory_bytes": 1_048_576,
        "gpu_count": 0,
        "gpu_memory_bytes": 0,
        "storage_bytes": 1_048_576,
        "ingress_bps": 0,
        "egress_bps": 0,
    }


def _parameters() -> dict[str, Any]:
    return {
        "batch_size": None,
        "max_tokens": None,
        "temperature": 0.0,
        "top_k": None,
        "seed": 0,
        "precision": None,
        "checkpoint_interval_seconds": None,
        "replica_count": None,
        "chunk_size": None,
        "width": None,
        "height": None,
        "steps": None,
        "deterministic": True,
    }


def _build_request(
    *,
    account_id: str,
    destination_node_id: str,
    controller: Ed25519DocumentSigner,
    now: datetime,
    run_token: str,
    object_sha256: str,
    object_bytes: int,
) -> ChalRequest:
    slug = hashlib.sha256(destination_node_id.encode("utf-8")).hexdigest()[:12]
    payload = {
        "schema": "planetary.chal.request.v1",
        "request_id": f"request:mesh-mtls:{run_token}:{slug}",
        "trace_id": f"trace:mesh-mtls:{run_token}:{slug}",
        "parent_request_id": None,
        "issued_at": wire_time(now),
        "ttl_seconds": 300,
        "idempotency_key": f"idempotency:mesh-mtls:{run_token}:{slug}",
        "account_id": account_id,
        "capability_id": f"capability:mesh-mtls:{run_token}:{slug}",
        "device_uri": f"chal://unisync-mesh/{slug}/object",
        "workload_kind": "evaluation",
        "workload_manifest": {
            "uri": f"artifact://unisync-mesh/object/{object_sha256}",
            "sha256": object_sha256,
            "size_bytes": object_bytes,
            "media_type": "application/octet-stream",
            "classification": "private",
        },
        "inputs": [],
        "parameters": _parameters(),
        "constraints": {
            "resources": _resources(),
            "latency_budget_ms": 30_000,
            "grounding_required": False,
            "template_leakage_allowed": False,
            "network_access": "none",
            "checkpoint_required": False,
        },
    }
    return sign_contract_document(ChalRequest, payload, controller)


def _build_capability(
    *,
    account_id: str,
    subject_id: str,
    destination_node_id: str,
    controller: Ed25519DocumentSigner,
    now: datetime,
    run_token: str,
) -> CapabilityDocument:
    slug = hashlib.sha256(destination_node_id.encode("utf-8")).hexdigest()[:12]
    payload = {
        "schema": "planetary.chal.capability.v1",
        "capability_id": f"capability:mesh-mtls:{run_token}:{slug}",
        "issuer_id": "controller:unisync-mesh",
        "subject_id": subject_id,
        "account_id": account_id,
        "audience_node_ids": [destination_node_id],
        "actions": ["execute", "reserve"],
        "constraints": {
            "resources": _resources(),
            "minimum_attestation": "unverified",
            "workload_kinds": ["evaluation"],
            "transports": ["lan_mtls"],
            "resource_prefixes": [f"chal://unisync-mesh/{slug}/"],
        },
        "not_before": wire_time(now),
        "ttl_seconds": 600,
        "nonce": f"meshmtls{run_token}{slug}",
        "revocation_epoch": 0,
        "delegable": False,
    }
    return sign_contract_document(CapabilityDocument, payload, controller)


def _peer_wire(record: MeshEnrollmentRecord) -> dict[str, Any]:
    return {
        "account_id": record.account_id,
        "node_id": record.node_id,
        "sans": list(record.sans),
        "certificate_sha256": record.certificate_sha256,
        "public_key_sha256": record.public_key_sha256,
    }


def _prepare_state_db(path: Path) -> Path:
    requested = path.expanduser()
    if requested.exists() or requested.is_symlink():
        raise MeshSecurityError("persistent SQLite state path already exists")
    requested.parent.mkdir(parents=True, exist_ok=True)
    resolved = requested.parent.resolve() / requested.name
    if resolved.exists() or resolved.is_symlink():
        raise MeshSecurityError("persistent SQLite state path already exists")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(resolved, flags, 0o600)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return resolved


def _checkpoint_sqlite(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        result = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    if result is None or result[0] != 0:
        raise MeshSecurityError("SQLite WAL checkpoint did not reach a stable snapshot")


def _write_evidence(path: Path, evidence: dict[str, Any]) -> None:
    encoded = (
        json.dumps(evidence, allow_nan=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    if b"PRIVATE KEY" in encoded:
        raise MeshSecurityError("evidence must never contain private key material")
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        offset = 0
        while offset < len(encoded):
            written = os.write(descriptor, encoded[offset:])
            if written <= 0:
                raise OSError("short write while creating mesh smoke evidence")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    if stat.S_IMODE(path.lstat().st_mode) != 0o600:
        raise MeshSecurityError("mesh smoke evidence file mode is not 0600")


def _job_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, allow_nan=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _prepare_allocated_transfer(
    *,
    config: MeshSmokeConfig,
    lease: Any,
    request: ChalRequest,
    scheduler: Ed25519DocumentSigner,
    scheduler_public: bytes,
    controller: Ed25519DocumentSigner,
    controller_public: bytes,
    registry: EnrollmentRegistry,
    object_sha256: str,
) -> tuple[
    dict[str, Any],
    str,
    TransferContext,
    MeshEnrollmentRecord,
    MeshEnrollmentRecord,
    dict[str, Any],
]:
    """Validate and materialize every post-allocation pre-listener binding."""

    if (
        lease.node_id != config.destination.node_id
        or lease.transport.value != "lan_mtls"
        or lease.state != LeaseState.ACTIVE
    ):
        raise MeshSecurityError("scheduler did not issue an active lan_mtls lease")
    lease_wire = lease.model_dump(mode="json", by_alias=True)
    lease_sha256 = document_sha256(lease)
    parse_signed_lease(
        lease_wire,
        scheduler_key_id=scheduler.key_id,
        scheduler_public_key=scheduler_public,
    )
    context = TransferContext(
        account_id=config.account_id,
        request_sha256=document_sha256(request),
        lease_id=lease.lease_id,
        lease_sha256=lease_sha256,
        fencing_token=lease.fencing_token,
        selected_transport="lan_mtls",
        source_node_id=config.source.node_id,
        destination_node_id=config.destination.node_id,
        object_sha256=object_sha256,
        byte_length=config.object_bytes,
        expires_at=lease.not_before + timedelta(seconds=lease.ttl_seconds),
    )
    SignedLeaseValidator(
        lease_wire=lease_wire,
        request_wire=request.model_dump(mode="json", by_alias=True),
        scheduler_key_id=scheduler.key_id,
        scheduler_public_key=scheduler_public,
        controller_key_id=controller.key_id,
        controller_public_key=controller_public,
        expected_context=context,
    )
    source_record = registry.record(config.account_id, config.source.node_id)
    destination_record = registry.record(
        config.account_id, config.destination.node_id
    )
    registry.active_peer(config.account_id, config.source.node_id)
    registry.active_peer(config.account_id, config.destination.node_id)
    serve_job = {
        "schema": SERVE_SCHEMA,
        "account_id": config.account_id,
        "node_id": config.destination.node_id,
        "bind_host": config.bind_address,
        "port": config.port,
        "declared_vpn_cidrs": list(config.declared_vpn_cidrs),
        "timeout_seconds": config.timeout_seconds,
        "transfer_context": context.to_wire(),
        "lease": lease_wire,
        "request": request.model_dump(mode="json", by_alias=True),
        "source_peer": _peer_wire(source_record),
    }
    return (
        lease_wire,
        lease_sha256,
        context,
        source_record,
        destination_record,
        serve_job,
    )


def run_mesh_mtls_smoke(config: MeshSmokeConfig, carrier: Any) -> dict[str, Any]:
    nodes = (config.source, config.destination)
    if config.carrier == "hybrid":
        # Desktop-as-destination: exactly one local node (the desktop, no SSH
        # alias) and one pinned-SSH remote node (the worker). The local node
        # must be the destination — the desktop runs the mTLS receiver.
        if config.destination.ssh_alias is not None:
            raise MeshSecurityError("hybrid destination (desktop) must be local, not SSH")
        if config.source.ssh_alias is None or config.source.ssh_host_fingerprint is None:
            raise MeshSecurityError("hybrid source (worker) must be a pinned SSH endpoint")
    pins = [carrier.verify_node(node) for node in nodes]
    if config.carrier == "ssh":
        if len({node.ssh_host_fingerprint for node in nodes}) != 2:
            raise MeshSecurityError("mesh smoke requires two distinct pinned SSH host keys")

    enroll_args = lambda node: [
        "enroll-init",
        "--state-dir",
        node.state_dir,
        "--account-id",
        config.account_id,
        "--node-id",
        node.node_id,
        *[value for san in node.tls_sans for value in ("--san", san)],
    ]
    enrollments = [carrier.run_cli(node, enroll_args(node)) for node in nodes]
    validated = [
        _validate_enroll_init(node, enrollment, account_id=config.account_id)
        for node, enrollment in zip(nodes, enrollments, strict=True)
    ]
    if config.carrier in ("ssh", "hybrid") and len({e["hostname"] for e in enrollments}) != 2:
        raise MeshSecurityError("carrier did not reach two distinct physical hostnames")
    if len({e["tls_public_key_sha256"] for e in enrollments}) != 2:
        raise MeshSecurityError("nodes do not have distinct node-local TLS keys")
    if len({e["contract"]["public_key_fingerprint"] for e in enrollments}) != 2:
        raise MeshSecurityError("nodes do not have distinct node-local contract keys")

    run_token = secrets.token_hex(8)
    now = datetime.now(UTC).replace(microsecond=0)
    subject_id = config.subject_id
    scheduler_id = f"scheduler:unisync-mesh:{run_token}"
    controller = _signer(f"key:controller:unisync-mesh:{run_token}")
    scheduler = _signer(f"key:scheduler:unisync-mesh:{run_token}")
    controller_public = _signer_public_bytes(controller)
    scheduler_public = _signer_public_bytes(scheduler)
    authority = MeshCertificateAuthority.create(f"Unisync Mesh CA {run_token}")
    registry = EnrollmentRegistry(config.registry_dir)
    issued: list[IssuedCertificate] = []
    for node, enrollment in zip(nodes, enrollments, strict=True):
        certificate = authority.issue_node_certificate(
            enrollment["csr_pem"],
            account_id=config.account_id,
            node_id=node.node_id,
            sans=node.tls_sans,
        )
        if certificate.public_key_sha256 != enrollment["tls_public_key_sha256"]:
            raise MeshSecurityError("issued certificate does not bind the node CSR key")
        registry.register(
            MeshEnrollmentRecord(
                account_id=config.account_id,
                node_id=node.node_id,
                sans=certificate.sans,
                certificate_sha256=certificate.certificate_sha256,
                public_key_sha256=certificate.public_key_sha256,
                serial_hex=certificate.serial_hex,
                issuer=certificate.issuer,
                not_before=certificate.not_before,
                not_after=certificate.not_after,
                enrolled_at=wire_time(now),
            )
        )
        issued.append(certificate)
        install_result = carrier.run_cli(
            node,
            ["enroll-install", "--state-dir", node.state_dir],
            stdin=_job_json(
                {
                    "schema": ENROLL_INSTALL_SCHEMA,
                    "account_id": config.account_id,
                    "node_id": node.node_id,
                    "certificate_pem": certificate.certificate_pem,
                    "ca_pem": certificate.ca_pem,
                    "certificate_sha256": certificate.certificate_sha256,
                    "public_key_sha256": certificate.public_key_sha256,
                    "controller_key_id": controller.key_id,
                    "controller_public_key_base64": b64url_encode(controller_public),
                    "scheduler_key_id": scheduler.key_id,
                    "scheduler_public_key_base64": b64url_encode(scheduler_public),
                }
            ),
        )
        if (
            install_result.get("schema") != ENROLL_INSTALL_RESULT_SCHEMA
            or install_result.get("installed") is not True
            or install_result.get("certificate_sha256") != certificate.certificate_sha256
            or install_result.get("public_key_sha256") != certificate.public_key_sha256
            or install_result.get("serial_hex") != certificate.serial_hex
            or install_result.get("node_id") != node.node_id
            or install_result.get("trust_installed") is not True
            or install_result.get("controller_key_id") != controller.key_id
            or install_result.get("scheduler_key_id") != scheduler.key_id
        ):
            raise MeshSecurityError(
                f"node {node.node_id} did not confirm the exact issued certificate"
            )

    resolver = _MemoryResolver()
    resolver.add(
        KeyRecord(
            key_id=controller.key_id,
            public_key=controller_public,
            account_id=config.account_id,
            audiences=(scheduler_id,),
            subject_id=subject_id,
        )
    )
    for node, extra in zip(nodes, validated, strict=True):
        enrollment_contract = enrollments[nodes.index(node)]["contract"]
        resolver.add(
            KeyRecord(
                key_id=enrollment_contract["key_id"],
                public_key=extra["contract_public_key"],
                account_id=config.account_id,
                audiences=(scheduler_id,),
                subject_id=subject_id,
                node_id=node.node_id,
            )
        )

    if config.prepare_mode == "existing":
        # The object is already present in the source outbox (e.g. a completed
        # AIVM result staged via `stage-result`). No preparation is performed;
        # the lease-bound mTLS `send` reads and verifies it from the outbox.
        object_sha256 = config.existing_object_sha256
    else:
        if config.prepare_mode == "random":
            prepare_result = carrier.run_cli(
                config.source,
                ["prepare", "--state-dir", config.source.state_dir],
                stdin=_job_json(
                    {
                        "schema": PREPARE_SCHEMA,
                        "account_id": config.account_id,
                        "node_id": config.source.node_id,
                        "byte_length": config.object_bytes,
                    }
                ),
            )
        else:
            # The source reproduces the repo-pinned workload artifact locally;
            # config.object_bytes declares its exact expected size upfront.
            prepare_result = carrier.run_cli(
                config.source,
                ["prepare-artifact", "--state-dir", config.source.state_dir],
                stdin=_job_json(
                    {
                        "schema": PREPARE_ARTIFACT_SCHEMA,
                        "account_id": config.account_id,
                        "node_id": config.source.node_id,
                        "artifact": (
                            "model"
                            if config.prepare_mode == "workload_model"
                            else "document"
                        ),
                    }
                ),
            )
        if (
            prepare_result.get("schema") != PREPARE_RESULT_SCHEMA
            or prepare_result.get("account_id") != config.account_id
            or prepare_result.get("node_id") != config.source.node_id
            or prepare_result.get("byte_length") != config.object_bytes
            or not isinstance(prepare_result.get("object_sha256"), str)
        ):
            raise MeshSecurityError("source did not prepare the exact bounded local object")
        object_sha256 = prepare_result["object_sha256"]
    if len(object_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in object_sha256
    ):
        raise MeshSecurityError("source returned an invalid object digest")

    database_path = _prepare_state_db(config.state_db)
    clock = _SystemClock()
    service = LocalVSourceControlPlane(
        database_path,
        key_resolver=resolver,
        signer=scheduler,
        clock=clock,
        scheduler_id=scheduler_id,
    )
    for extra in validated:
        _require_accepted("signed inventory", service.register_inventory(extra["inventory"]))

    request = _build_request(
        account_id=config.account_id,
        destination_node_id=config.destination.node_id,
        controller=controller,
        now=clock.now(),
        run_token=run_token,
        object_sha256=object_sha256,
        object_bytes=config.object_bytes,
    )
    capability = _build_capability(
        account_id=config.account_id,
        subject_id=subject_id,
        destination_node_id=config.destination.node_id,
        controller=controller,
        now=clock.now(),
        run_token=run_token,
    )
    allocation = service.allocate(
        request,
        capability,
        authenticated_subject_id=subject_id,
        lease_ttl_seconds=config.lease_ttl_seconds,
    )
    _require_accepted("mesh allocation", allocation)
    lease = allocation.lease
    if lease is None:
        raise MeshSecurityError("scheduler accepted allocation without returning a lease")
    try:
        (
            lease_wire,
            lease_sha256,
            context,
            source_record,
            destination_record,
            serve_job,
        ) = _prepare_allocated_transfer(
            config=config,
            lease=lease,
            request=request,
            scheduler=scheduler,
            scheduler_public=scheduler_public,
            controller=controller,
            controller_public=controller_public,
            registry=registry,
            object_sha256=object_sha256,
        )
    except BaseException:
        _revoke_failed_lease(service, lease)
        raise
    handle = None
    try:
        handle = carrier.start_serve(
            config.destination,
            ["serve", "--state-dir", config.destination.state_dir],
            stdin=_job_json(serve_job),
            timeout_seconds=float(config.timeout_seconds),
        )
        ready = handle.ready()
        if (
            ready.get("schema") != SERVE_READY_SCHEMA
            or ready.get("node_id") != config.destination.node_id
            or normalize_san(str(ready.get("host"))) != normalize_san(config.bind_address)
        ):
            raise MeshSecurityError("serve process did not report the declared listener")
        server_port = ready.get("port")
        if not isinstance(server_port, int) or isinstance(server_port, bool) or not 1 <= server_port <= 65535:
            raise MeshSecurityError("serve process reported an invalid port")
        if config.port != 0 and server_port != config.port:
            raise MeshSecurityError("serve process bound an undeclared port")

        send_job = {
            "schema": SEND_SCHEMA,
            "account_id": config.account_id,
            "node_id": config.source.node_id,
            "server_host": config.bind_address,
            "server_port": server_port,
            "server_hostname": config.server_hostname,
            "declared_vpn_cidrs": list(config.declared_vpn_cidrs),
            "timeout_seconds": config.timeout_seconds,
            "transfer_context": context.to_wire(),
            "lease": lease_wire,
            "request": request.model_dump(mode="json", by_alias=True),
            "destination_peer": _peer_wire(destination_record),
        }
        send_result = carrier.run_cli(
            config.source,
            ["send", "--state-dir", config.source.state_dir],
            stdin=_job_json(send_job),
        )
        serve_result = handle.result()
    except BaseException:
        if handle is not None:
            handle.kill()
        _revoke_failed_lease(service, lease)
        raise

    try:
        release = service.release_lease(
            lease.lease_id,
            lease_sha256=lease_sha256,
            fencing_token=lease.fencing_token,
            renewal_sequence=lease.renewal_sequence,
        )
        _require_accepted("lease release", release)
        released = service.get_lease(lease.lease_id)
        if released is None or released.state != LeaseState.RELEASED:
            raise MeshSecurityError("lease was not durably released after the transfer")
    except BaseException:
        _revoke_failed_lease(service, lease)
        raise

    expected_receipt = context.receipt_sha256(object_sha256)
    if (
        send_result.get("schema") != SEND_RESULT_SCHEMA
        or send_result.get("node_id") != config.source.node_id
        or send_result.get("object_sha256") != object_sha256
        or send_result.get("bytes_transferred") != config.object_bytes
        or send_result.get("resumed_from") != 0
        or send_result.get("transport_id") != "lan_mtls"
        or send_result.get("verified_receipt_sha256") != expected_receipt
        or send_result.get("certificate_sha256") != source_record.certificate_sha256
        or send_result.get("negotiated_tls_version") != "TLSv1.3"
    ):
        raise MeshSecurityError("send result does not prove the bound mTLS transfer")
    if (
        serve_result.get("schema") != SERVE_RESULT_SCHEMA
        or serve_result.get("node_id") != config.destination.node_id
        or serve_result.get("received") is not True
        or serve_result.get("object_sha256") != object_sha256
        or serve_result.get("byte_length") != config.object_bytes
        or serve_result.get("verified_receipt_sha256") != expected_receipt
        or serve_result.get("certificate_sha256") != destination_record.certificate_sha256
        or "client_identity_bound" not in serve_result.get("audit_events", [])
    ):
        raise MeshSecurityError("serve result does not prove the bound mTLS receipt")

    os.chmod(database_path, 0o600)
    if stat.S_IMODE(database_path.lstat().st_mode) != 0o600:
        raise MeshSecurityError("persistent SQLite state is not mode 0600")
    _checkpoint_sqlite(database_path)
    database_sha256 = hashlib.sha256(database_path.read_bytes()).hexdigest()

    return {
        "schema": EVIDENCE_SCHEMA,
        "passed": True,
        "completed_at": wire_time(datetime.now(UTC)),
        "run_token": run_token,
        "account_id": config.account_id,
        "subject_id": subject_id,
        "bootstrap_carrier": carrier.kind,
        "contract_transport": "lan_mtls",
        "implementation_sha256": implementation_sha256(),
        "carrier_pins": pins,
        "trust_bundle": {
            "scheduler_id": scheduler_id,
            "controller_key_id": controller.key_id,
            "controller_public_key_base64": b64url_encode(controller_public),
            "scheduler_key_id": scheduler.key_id,
            "scheduler_public_key_base64": b64url_encode(scheduler_public),
            "node_contracts": [enrollment["contract"] for enrollment in enrollments],
        },
        "enrollment": {
            "registry_path": str(registry.path),
            "registry": registry.snapshot_wire(),
            "hostnames": [enrollment["hostname"] for enrollment in enrollments],
            "csr_pems": {
                node.node_id: enrollment["csr_pem"]
                for node, enrollment in zip(nodes, enrollments, strict=True)
            },
        },
        "documents": {
            "inventories": [enrollment["inventory"] for enrollment in enrollments],
            "request": request.model_dump(mode="json", by_alias=True),
            "capability": capability.model_dump(mode="json", by_alias=True),
            "active_lease": lease_wire,
            "released_lease": released.model_dump(mode="json", by_alias=True),
        },
        "transfer": {
            "transfer_context": context.to_wire(),
            "object_sha256": object_sha256,
            "byte_length": config.object_bytes,
            "prepare_mode": config.prepare_mode,
            "verified_receipt_sha256": expected_receipt,
            "send_result": send_result,
            "serve_result": serve_result,
        },
        "sqlite_state": {
            "path": str(database_path),
            "sha256": database_sha256,
        },
        "claims": {
            "bootstrap_carrier": carrier.kind,
            "data_transport": "lan_mtls",
            "workload_bytes_to_destination_via_lan_mtls_only": True,
            "workload_bytes_generated_on_source_node": True,
            "workload_bytes_provisioned_to_source_via_bootstrap": False,
            "negotiated_tls_version": "TLSv1.3",
            "mutual_tls_client_certificate_required": True,
            "node_local_private_key_export": False,
            "persistent_enrollment_registry": True,
            "scheduler_signed_active_lease_bound": True,
            "content_addressed_bounded_object": True,
            "two_distinct_pinned_ssh_endpoints": config.carrier == "ssh",
            "single_host_rehearsal": config.carrier == "local",
            # Hybrid spans this desktop (local receiver) and one physical SSH
            # worker: two distinct machines, verified above by distinct
            # enrollment hostnames. It is a genuine physical two-node transfer
            # with a single pinned SSH endpoint (the worker) and the desktop as
            # the destination.
            "physical_two_node_execution_proven": config.carrier in ("ssh", "hybrid"),
            "desktop_is_local_mtls_destination": config.carrier == "hybrid",
            "single_pinned_ssh_worker_endpoint": config.carrier == "hybrid",
            "certificate_rotation_renewal_proven": False,
            "revocation_distribution_proven": False,
            "nat_traversal_or_relay_proven": False,
            "production_ca_operations_proven": False,
            "failure_recovery_proven": False,
            "hardware_attestation_proven": False,
        },
        "capacity_note": (
            "Inventory RAM/free-disk values are host snapshots, not reservations; "
            "network capacity is intentionally advertised as zero for this "
            "single-object gate."
        ),
    }


def load_config(path: Path) -> MeshSmokeConfig:
    raw = path.expanduser().read_bytes()
    if len(raw) > MAX_CONFIG_BYTES:
        raise MeshSecurityError("mesh smoke configuration exceeds its size bound")
    return parse_config(strict_json(raw))


def build_carrier(config: MeshSmokeConfig) -> Any:
    if config.carrier == "ssh":
        assert config.known_hosts is not None
        return SshMeshCarrier(
            known_hosts=config.known_hosts,
            identity_file=config.identity_file,
            timeout_seconds=config.timeout_seconds,
        )
    return LocalMeshCarrier(timeout_seconds=config.timeout_seconds)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        config = load_config(arguments.config)
        carrier = build_carrier(config)
        evidence = run_mesh_mtls_smoke(config, carrier)
        _write_evidence(config.output, evidence)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "schema": ERROR_SCHEMA,
                    "passed": False,
                    "error": type(exc).__name__,
                    "message": str(exc)[:512],
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            {
                "schema": evidence["schema"],
                "passed": True,
                "output": str(config.output),
                "object_sha256": evidence["transfer"]["object_sha256"],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
