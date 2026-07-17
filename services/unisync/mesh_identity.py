"""Node-local identity state for the Unisync private-mesh mTLS gate.

Each node keeps three deliberately separate identity layers:

1. an OpenSSH host/user identity managed by the operator (never touched here);
2. a CHAL/vSource contract identity (raw Ed25519, signs frozen v1 documents);
3. a TLS transport identity (EC P-256, used only for Unisync mTLS sockets).

All private keys are generated node-locally inside an owner-controlled
mode-0700 state directory, stored as mode-0600 regular files, and never
returned, logged, or serialized by any function in this module.  Enrollment
exports only a certificate signing request; a certificate is installed only
after exact chain, SAN, and public-key binding checks.
"""

from __future__ import annotations

import hashlib
import ipaddress
import os
import platform
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from contracts.chal_vsource.v1.canonical import document_sha256
from contracts.chal_vsource.v1.models import ResourceInventory
from services.vsource import Ed25519DocumentSigner, sign_contract_document

from .mesh_common import (
    MeshSecurityError,
    b64url_decode,
    b64url_encode,
    compact_json,
    fsync_directory,
    normalize_san_set,
    read_private_file,
    require_identifier,
    require_sha256,
    safe_owned_directory,
    strict_json,
    wire_time,
    write_exclusive_private,
)

TLS_KEY_FILE = "tls-key.pem"
TLS_IDENTITY_FILE = "tls-identity.json"
TLS_CERTIFICATE_FILE = "tls-certificate.pem"
TLS_CA_FILE = "tls-ca.pem"
MESH_TRUST_FILE = "mesh-trust.json"
CONTRACT_KEY_FILE = "contract-ed25519.key"
CONTRACT_IDENTITY_FILE = "contract-identity.json"
TLS_IDENTITY_SCHEMA = "planetary.unisync.mesh_tls_identity.v1"
MESH_TRUST_SCHEMA = "planetary.unisync.mesh_trust.v1"
CONTRACT_IDENTITY_SCHEMA = "planetary.unisync.mesh_contract_identity.v1"
MAX_PEM_BYTES = 16 * 1024
_TLS_IDENTITY_FIELDS = frozenset(
    {"schema", "account_id", "node_id", "sans", "tls_public_key_sha256"}
)
_CONTRACT_IDENTITY_FIELDS = frozenset({"schema", "account_id", "node_id", "key_id"})
_MESH_TRUST_FIELDS = frozenset(
    {
        "schema",
        "account_id",
        "node_id",
        "controller_key_id",
        "controller_public_key_base64",
        "scheduler_key_id",
        "scheduler_public_key_base64",
    }
)
_TLS_STATE_FILES = (
    TLS_KEY_FILE,
    TLS_IDENTITY_FILE,
    TLS_CERTIFICATE_FILE,
    TLS_CA_FILE,
    MESH_TRUST_FILE,
)


def _entry_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _spki_sha256(public_key: Any) -> str:
    der = public_key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return hashlib.sha256(der).hexdigest()


def _require_p256(public_key: Any, label: str) -> None:
    if not isinstance(public_key, ec.EllipticCurvePublicKey) or not isinstance(
        public_key.curve, ec.SECP256R1
    ):
        raise MeshSecurityError(f"{label} must use an EC P-256 public key")


def _load_pem_bounded(pem: object, label: str) -> bytes:
    if not isinstance(pem, str) or not pem or len(pem) > MAX_PEM_BYTES:
        raise MeshSecurityError(f"{label} must be a nonempty bounded PEM string")
    return pem.encode("ascii", errors="strict")


def _certificate_sans(certificate: x509.Certificate) -> tuple[str, ...]:
    try:
        extension = certificate.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        )
    except x509.ExtensionNotFound as exc:
        raise MeshSecurityError("certificate has no subjectAltName extension") from exc
    values: list[str] = []
    for name in extension.value:
        if isinstance(name, x509.DNSName):
            values.append(name.value.lower())
        elif isinstance(name, x509.IPAddress):
            values.append(str(name.value))
        else:
            raise MeshSecurityError("certificate SANs must be DNS names or IP addresses")
    return normalize_san_set(values)


