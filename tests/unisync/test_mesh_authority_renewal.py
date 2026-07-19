import os
import secrets
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography import x509
from cryptography.x509.oid import NameOID

from services.unisync.mesh_authority import (
    MeshCertificateAuthority,
    EnrollmentRegistry,
    MeshEnrollmentRecord,
    MeshSecurityError,
)
from services.unisync.mesh_identity import (
    create_tls_enrollment,
)

def test_mesh_authority_renewal(tmp_path: Path):
    ca = MeshCertificateAuthority.create("Test CA", validity_days=14)
    registry = EnrollmentRegistry(tmp_path / "registry")
    
    node_dir = tmp_path / "node1"
    node_dir.mkdir(mode=0o700)
    
    enrollment = create_tls_enrollment(
        node_dir,
        account_id="acct1",
        node_id="node1",
        sans=["node1.local"],
    )
    
    issued = ca.issue_node_certificate(
        enrollment["csr_pem"],
        account_id="acct1",
        node_id="node1",
        sans=["node1.local"],
        validity_days=7,
    )
    
    record = MeshEnrollmentRecord(
        account_id="acct1",
        node_id="node1",
        sans=("node1.local",),
        certificate_sha256=issued.certificate_sha256,
        public_key_sha256=issued.public_key_sha256,
        serial_hex=issued.serial_hex,
        issuer=issued.issuer,
        not_before=issued.not_before,
        not_after=issued.not_after,
        enrolled_at=issued.not_before,
    )
    registry.register(record)
    
    key_pem = (node_dir / "tls-key.pem").read_bytes()
    private_key = serialization.load_pem_private_key(key_pem, password=None)
    
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(
            x509.Name([
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "acct1"),
                x509.NameAttribute(NameOID.COMMON_NAME, "node1"),
            ])
        )
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("node1.local")]),
            critical=False,
        )
        .sign(private_key, hashes.SHA256())
    )
    new_csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode("ascii")
    
    renewed = ca.renew_certificate(
        new_csr_pem,
        existing_record=record,
        validity_days=14,
    )
    
    assert renewed.public_key_sha256 == record.public_key_sha256
    assert renewed.certificate_sha256 != record.certificate_sha256
    
    renewed_record = MeshEnrollmentRecord(
        account_id="acct1",
        node_id="node1",
        sans=("node1.local",),
        certificate_sha256=renewed.certificate_sha256,
        public_key_sha256=renewed.public_key_sha256,
        serial_hex=renewed.serial_hex,
        issuer=renewed.issuer,
        not_before=renewed.not_before,
        not_after=renewed.not_after,
        enrolled_at=record.enrolled_at,
    )
    
    registry.renew_peer(renewed_record)
    
    active = registry.active_peer("acct1", "node1")
    assert active.certificate_sha256 == renewed.certificate_sha256
    
    bad_key = ec.generate_private_key(ec.SECP256R1())
    bad_csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(
            x509.Name([
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "acct1"),
                x509.NameAttribute(NameOID.COMMON_NAME, "node1"),
            ])
        )
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("node1.local")]),
            critical=False,
        )
        .sign(bad_key, hashes.SHA256())
    )
    bad_csr_pem = bad_csr.public_bytes(serialization.Encoding.PEM).decode("ascii")
    
    with pytest.raises(MeshSecurityError, match="CSR public key does not match the active enrollment"):
        ca.renew_certificate(bad_csr_pem, existing_record=record)
        
    # test wrong SANs
    bad_san_csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(
            x509.Name([
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "acct1"),
                x509.NameAttribute(NameOID.COMMON_NAME, "node1"),
            ])
        )
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("wrong.local")]),
            critical=False,
        )
        .sign(private_key, hashes.SHA256())
    )
    bad_san_csr_pem = bad_san_csr.public_bytes(serialization.Encoding.PEM).decode("ascii")
    with pytest.raises(MeshSecurityError, match="CSR SANs do not match the active enrollment SANs"):
        ca.renew_certificate(bad_san_csr_pem, existing_record=record)
        
    registry.revoke("acct1", "node1", reason="compromised")
    revoked_record = registry.record("acct1", "node1")
    
    with pytest.raises(MeshSecurityError, match="cannot renew a revoked enrollment"):
        ca.renew_certificate(new_csr_pem, existing_record=revoked_record)
        
    with pytest.raises(MeshSecurityError, match="cannot renew a revoked enrollment"):
        registry.renew_peer(renewed_record)

