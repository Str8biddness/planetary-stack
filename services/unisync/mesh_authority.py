"""Coordinator-side certificate issuing and persistent enrollment registry.

The issuing CA private key exists only inside the coordinator process; nothing
in this module serializes, returns, or logs it.  Nodes submit certificate
signing requests; certificates are issued only after CSR signature, subject,
SAN, and key-type verification, and peers become usable only through the
persistent registry, which fails closed on unknown, mismatched, expired, or
revoked entries.

This is the gate-scoped issuer for the private-mesh mTLS smoke test.
Production CA operations (HSM custody, rotation, renewal, CRL/OCSP
distribution) are explicit non-claims and remain separate gates.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import stat
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from .errors import AuthorizationError
from .mesh_common import (
    SERIAL_HEX_RE,
    MeshSecurityError,
    certificate_not_valid_after_utc,
    compact_json,
    fsync_directory,
    normalize_san_set,
    owned_file_lock,
    parse_wire_time,
    read_private_file,
    require_identifier,
    require_sha256,
    safe_owned_directory,
    strict_json,
    wire_time,
    write_exclusive_private,
)
from .mesh_identity import MAX_PEM_BYTES, validate_issued_certificate
from .tls import EnrolledPeerIdentity

REGISTRY_FILE = "enrollments.json"
REGISTRY_LOCK_FILE = "enrollments.lock"
REGISTRY_SCHEMA = "planetary.unisync.mesh_enrollment_registry.v1"
RECORD_SCHEMA = "planetary.unisync.mesh_enrollment_record.v1"
_RECORD_FIELDS = frozenset(
    {
        "schema",
        "account_id",
        "node_id",
        "sans",
        "certificate_sha256",
        "public_key_sha256",
        "serial_hex",
        "issuer",
        "not_before",
        "not_after",
        "status",
        "revocation_reason",
        "enrolled_at",
    }
)
_STATUSES = frozenset({"active", "revoked"})
MAX_REGISTRY_BYTES = 1024 * 1024
MAX_ISSUE_VALIDITY_DAYS = 30


@dataclass(frozen=True)
class IssuedCertificate:
    """Public result of issuing one node certificate (no key material)."""

    certificate_pem: str
    ca_pem: str
    certificate_sha256: str
    public_key_sha256: str
    serial_hex: str
    issuer: str
    not_before: str
    not_after: str
    sans: tuple[str, ...]


class MeshCertificateAuthority:
    """In-process EC P-256 issuing CA for one mesh enrollment run."""

    def __init__(self, private_key: ec.EllipticCurvePrivateKey, certificate: x509.Certificate) -> None:
        self._private_key = private_key
        self._certificate = certificate

    @classmethod
    def create(cls, common_name: str, *, validity_days: int = 14) -> "MeshCertificateAuthority":
        if not isinstance(common_name, str) or not 3 <= len(common_name) <= 64:
            raise MeshSecurityError("CA common name must be a short nonempty string")
        if not 1 <= validity_days <= MAX_ISSUE_VALIDITY_DAYS:
            raise MeshSecurityError("CA validity must be between 1 and 30 days")
        private_key = ec.generate_private_key(ec.SECP256R1())
        now = datetime.now(UTC)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
        certificate = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=validity_days))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=False,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=True,
                    crl_sign=True,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(private_key.public_key()),
                critical=False,
            )
            .sign(private_key, hashes.SHA256())
        )
        return cls(private_key, certificate)

    @property
    def ca_pem(self) -> str:
        return self._certificate.public_bytes(serialization.Encoding.PEM).decode("ascii")

    def issue_node_certificate(
        self,
        csr_pem: str,
        *,
        account_id: str,
        node_id: str,
        sans: list[str] | tuple[str, ...],
        validity_days: int = 7,
    ) -> IssuedCertificate:
        require_identifier("account_id", account_id)
        require_identifier("node_id", node_id)
        expected_sans = normalize_san_set(sans)
        if not 1 <= validity_days <= MAX_ISSUE_VALIDITY_DAYS:
            raise MeshSecurityError("certificate validity must be between 1 and 30 days")
        if not isinstance(csr_pem, str) or not csr_pem or len(csr_pem) > MAX_PEM_BYTES:
            raise MeshSecurityError("CSR must be a nonempty bounded PEM string")
        try:
            csr = x509.load_pem_x509_csr(csr_pem.encode("ascii", errors="strict"))
        except Exception as exc:
            raise MeshSecurityError("CSR is not valid PEM") from exc
        if not csr.is_signature_valid:
            raise MeshSecurityError("CSR signature is invalid")
        common_names = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        if len(common_names) != 1 or common_names[0].value != node_id:
            raise MeshSecurityError("CSR subject does not bind the enrolling node")
        account_names = csr.subject.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)
        if len(account_names) != 1 or account_names[0].value != account_id:
            raise MeshSecurityError("CSR subject does not bind the enrolling account")
        public_key = csr.public_key()
        if not isinstance(public_key, ec.EllipticCurvePublicKey) or not isinstance(
            public_key.curve, ec.SECP256R1
        ):
            raise MeshSecurityError("CSR public key must be EC P-256")
        try:
            csr_san = csr.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        except x509.ExtensionNotFound as exc:
            raise MeshSecurityError("CSR must carry a subjectAltName extension") from exc
        csr_values: list[str] = []
        for name in csr_san.value:
            if isinstance(name, x509.DNSName):
                csr_values.append(name.value.lower())
            elif isinstance(name, x509.IPAddress):
                csr_values.append(str(name.value))
            else:
                raise MeshSecurityError("CSR SANs must be DNS names or IP addresses")
        if normalize_san_set(csr_values) != expected_sans:
            raise MeshSecurityError("CSR SANs do not match the declared node SANs")
        now = datetime.now(UTC)
        certificate = (
            x509.CertificateBuilder()
            .subject_name(csr.subject)
            .issuer_name(self._certificate.subject)
            .public_key(public_key)
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(
                min(
                    now + timedelta(days=validity_days),
                    certificate_not_valid_after_utc(self._certificate),
                )
            )
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(csr_san.value, critical=False)
            .add_extension(
                x509.ExtendedKeyUsage(
                    [ExtendedKeyUsageOID.CLIENT_AUTH, ExtendedKeyUsageOID.SERVER_AUTH]
                ),
                critical=False,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(self._private_key, hashes.SHA256())
        )
        metadata = validate_issued_certificate(
            certificate,
            self._certificate,
            account_id=account_id,
            node_id=node_id,
            expected_sans=expected_sans,
            expected_spki_sha256=hashlib.sha256(
                public_key.public_bytes(
                    serialization.Encoding.DER,
                    serialization.PublicFormat.SubjectPublicKeyInfo,
                )
            ).hexdigest(),
        )
        return IssuedCertificate(
            certificate_pem=certificate.public_bytes(serialization.Encoding.PEM).decode("ascii"),
            ca_pem=self.ca_pem,
            certificate_sha256=metadata["certificate_sha256"],
            public_key_sha256=metadata["public_key_sha256"],
            serial_hex=metadata["serial_hex"],
            issuer=metadata["issuer"],
            not_before=metadata["not_before"],
            not_after=metadata["not_after"],
            sans=expected_sans,
        )


@dataclass(frozen=True)
class MeshEnrollmentRecord:
    """One persistent enrollment binding for a mesh TLS peer."""

    account_id: str
    node_id: str
    sans: tuple[str, ...]
    certificate_sha256: str
    public_key_sha256: str
    serial_hex: str
    issuer: str
    not_before: str
    not_after: str
    status: str = "active"
    revocation_reason: str | None = None
    enrolled_at: str = ""

    def __post_init__(self) -> None:
        require_identifier("account_id", self.account_id)
        require_identifier("node_id", self.node_id)
        if normalize_san_set(self.sans) != tuple(self.sans):
            raise MeshSecurityError("enrollment SANs must be a canonical sorted tuple")
        require_sha256("certificate_sha256", self.certificate_sha256)
        require_sha256("public_key_sha256", self.public_key_sha256)
        if not isinstance(self.serial_hex, str) or not SERIAL_HEX_RE.fullmatch(self.serial_hex):
            raise MeshSecurityError("enrollment serial must be lowercase hex")
        if not isinstance(self.issuer, str) or not 1 <= len(self.issuer) <= 256:
            raise MeshSecurityError("enrollment issuer must be a bounded string")
        parse_wire_time(self.not_before)
        parse_wire_time(self.not_after)
        if parse_wire_time(self.not_before) >= parse_wire_time(self.not_after):
            raise MeshSecurityError("enrollment validity window is empty")
        if self.status not in _STATUSES:
            raise MeshSecurityError("enrollment status must be active or revoked")
        if (self.status == "revoked") != (self.revocation_reason is not None):
            raise MeshSecurityError("revocation_reason must accompany exactly revoked status")
        if self.revocation_reason is not None and not (
            isinstance(self.revocation_reason, str) and 1 <= len(self.revocation_reason) <= 256
        ):
            raise MeshSecurityError("revocation_reason must be a bounded string")
        parse_wire_time(self.enrolled_at)

    def to_wire(self) -> dict[str, Any]:
        return {
            "schema": RECORD_SCHEMA,
            "account_id": self.account_id,
            "node_id": self.node_id,
            "sans": list(self.sans),
            "certificate_sha256": self.certificate_sha256,
            "public_key_sha256": self.public_key_sha256,
            "serial_hex": self.serial_hex,
            "issuer": self.issuer,
            "not_before": self.not_before,
            "not_after": self.not_after,
            "status": self.status,
            "revocation_reason": self.revocation_reason,
            "enrolled_at": self.enrolled_at,
        }

    @classmethod
    def from_wire(cls, payload: object) -> "MeshEnrollmentRecord":
        if not isinstance(payload, dict) or set(payload) != _RECORD_FIELDS:
            raise MeshSecurityError("enrollment record has unexpected fields")
        if payload["schema"] != RECORD_SCHEMA:
            raise MeshSecurityError("enrollment record schema is unsupported")
        sans = payload["sans"]
        if not isinstance(sans, list):
            raise MeshSecurityError("enrollment SANs must be a list")
        return cls(
            account_id=payload["account_id"],
            node_id=payload["node_id"],
            sans=tuple(sans),
            certificate_sha256=payload["certificate_sha256"],
            public_key_sha256=payload["public_key_sha256"],
            serial_hex=payload["serial_hex"],
            issuer=payload["issuer"],
            not_before=payload["not_before"],
            not_after=payload["not_after"],
            status=payload["status"],
            revocation_reason=payload["revocation_reason"],
            enrolled_at=payload["enrolled_at"],
        )

    def peer_identity(self) -> EnrolledPeerIdentity:
        return EnrolledPeerIdentity(
            account_id=self.account_id,
            node_id=self.node_id,
            sans=frozenset(self.sans),
            certificate_sha256=self.certificate_sha256,
            public_key_sha256=self.public_key_sha256,
        )


class EnrollmentRegistry:
    """Persistent, atomic, fail-closed registry of enrolled mesh TLS peers."""

    def __init__(self, directory: Path) -> None:
        self._directory = safe_owned_directory(Path(directory))
        self._path = self._directory / REGISTRY_FILE
        self._records: dict[tuple[str, str], MeshEnrollmentRecord] = {}
        with owned_file_lock(
            self._directory, REGISTRY_LOCK_FILE, exclusive=True
        ):
            try:
                self._path.lstat()
                exists = True
            except FileNotFoundError:
                exists = False
            if exists:
                self._load()
            else:
                self._save()

    @property
    def path(self) -> Path:
        return self._path

    def _load(self) -> None:
        raw = read_private_file(self._path, max_bytes=MAX_REGISTRY_BYTES)
        if len(raw) > MAX_REGISTRY_BYTES:
            raise MeshSecurityError("enrollment registry exceeds its size bound")
        payload = strict_json(raw)
        if set(payload) != {"schema", "records"}:
            raise MeshSecurityError("enrollment registry has unexpected fields")
        if payload["schema"] != REGISTRY_SCHEMA:
            raise MeshSecurityError("enrollment registry schema is unsupported")
        if not isinstance(payload["records"], list):
            raise MeshSecurityError("enrollment registry records must be a list")
        records: dict[tuple[str, str], MeshEnrollmentRecord] = {}
        certificate_digests: set[str] = set()
        key_digests: set[str] = set()
        for item in payload["records"]:
            record = MeshEnrollmentRecord.from_wire(item)
            key = (record.account_id, record.node_id)
            if key in records:
                raise MeshSecurityError("enrollment registry contains duplicate node records")
            if record.certificate_sha256 in certificate_digests:
                raise MeshSecurityError("enrollment registry reuses a certificate fingerprint")
            if record.public_key_sha256 in key_digests:
                raise MeshSecurityError("enrollment registry reuses a public-key fingerprint")
            certificate_digests.add(record.certificate_sha256)
            key_digests.add(record.public_key_sha256)
            records[key] = record
        self._records = records

    def _save(self) -> None:
        payload = {
            "schema": REGISTRY_SCHEMA,
            "records": [
                record.to_wire()
                for _, record in sorted(self._records.items())
            ],
        }
        encoded = (compact_json(payload) + "\n").encode("utf-8")
        if len(encoded) > MAX_REGISTRY_BYTES:
            raise MeshSecurityError("enrollment registry exceeds its size bound")
        temp_path = self._directory / f".{REGISTRY_FILE}.{secrets.token_hex(8)}.tmp"
        write_exclusive_private(temp_path, encoded)
        try:
            os.replace(temp_path, self._path)
        except OSError:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
            raise
        fsync_directory(self._directory)
        if stat.S_IMODE(self._path.lstat().st_mode) != 0o600:
            raise MeshSecurityError("enrollment registry file mode is not 0600")

    def register(self, record: MeshEnrollmentRecord) -> None:
        """Explicitly add one peer; duplicates and substitutions fail closed."""

        with owned_file_lock(
            self._directory, REGISTRY_LOCK_FILE, exclusive=True
        ):
            self._load()
            key = (record.account_id, record.node_id)
            if key in self._records:
                raise MeshSecurityError(
                    "node is already enrolled; re-enrollment/rotation is a separate gate"
                )
            for existing in self._records.values():
                if existing.certificate_sha256 == record.certificate_sha256:
                    raise MeshSecurityError("certificate fingerprint is already enrolled")
                if existing.public_key_sha256 == record.public_key_sha256:
                    raise MeshSecurityError("public-key fingerprint is already enrolled")
            previous = self._records
            self._records = {**previous, key: record}
            try:
                self._save()
            except BaseException:
                self._records = previous
                raise

    def revoke(self, account_id: str, node_id: str, *, reason: str) -> None:
        with owned_file_lock(
            self._directory, REGISTRY_LOCK_FILE, exclusive=True
        ):
            self._load()
            key = (account_id, node_id)
            record = self._records.get(key)
            if record is None:
                raise MeshSecurityError("cannot revoke an unknown enrollment")
            if record.status != "active":
                if record.revocation_reason == reason:
                    return
                raise MeshSecurityError("enrollment is already revoked with a different reason")
            replacement = MeshEnrollmentRecord(
                **{
                    **{
                        field: getattr(record, field)
                        for field in (
                            "account_id",
                            "node_id",
                            "sans",
                            "certificate_sha256",
                            "public_key_sha256",
                            "serial_hex",
                            "issuer",
                            "not_before",
                            "not_after",
                            "enrolled_at",
                        )
                    },
                    "status": "revoked",
                    "revocation_reason": reason,
                }
            )
            previous = self._records
            self._records = {**previous, key: replacement}
            try:
                self._save()
            except BaseException:
                self._records = previous
                raise

    def active_peer(
        self,
        account_id: str,
        node_id: str,
        *,
        now: datetime | None = None,
    ) -> EnrolledPeerIdentity:
        """Return the active enrollment or fail closed."""

        with owned_file_lock(
            self._directory, REGISTRY_LOCK_FILE, exclusive=False
        ):
            self._load()
            record = self._records.get((account_id, node_id))
            if record is None:
                raise AuthorizationError("peer is not enrolled in the mesh registry")
            if record.status != "active":
                raise AuthorizationError("peer enrollment is revoked")
            current = (now or datetime.now(UTC)).astimezone(UTC)
            if current < parse_wire_time(record.not_before) or current >= parse_wire_time(
                record.not_after
            ):
                raise AuthorizationError("peer enrollment is outside its validity window")
            return record.peer_identity()

    def record(self, account_id: str, node_id: str) -> MeshEnrollmentRecord:
        with owned_file_lock(
            self._directory, REGISTRY_LOCK_FILE, exclusive=False
        ):
            self._load()
            record = self._records.get((account_id, node_id))
            if record is None:
                raise AuthorizationError("peer is not enrolled in the mesh registry")
            return record

    def snapshot_wire(self) -> list[dict[str, Any]]:
        with owned_file_lock(
            self._directory, REGISTRY_LOCK_FILE, exclusive=False
        ):
            self._load()
            return [record.to_wire() for _, record in sorted(self._records.items())]