def validate_issued_certificate(
    certificate: x509.Certificate,
    issuer: x509.Certificate,
    *,
    node_id: str,
    expected_sans: tuple[str, ...],
    expected_spki_sha256: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Fail-closed verification of one issued node certificate against its CA."""

    current = (now or datetime.now(UTC)).astimezone(UTC)
    try:
        certificate.verify_directly_issued_by(issuer)
    except Exception as exc:
        raise MeshSecurityError("certificate is not signed by the expected CA") from exc
    try:
        issuer_constraints = issuer.extensions.get_extension_for_class(
            x509.BasicConstraints
        )
        leaf_constraints = certificate.extensions.get_extension_for_class(
            x509.BasicConstraints
        )
        extended_usage = certificate.extensions.get_extension_for_class(
            x509.ExtendedKeyUsage
        )
        key_usage = certificate.extensions.get_extension_for_class(x509.KeyUsage)
    except x509.ExtensionNotFound as exc:
        raise MeshSecurityError("certificate chain is missing required extensions") from exc
    if not issuer_constraints.value.ca:
        raise MeshSecurityError("issuer certificate is not a CA certificate")
    if leaf_constraints.value.ca or not leaf_constraints.critical:
        raise MeshSecurityError("node certificate must be a critical non-CA leaf")
    if (
        ExtendedKeyUsageOID.CLIENT_AUTH not in extended_usage.value
        or ExtendedKeyUsageOID.SERVER_AUTH not in extended_usage.value
    ):
        raise MeshSecurityError("node certificate must allow client and server auth")
    if not key_usage.value.digital_signature:
        raise MeshSecurityError("node certificate must allow digital signatures")
    common_names = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    if len(common_names) != 1 or common_names[0].value != node_id:
        raise MeshSecurityError("certificate subject does not bind the enrolled node")
    if certificate.not_valid_before_utc > current or current >= certificate.not_valid_after_utc:
        raise MeshSecurityError("certificate is outside its validity window")
    if (
        certificate.not_valid_before_utc < issuer.not_valid_before_utc
        or certificate.not_valid_after_utc > issuer.not_valid_after_utc
    ):
        raise MeshSecurityError("certificate validity exceeds the CA validity window")
    if _certificate_sans(certificate) != expected_sans:
        raise MeshSecurityError("certificate SANs do not match the enrolled SANs")
    _require_p256(certificate.public_key(), "node certificate")
    if _spki_sha256(certificate.public_key()) != expected_spki_sha256:
        raise MeshSecurityError("certificate public key does not match the node-local key")
    if certificate.serial_number <= 0:
        raise MeshSecurityError("certificate serial number must be positive")
    return {
        "certificate_sha256": hashlib.sha256(
            certificate.public_bytes(serialization.Encoding.DER)
        ).hexdigest(),
        "public_key_sha256": _spki_sha256(certificate.public_key()),
        "serial_hex": format(certificate.serial_number, "x"),
        "issuer": issuer.subject.rfc4514_string(),
        "not_before": wire_time(certificate.not_valid_before_utc),
        "not_after": wire_time(certificate.not_valid_after_utc),
        "sans": list(expected_sans),
    }


def create_tls_enrollment(
    state_dir: Path,
    *,
    account_id: str,
    node_id: str,
    sans: list[str] | tuple[str, ...],
) -> dict[str, Any]:
    """Generate the node-local TLS key and return only its public CSR."""

    require_identifier("account_id", account_id)
    require_identifier("node_id", node_id)
    normalized = normalize_san_set(sans)
    directory = safe_owned_directory(state_dir)
    for name in _TLS_STATE_FILES:
        if _entry_exists(directory / name):
            raise MeshSecurityError(
                "TLS enrollment state already exists; refusing to overwrite it"
            )
    private_key = ec.generate_private_key(ec.SECP256R1())
    key_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_key_sha256 = _spki_sha256(private_key.public_key())
    identity = {
        "schema": TLS_IDENTITY_SCHEMA,
        "account_id": account_id,
        "node_id": node_id,
        "sans": list(normalized),
        "tls_public_key_sha256": public_key_sha256,
    }
    write_exclusive_private(directory / TLS_KEY_FILE, key_pem)
    write_exclusive_private(
        directory / TLS_IDENTITY_FILE,
        (compact_json(identity) + "\n").encode("utf-8"),
    )
    fsync_directory(directory)
    san_entries: list[x509.GeneralName] = []
    for value in normalized:
        try:
            san_entries.append(x509.IPAddress(ipaddress.ip_address(value)))
        except ValueError:
            san_entries.append(x509.DNSName(value))
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, node_id)]))
        .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
        .sign(private_key, hashes.SHA256())
    )
    return {
        "csr_pem": csr.public_bytes(serialization.Encoding.PEM).decode("ascii"),
        "sans": list(normalized),
        "tls_public_key_sha256": public_key_sha256,
    }


def _load_tls_identity(
    state_dir: Path,
    *,
    account_id: str,
    node_id: str,
) -> tuple[Path, dict[str, Any], ec.EllipticCurvePrivateKey]:
    require_identifier("account_id", account_id)
    require_identifier("node_id", node_id)
    directory = safe_owned_directory(state_dir, create=False)
    key_exists = _entry_exists(directory / TLS_KEY_FILE)
    identity_exists = _entry_exists(directory / TLS_IDENTITY_FILE)
    if key_exists != identity_exists:
        raise MeshSecurityError("TLS identity state is partial; refusing to proceed")
    if not key_exists:
        raise MeshSecurityError("TLS identity has not been enrolled")
    identity = strict_json(read_private_file(directory / TLS_IDENTITY_FILE))
    if set(identity) != _TLS_IDENTITY_FIELDS:
        raise MeshSecurityError("TLS identity has unexpected fields")
    if (
        identity["schema"] != TLS_IDENTITY_SCHEMA
        or identity["account_id"] != account_id
        or identity["node_id"] != node_id
    ):
        raise MeshSecurityError("TLS identity does not match the requested account and node")
    stored_sans = normalize_san_set(identity["sans"])
    if list(stored_sans) != identity["sans"]:
        raise MeshSecurityError("TLS identity SANs are not canonical")
    key_pem = read_private_file(directory / TLS_KEY_FILE)
    try:
        private_key = serialization.load_pem_private_key(key_pem, password=None)
    except Exception as exc:
        raise MeshSecurityError("TLS private key is unreadable") from exc
    if not isinstance(private_key, ec.EllipticCurvePrivateKey) or not isinstance(
        private_key.curve, ec.SECP256R1
    ):
        raise MeshSecurityError("TLS private key must be EC P-256")
    if _spki_sha256(private_key.public_key()) != identity["tls_public_key_sha256"]:
        raise MeshSecurityError("TLS identity does not bind the node-local private key")
    return directory, identity, private_key


def install_certificate(
    state_dir: Path,
    *,
    account_id: str,
    node_id: str,
    certificate_pem: str,
    ca_pem: str,
    expected_certificate_sha256: str,
    expected_public_key_sha256: str,
) -> dict[str, Any]:
    """Install an issued certificate only after full local binding verification."""

    require_sha256("expected_certificate_sha256", expected_certificate_sha256)
    require_sha256("expected_public_key_sha256", expected_public_key_sha256)
    directory, identity, private_key = _load_tls_identity(
        state_dir, account_id=account_id, node_id=node_id
    )
    for name in (TLS_CERTIFICATE_FILE, TLS_CA_FILE):
        if _entry_exists(directory / name):
            raise MeshSecurityError(
                "a TLS certificate is already installed; rotation is a separate gate"
            )
    certificate_bytes = _load_pem_bounded(certificate_pem, "certificate_pem")
    ca_bytes = _load_pem_bounded(ca_pem, "ca_pem")
    try:
        certificate = x509.load_pem_x509_certificate(certificate_bytes)
        issuer = x509.load_pem_x509_certificate(ca_bytes)
    except Exception as exc:
        raise MeshSecurityError("certificate material is not valid PEM") from exc
    metadata = validate_issued_certificate(
        certificate,
        issuer,
        node_id=node_id,
        expected_sans=tuple(identity["sans"]),
        expected_spki_sha256=identity["tls_public_key_sha256"],
    )
    if metadata["certificate_sha256"] != expected_certificate_sha256:
        raise MeshSecurityError("issued certificate fingerprint does not match enrollment")
    if metadata["public_key_sha256"] != expected_public_key_sha256:
        raise MeshSecurityError("issued public-key fingerprint does not match enrollment")
    if _spki_sha256(private_key.public_key()) != metadata["public_key_sha256"]:
        raise MeshSecurityError("issued certificate does not bind the node-local key")
    write_exclusive_private(directory / TLS_CERTIFICATE_FILE, certificate_bytes)
    write_exclusive_private(directory / TLS_CA_FILE, ca_bytes)
    fsync_directory(directory)
    return metadata


def load_tls_credential_paths(
    state_dir: Path,
    *,
    account_id: str,
    node_id: str,
) -> tuple[dict[str, Path], dict[str, Any]]:
    """Re-verify the installed TLS state and return credential file paths."""

    directory, identity, private_key = _load_tls_identity(
        state_dir, account_id=account_id, node_id=node_id
    )
    certificate_bytes = read_private_file(directory / TLS_CERTIFICATE_FILE)
    ca_bytes = read_private_file(directory / TLS_CA_FILE)
    try:
        certificate = x509.load_pem_x509_certificate(certificate_bytes)
        issuer = x509.load_pem_x509_certificate(ca_bytes)
    except Exception as exc:
        raise MeshSecurityError("installed certificate material is not valid PEM") from exc
    metadata = validate_issued_certificate(
        certificate,
        issuer,
        node_id=node_id,
        expected_sans=tuple(identity["sans"]),
        expected_spki_sha256=identity["tls_public_key_sha256"],
    )
    if _spki_sha256(private_key.public_key()) != metadata["public_key_sha256"]:
        raise MeshSecurityError("installed certificate does not bind the node-local key")
    paths = {
        "ca_file": directory / TLS_CA_FILE,
        "cert_file": directory / TLS_CERTIFICATE_FILE,
        "key_file": directory / TLS_KEY_FILE,
    }
    return paths, metadata


def install_mesh_trust(
    state_dir: Path,
    *,
    account_id: str,
    node_id: str,
    controller_key_id: str,
    controller_public_key: bytes,
    scheduler_key_id: str,
    scheduler_public_key: bytes,
) -> dict[str, Any]:
    """Persist public controller/scheduler anchors delivered at enrollment."""

    require_identifier("account_id", account_id)
    require_identifier("node_id", node_id)
    require_identifier("controller_key_id", controller_key_id)
    require_identifier("scheduler_key_id", scheduler_key_id)
    if not isinstance(controller_public_key, bytes) or len(controller_public_key) != 32:
        raise MeshSecurityError("controller public key must be 32 raw Ed25519 bytes")
    if not isinstance(scheduler_public_key, bytes) or len(scheduler_public_key) != 32:
        raise MeshSecurityError("scheduler public key must be 32 raw Ed25519 bytes")
    directory = safe_owned_directory(state_dir, create=False)
    load_tls_credential_paths(directory, account_id=account_id, node_id=node_id)
    payload = {
        "schema": MESH_TRUST_SCHEMA,
        "account_id": account_id,
        "node_id": node_id,
        "controller_key_id": controller_key_id,
        "controller_public_key_base64": b64url_encode(controller_public_key),
        "scheduler_key_id": scheduler_key_id,
        "scheduler_public_key_base64": b64url_encode(scheduler_public_key),
    }
    write_exclusive_private(
        directory / MESH_TRUST_FILE,
        (compact_json(payload) + "\n").encode("utf-8"),
    )
    fsync_directory(directory)
    return payload


def load_mesh_trust(
    state_dir: Path,
    *,
    account_id: str,
    node_id: str,
) -> dict[str, Any]:
    """Load exact public trust anchors; missing or altered state fails closed."""

    directory = safe_owned_directory(state_dir, create=False)
    payload = strict_json(read_private_file(directory / MESH_TRUST_FILE))
    if set(payload) != _MESH_TRUST_FIELDS or payload["schema"] != MESH_TRUST_SCHEMA:
        raise MeshSecurityError("mesh trust state has unexpected fields")
    if payload["account_id"] != account_id or payload["node_id"] != node_id:
        raise MeshSecurityError("mesh trust state does not bind this account and node")
    controller_key_id = require_identifier(
        "controller_key_id", payload["controller_key_id"]
    )
    scheduler_key_id = require_identifier(
        "scheduler_key_id", payload["scheduler_key_id"]
    )
    return {
        "controller_key_id": controller_key_id,
        "controller_public_key": b64url_decode(
            payload["controller_public_key_base64"], expected_bytes=32
        ),
        "scheduler_key_id": scheduler_key_id,
        "scheduler_public_key": b64url_decode(
            payload["scheduler_public_key_base64"], expected_bytes=32
        ),
    }


@dataclass(frozen=True)
class MeshContractIdentity:
    """Node-local CHAL/vSource signing identity (separate from TLS and SSH)."""

    account_id: str
    node_id: str
    key_id: str
    signer: Ed25519DocumentSigner

    def public_key_bytes(self) -> bytes:
        return self.signer.private_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )

    def public_key_fingerprint(self) -> str:
        return hashlib.sha256(self.public_key_bytes()).hexdigest()


def load_or_create_contract_identity(
    state_dir: Path,
    *,
    account_id: str,
    node_id: str,
    create: bool = True,
) -> MeshContractIdentity:
    require_identifier("account_id", account_id)
    require_identifier("node_id", node_id)
    directory = safe_owned_directory(state_dir, create=create)
    key_id = f"key:unisync-mesh:{hashlib.sha256(node_id.encode('utf-8')).hexdigest()[:20]}"
    expected = {
        "schema": CONTRACT_IDENTITY_SCHEMA,
        "account_id": account_id,
        "node_id": node_id,
        "key_id": key_id,
    }
    key_path = directory / CONTRACT_KEY_FILE
    identity_path = directory / CONTRACT_IDENTITY_FILE
    key_exists = _entry_exists(key_path)
    identity_exists = _entry_exists(identity_path)
    if key_exists != identity_exists:
        raise MeshSecurityError("contract identity state is partial; refusing to proceed")
    if not key_exists:
        if not create:
            raise MeshSecurityError("contract identity has not been enrolled")
        private_key = Ed25519PrivateKey.generate()
        key_bytes = private_key.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        write_exclusive_private(key_path, key_bytes)
        write_exclusive_private(
            identity_path,
            (compact_json(expected) + "\n").encode("utf-8"),
        )
        fsync_directory(directory)
    stored = strict_json(read_private_file(identity_path))
    if set(stored) != _CONTRACT_IDENTITY_FIELDS or stored != expected:
        raise MeshSecurityError(
            "contract identity does not match the requested account and node"
        )
    key_bytes = read_private_file(key_path, expected_size=32)
    private_key = Ed25519PrivateKey.from_private_bytes(key_bytes)
    return MeshContractIdentity(
        account_id=account_id,
        node_id=node_id,
        key_id=key_id,
        signer=Ed25519DocumentSigner(key_id, private_key),
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
    raise MeshSecurityError(f"unsupported contract architecture: {value!r}")


def build_signed_inventory(
    identity: MeshContractIdentity,
    *,
    state_dir: Path,
) -> ResourceInventory:
    """Sign a lan_mtls resource inventory with the node contract identity."""

    cpu_count = max(1, os.cpu_count() or 1)
    if cpu_count > 4096:
        raise MeshSecurityError("logical CPU count exceeds the frozen contract bound")
    now = datetime.now(UTC).replace(microsecond=0)
    slug = hashlib.sha256(identity.node_id.encode("utf-8")).hexdigest()[:22]
    payload = {
        "schema": "planetary.vsource.inventory.v1",
        "inventory_id": f"inventory:mesh:{slug}",
        "node_id": identity.node_id,
        "account_id": identity.account_id,
        "trust_zone": "personal_cell",
        "public_key_fingerprint": identity.public_key_fingerprint(),
        "attestation": "unverified",
        "observed_at": wire_time(now),
        "ttl_seconds": 300,
        "health": "ready",
        "resources": {
            "allocatable": {
                "cpu_millicores": cpu_count * 1_000,
                "memory_bytes": _host_memory_bytes(),
                "storage_bytes": shutil.disk_usage(state_dir).free,
                "ingress_bps": 0,
                "egress_bps": 0,
            },
            "cpu": {
                "architecture": _architecture(),
                "logical_cores": cpu_count,
                "features": [],
            },
            "gpus": {},
        },
        "transports": ["lan_mtls"],
        "workload_kinds": ["evaluation"],
        "labels": {
            "power_class": "consumer",
            "thermal_policy": "balanced",
            "network_scope": "trusted_lan",
        },
    }
    return sign_contract_document(ResourceInventory, payload, identity.signer)


def inventory_wire(inventory: ResourceInventory) -> dict[str, Any]:
    return inventory.model_dump(mode="json", by_alias=True)


def inventory_sha256(inventory: ResourceInventory) -> str:
    return document_sha256(inventory)


def public_contract_record(identity: MeshContractIdentity) -> dict[str, Any]:
    """Public enrollment view of the contract identity (no key material)."""

    return {
        "key_id": identity.key_id,
        "public_key_base64": b64url_encode(identity.public_key_bytes()),
        "public_key_fingerprint": identity.public_key_fingerprint(),
        "account_id": identity.account_id,
        "node_id": identity.node_id,
    }
