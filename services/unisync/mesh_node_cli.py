"""Fixed node-local CLI for the Unisync private-mesh mTLS smoke gate.

The coordinator may invoke only these five subcommands over its pinned
administrative SSH carrier:

- ``enroll-init``: generate node-local TLS and contract keys, emit a CSR and a
  signed ``lan_mtls`` inventory.  No private key ever leaves the node.
- ``enroll-install``: install an issued certificate after exact chain, SAN,
  account/node, and public-key binding verification.
- ``prepare``: create one bounded opaque source object locally and return only
  its content digest and size.
- ``serve``: receive exactly one lease-bound object over a real TCP mTLS
  socket bound to an explicitly declared loopback/private/VPN address.
- ``send``: upload exactly one lease-bound object over a real TCP mTLS socket.

There is no shell, entrypoint, command, eval, pickle, marshal, or bytecode
field anywhere in these jobs.  SSH is bootstrap control only; workload bytes
cross only the Unisync ``lan_mtls`` socket.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import secrets
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .contracts import TransferContext
from .framing import DEFAULT_LIMITS
from .mesh_common import (
    MeshSecurityError,
    b64url_decode,
    normalize_san,
    normalize_san_set,
    require_identifier,
    require_sha256,
    strict_json,
)
from .mesh_identity import (
    build_signed_inventory,
    create_tls_enrollment,
    install_certificate,
    install_mesh_trust,
    inventory_sha256,
    inventory_wire,
    load_or_create_contract_identity,
    load_mesh_trust,
    load_tls_credential_paths,
    public_contract_record,
)
from .mesh_lease import LeaseUseStore, SignedLeaseValidator
from .storage import ContentAddressedStore
from .tls import (
    EnrolledPeerIdentity,
    TLSCredentials,
    TrustedLanClient,
    TrustedLanServer,
    _literal_allowed_address,
)
from .errors import TLSConfigurationError

ENROLL_INIT_SCHEMA = "planetary.unisync.mesh_enroll_init.v1"
ENROLL_INSTALL_SCHEMA = "planetary.unisync.mesh_enroll_install.v1"
ENROLL_INSTALL_RESULT_SCHEMA = "planetary.unisync.mesh_enroll_install_result.v1"
PREPARE_SCHEMA = "planetary.unisync.mesh_prepare.v1"
PREPARE_ARTIFACT_SCHEMA = "planetary.unisync.mesh_prepare_artifact.v1"
PREPARE_RESULT_SCHEMA = "planetary.unisync.mesh_prepare_result.v1"
SERVE_SCHEMA = "planetary.unisync.mesh_serve.v1"
SERVE_READY_SCHEMA = "planetary.unisync.mesh_serve_ready.v1"
SERVE_RESULT_SCHEMA = "planetary.unisync.mesh_serve_result.v1"
SEND_SCHEMA = "planetary.unisync.mesh_send.v1"
SEND_RESULT_SCHEMA = "planetary.unisync.mesh_send_result.v1"
CLI_ERROR_SCHEMA = "planetary.unisync.mesh_cli_error.v1"

MAX_INSTALL_JOB_BYTES = 64 * 1024
MAX_PREPARE_JOB_BYTES = 8 * 1024
MAX_SERVE_JOB_BYTES = 256 * 1024
MAX_SEND_JOB_BYTES = 256 * 1024
MAX_OBJECT_BYTES = 8 * 1024 * 1024
INBOX_DIR = "inbox"
OUTBOX_DIR = "outbox"

_INSTALL_FIELDS = frozenset(
    {
        "schema",
        "account_id",
        "node_id",
        "certificate_pem",
        "ca_pem",
        "certificate_sha256",
        "public_key_sha256",
        "controller_key_id",
        "controller_public_key_base64",
        "scheduler_key_id",
        "scheduler_public_key_base64",
    }
)
_PREPARE_FIELDS = frozenset({"schema", "account_id", "node_id", "byte_length"})
_PREPARE_ARTIFACT_FIELDS = frozenset({"schema", "account_id", "node_id", "artifact"})
_PEER_FIELDS = frozenset(
    {"account_id", "node_id", "sans", "certificate_sha256", "public_key_sha256"}
)
_SERVE_FIELDS = frozenset(
    {
        "schema",
        "account_id",
        "node_id",
        "bind_host",
        "port",
        "declared_vpn_cidrs",
        "timeout_seconds",
        "transfer_context",
        "lease",
        "request",
        "source_peer",
    }
)
_SEND_FIELDS = frozenset(
    {
        "schema",
        "account_id",
        "node_id",
        "server_host",
        "server_port",
        "server_hostname",
        "declared_vpn_cidrs",
        "timeout_seconds",
        "transfer_context",
        "lease",
        "request",
        "destination_peer",
    }
)

_IMPLEMENTATION_FILES = (
    "mesh_node_cli.py",
    "mesh_identity.py",
    "mesh_lease.py",
    "mesh_common.py",
    "contracts.py",
    "errors.py",
    "framing.py",
    "storage.py",
    "tls.py",
)


def implementation_sha256() -> str:
    """Digest the fixed node-side implementation used by this gate."""

    digest = hashlib.sha256()
    for name in _IMPLEMENTATION_FILES:
        payload = Path(__file__).with_name(name).read_bytes()
        digest.update(name.encode("ascii"))
        digest.update(b"\0")
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _read_stdin_job(max_bytes: int) -> dict[str, Any]:
    raw = sys.stdin.buffer.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise MeshSecurityError("mesh job exceeds its input limit")
    return strict_json(raw)


def _require_timeout(value: object) -> float:
    if not isinstance(value, int) or isinstance(value, bool) or not 5 <= value <= 300:
        raise MeshSecurityError("timeout_seconds must be an integer between 5 and 300")
    return float(value)


def _require_port(value: object, *, allow_zero: bool) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise MeshSecurityError("port must be an integer")
    lower = 0 if allow_zero else 1
    if not lower <= value <= 65535:
        raise MeshSecurityError("port is outside the valid range")
    return value


def _require_vpn_cidrs(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise MeshSecurityError("declared_vpn_cidrs must be a list of strings")
    if len(value) > 8:
        raise MeshSecurityError("too many declared VPN CIDRs")
    return tuple(value)


def _peer_from_wire(payload: object, label: str) -> EnrolledPeerIdentity:
    if not isinstance(payload, dict) or set(payload) != _PEER_FIELDS:
        raise MeshSecurityError(f"{label} record has unexpected fields")
    sans = normalize_san_set(payload["sans"])
    return EnrolledPeerIdentity(
        account_id=require_identifier(f"{label}.account_id", payload["account_id"]),
        node_id=require_identifier(f"{label}.node_id", payload["node_id"]),
        sans=frozenset(sans),
        certificate_sha256=require_sha256(
            f"{label}.certificate_sha256", payload["certificate_sha256"]
        ),
        public_key_sha256=require_sha256(
            f"{label}.public_key_sha256", payload["public_key_sha256"]
        ),
    )


def _lease_wire(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise MeshSecurityError("lease must be a JSON object")
    return payload


def _validator_for_job(
    job: dict[str, Any],
    context: TransferContext,
    *,
    state_dir: Path,
    account_id: str,
    node_id: str,
) -> SignedLeaseValidator:
    trust = load_mesh_trust(
        state_dir,
        account_id=account_id,
        node_id=node_id,
    )
    return SignedLeaseValidator(
        lease_wire=_lease_wire(job["lease"]),
        request_wire=_lease_wire(job["request"]),
        scheduler_key_id=trust["scheduler_key_id"],
        scheduler_public_key=trust["scheduler_public_key"],
        controller_key_id=trust["controller_key_id"],
        controller_public_key=trust["controller_public_key"],
        expected_context=context,
    )


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, allow_nan=False, sort_keys=True, separators=(",", ":")))
    sys.stdout.flush()


def command_enroll_init(arguments: argparse.Namespace) -> dict[str, Any]:
    account_id = require_identifier("account_id", arguments.account_id)
    node_id = require_identifier("node_id", arguments.node_id)
    state_dir = Path(arguments.state_dir)
    enrollment = create_tls_enrollment(
        state_dir,
        account_id=account_id,
        node_id=node_id,
        sans=arguments.san,
    )
    contract = load_or_create_contract_identity(
        state_dir, account_id=account_id, node_id=node_id
    )
    inventory = build_signed_inventory(contract, state_dir=state_dir)
    return {
        "schema": ENROLL_INIT_SCHEMA,
        "hostname": platform.node(),
        "account_id": account_id,
        "node_id": node_id,
        "sans": enrollment["sans"],
        "csr_pem": enrollment["csr_pem"],
        "tls_public_key_sha256": enrollment["tls_public_key_sha256"],
        "contract": public_contract_record(contract),
        "inventory": inventory_wire(inventory),
        "inventory_sha256": inventory_sha256(inventory),
        "implementation_sha256": implementation_sha256(),
    }


def command_enroll_install(arguments: argparse.Namespace) -> dict[str, Any]:
    job = _read_stdin_job(MAX_INSTALL_JOB_BYTES)
    if set(job) != _INSTALL_FIELDS or job["schema"] != ENROLL_INSTALL_SCHEMA:
        raise MeshSecurityError("enroll-install job has unexpected fields")
    account_id = require_identifier("account_id", job["account_id"])
    node_id = require_identifier("node_id", job["node_id"])
    metadata = install_certificate(
        Path(arguments.state_dir),
        account_id=account_id,
        node_id=node_id,
        certificate_pem=job["certificate_pem"],
        ca_pem=job["ca_pem"],
        expected_certificate_sha256=require_sha256(
            "certificate_sha256", job["certificate_sha256"]
        ),
        expected_public_key_sha256=require_sha256(
            "public_key_sha256", job["public_key_sha256"]
        ),
    )
    trust = install_mesh_trust(
        Path(arguments.state_dir),
        account_id=account_id,
        node_id=node_id,
        controller_key_id=require_identifier(
            "controller_key_id", job["controller_key_id"]
        ),
        controller_public_key=b64url_decode(
            job["controller_public_key_base64"], expected_bytes=32
        ),
        scheduler_key_id=require_identifier(
            "scheduler_key_id", job["scheduler_key_id"]
        ),
        scheduler_public_key=b64url_decode(
            job["scheduler_public_key_base64"], expected_bytes=32
        ),
    )
    return {
        "schema": ENROLL_INSTALL_RESULT_SCHEMA,
        "account_id": account_id,
        "node_id": node_id,
        "installed": True,
        "trust_installed": True,
        "controller_key_id": trust["controller_key_id"],
        "scheduler_key_id": trust["scheduler_key_id"],
        **metadata,
    }


def command_prepare(arguments: argparse.Namespace) -> dict[str, Any]:
    """Create one bounded opaque object locally and reveal only digest and size."""

    job = _read_stdin_job(MAX_PREPARE_JOB_BYTES)
    if set(job) != _PREPARE_FIELDS or job["schema"] != PREPARE_SCHEMA:
        raise MeshSecurityError("prepare job has unexpected fields")
    account_id = require_identifier("account_id", job["account_id"])
    node_id = require_identifier("node_id", job["node_id"])
    byte_length = job["byte_length"]
    if (
        not isinstance(byte_length, int)
        or isinstance(byte_length, bool)
        or not 1 <= byte_length <= MAX_OBJECT_BYTES
    ):
        raise MeshSecurityError("byte_length is outside the bounded object range")
    state_dir = Path(arguments.state_dir)
    load_tls_credential_paths(state_dir, account_id=account_id, node_id=node_id)
    payload = secrets.token_bytes(byte_length)
    digest = ContentAddressedStore(state_dir / OUTBOX_DIR).put_bytes(payload)
    return {
        "schema": PREPARE_RESULT_SCHEMA,
        "account_id": account_id,
        "node_id": node_id,
        "object_sha256": digest,
        "byte_length": byte_length,
    }


def command_prepare_artifact(arguments: argparse.Namespace) -> dict[str, Any]:
    """Reproduce one repo-pinned workload artifact locally; reveal only digest and size.

    The artifact bytes are derived deterministically from the pinned repository
    content on this node (the demo ONNX classifier builder or the fixed demo
    document), so no workload bytes ever cross the administrative channel.
    """

    job = _read_stdin_job(MAX_PREPARE_JOB_BYTES)
    if set(job) != _PREPARE_ARTIFACT_FIELDS or job["schema"] != PREPARE_ARTIFACT_SCHEMA:
        raise MeshSecurityError("prepare-artifact job has unexpected fields")
    account_id = require_identifier("account_id", job["account_id"])
    node_id = require_identifier("node_id", job["node_id"])
    artifact = job["artifact"]
    if artifact not in {"model", "document"}:
        raise MeshSecurityError("prepare-artifact kind is not allowlisted")
    state_dir = Path(arguments.state_dir)
    load_tls_credential_paths(state_dir, account_id=account_id, node_id=node_id)
    from services.aivm_profiles.text_classification.build_demo_model import (
        DEMO_DOCUMENT,
        build,
    )

    payload = DEMO_DOCUMENT if artifact == "document" else build()
    if not 1 <= len(payload) <= MAX_OBJECT_BYTES:
        raise MeshSecurityError("artifact is outside the bounded object range")
    digest = ContentAddressedStore(state_dir / OUTBOX_DIR).put_bytes(payload)
    return {
        "schema": PREPARE_RESULT_SCHEMA,
        "account_id": account_id,
        "node_id": node_id,
        "object_sha256": digest,
        "byte_length": len(payload),
    }


def command_serve(arguments: argparse.Namespace) -> dict[str, Any]:
    job = _read_stdin_job(MAX_SERVE_JOB_BYTES)
    if set(job) != _SERVE_FIELDS or job["schema"] != SERVE_SCHEMA:
        raise MeshSecurityError("serve job has unexpected fields")
    account_id = require_identifier("account_id", job["account_id"])
    node_id = require_identifier("node_id", job["node_id"])
    timeout = _require_timeout(job["timeout_seconds"])
    context = TransferContext.from_wire(job["transfer_context"])
    if context.account_id != account_id or context.destination_node_id != node_id:
        raise MeshSecurityError("serve job context does not bind this node as destination")
    source_peer = _peer_from_wire(job["source_peer"], "source_peer")
    if (
        source_peer.node_id != context.source_node_id
        or source_peer.account_id != account_id
    ):
        raise MeshSecurityError("serve job source peer does not match the transfer context")
    if not isinstance(job["bind_host"], str):
        raise MeshSecurityError("bind_host must be a string")
    state_dir = Path(arguments.state_dir)
    validator = _validator_for_job(
        job,
        context,
        state_dir=state_dir,
        account_id=account_id,
        node_id=node_id,
    )
    paths, certificate_metadata = load_tls_credential_paths(
        state_dir, account_id=account_id, node_id=node_id
    )
    credentials = TLSCredentials(**paths)
    destination_root = state_dir / INBOX_DIR
    server = TrustedLanServer(
        bind_host=job["bind_host"],
        port=_require_port(job["port"], allow_zero=True),
        credentials=credentials,
        destination_root=destination_root,
        validator=validator,
        declared_listener_addresses={job["bind_host"]},
        allowed_client_sans=set(source_peer.sans),
        enrolled_client_identities=(source_peer,),
        declared_vpn_cidrs=_require_vpn_cidrs(job["declared_vpn_cidrs"]),
        limits=DEFAULT_LIMITS,
        idle_timeout=min(timeout, 30.0),
    )
    lease_use = LeaseUseStore(state_dir, account_id=account_id, node_id=node_id)
    lease_use.begin(context)
    try:
        server.start()
        try:
            host, port = server.address
            _print_json(
                {
                    "schema": SERVE_READY_SCHEMA,
                    "node_id": node_id,
                    "host": host,
                    "port": port,
                }
            )
            destination = ContentAddressedStore(destination_root)
            deadline = time.monotonic() + timeout
            received = False
            while time.monotonic() < deadline:
                if destination.has(context.object_sha256):
                    received = True
                    break
                time.sleep(0.1)
        finally:
            server.close()
        if not received:
            raise MeshSecurityError("mTLS receiver timed out before committing the object")
        result: dict[str, Any] = {
            "schema": SERVE_RESULT_SCHEMA,
            "node_id": node_id,
            "received": True,
            "object_sha256": context.object_sha256,
            "byte_length": destination.stat_size(context.object_sha256),
            "verified_receipt_sha256": context.receipt_sha256(),
            "certificate_sha256": certificate_metadata["certificate_sha256"],
            "audit_events": server.audit_events,
            "errors": [type(error).__name__ for error in server.errors],
        }
        if result["byte_length"] != context.byte_length:
            raise MeshSecurityError("received object size does not match the transfer context")
        lease_use.finish(context, succeeded=True)
        return result
    except BaseException:
        try:
            lease_use.finish(context, succeeded=False)
        except BaseException:
            pass
        raise


class _RecordingLanClient(TrustedLanClient):
    """TrustedLanClient that records and enforces the negotiated TLS version."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.negotiated_tls_version: str | None = None
        self.negotiated_cipher: str | None = None

    def _upload_over_socket(self, *, tls_sock: Any, **kwargs: Any) -> Any:
        version_probe = getattr(tls_sock, "version", None)
        cipher_probe = getattr(tls_sock, "cipher", None)
        self.negotiated_tls_version = version_probe() if callable(version_probe) else None
        cipher_info = cipher_probe() if callable(cipher_probe) else None
        self.negotiated_cipher = cipher_info[0] if cipher_info else None
        if self.negotiated_tls_version != "TLSv1.3":
            raise TLSConfigurationError("negotiated TLS version is not TLSv1.3")
        return super()._upload_over_socket(tls_sock=tls_sock, **kwargs)


def command_send(arguments: argparse.Namespace) -> dict[str, Any]:
    job = _read_stdin_job(MAX_SEND_JOB_BYTES)
    if set(job) != _SEND_FIELDS or job["schema"] != SEND_SCHEMA:
        raise MeshSecurityError("send job has unexpected fields")
    account_id = require_identifier("account_id", job["account_id"])
    node_id = require_identifier("node_id", job["node_id"])
    timeout = _require_timeout(job["timeout_seconds"])
    context = TransferContext.from_wire(job["transfer_context"])
    if context.account_id != account_id or context.source_node_id != node_id:
        raise MeshSecurityError("send job context does not bind this node as source")
    destination_peer = _peer_from_wire(job["destination_peer"], "destination_peer")
    if (
        destination_peer.node_id != context.destination_node_id
        or destination_peer.account_id != account_id
    ):
        raise MeshSecurityError(
            "send job destination peer does not match the transfer context"
        )
    if not isinstance(job["server_host"], str):
        raise MeshSecurityError("server_host must be a string")
    _literal_allowed_address(
        job["server_host"],
        declared_vpn_cidrs=_require_vpn_cidrs(job["declared_vpn_cidrs"]),
    )
    server_hostname = normalize_san(job["server_hostname"])
    if server_hostname not in destination_peer.sans:
        raise MeshSecurityError("server_hostname is not an enrolled destination SAN")
    state_dir = Path(arguments.state_dir)
    validator = _validator_for_job(
        job,
        context,
        state_dir=state_dir,
        account_id=account_id,
        node_id=node_id,
    )
    paths, certificate_metadata = load_tls_credential_paths(
        state_dir, account_id=account_id, node_id=node_id
    )
    source = ContentAddressedStore(state_dir / OUTBOX_DIR)
    if source.stat_size(context.object_sha256) != context.byte_length:
        raise MeshSecurityError(
            "source content-addressed object is missing or has the wrong size"
        )
    client = _RecordingLanClient(
        credentials=TLSCredentials(**paths),
        server_hostname=server_hostname,
        validator=validator,
        enrolled_server_identities=(destination_peer,),
        limits=DEFAULT_LIMITS,
    )
    lease_use = LeaseUseStore(state_dir, account_id=account_id, node_id=node_id)
    lease_use.begin(context)
    try:
        result = client.upload_object(
            context=context,
            source_root=source.root,
            host=job["server_host"],
            port=_require_port(job["server_port"], allow_zero=False),
            timeout=min(timeout, 30.0),
        )
        response = {
            "schema": SEND_RESULT_SCHEMA,
            "node_id": node_id,
            "object_sha256": result.object_sha256,
            "bytes_transferred": result.bytes_transferred,
            "resumed_from": result.resumed_from,
            "transport_id": result.transport_id,
            "verified_receipt_sha256": result.verified_receipt_sha256,
            "certificate_sha256": certificate_metadata["certificate_sha256"],
            "negotiated_tls_version": client.negotiated_tls_version,
            "negotiated_cipher": client.negotiated_cipher,
        }
        lease_use.finish(context, succeeded=True)
        return response
    except BaseException:
        try:
            lease_use.finish(context, succeeded=False)
        except BaseException:
            pass
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    enroll_init = subparsers.add_parser("enroll-init")
    enroll_init.add_argument("--state-dir", type=Path, required=True)
    enroll_init.add_argument("--account-id", required=True)
    enroll_init.add_argument("--node-id", required=True)
    enroll_init.add_argument("--san", action="append", required=True)
    for name in ("enroll-install", "prepare", "prepare-artifact", "serve", "send"):
        sub = subparsers.add_parser(name)
        sub.add_argument("--state-dir", type=Path, required=True)
    return parser


_COMMANDS = {
    "enroll-init": command_enroll_init,
    "enroll-install": command_enroll_install,
    "prepare": command_prepare,
    "prepare-artifact": command_prepare_artifact,
    "serve": command_serve,
    "send": command_send,
}


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        result = _COMMANDS[arguments.command](arguments)
    except Exception as exc:
        _print_json(
            {
                "schema": CLI_ERROR_SCHEMA,
                "ok": False,
                "error": type(exc).__name__,
                "message": str(exc)[:256],
            }
        )
        return 2
    _print_json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
