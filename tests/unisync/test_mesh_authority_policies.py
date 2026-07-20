import pytest
from datetime import datetime, UTC
from pathlib import Path
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
from services.unisync.mesh_identity import create_tls_enrollment
from services.unisync.errors import AuthorizationError

def test_rotate_account_key():
    ca1 = MeshCertificateAuthority.create("Test CA 1")
    ca2 = ca1.rotate_account_key(validity_days=14)
    
    # Assert CA is different but valid
    assert ca1.ca_pem != ca2.ca_pem
    
    cert1 = x509.load_pem_x509_certificate(ca1.ca_pem.encode('ascii'))
    cert2 = x509.load_pem_x509_certificate(ca2.ca_pem.encode('ascii'))
    
    assert cert1.subject == cert2.subject
    assert cert2.issuer == cert1.subject
    
    # verify signature
    cert2_pub = cert1.public_key()
    assert isinstance(cert2_pub, ec.EllipticCurvePublicKey)
    cert2_pub.verify(cert2.signature, cert2.tbs_certificate_bytes, ec.ECDSA(cert2.signature_hash_algorithm))

def test_rotate_peer_key(tmp_path: Path):
    ca = MeshCertificateAuthority.create("Test CA")
    registry = EnrollmentRegistry(tmp_path / "registry")
    
    node_dir = tmp_path / "node1"
    node_dir.mkdir(mode=0o700)
    
    enrollment = create_tls_enrollment(node_dir, account_id="acct1", node_id="node1", sans=["node1.local"])
    
    issued = ca.issue_node_certificate(
        enrollment["csr_pem"],
        account_id="acct1",
        node_id="node1",
        sans=["node1.local"],
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
    
    # create new key
    new_dir = tmp_path / "node1_new"
    new_dir.mkdir(mode=0o700)
    enrollment2 = create_tls_enrollment(new_dir, account_id="acct1", node_id="node1", sans=["node1.local"])
    
    # Rotate
    rotated = ca.rotate_peer_key(
        enrollment2["csr_pem"],
        existing_record=record,
    )
    
    assert rotated.public_key_sha256 != record.public_key_sha256
    
    new_record = MeshEnrollmentRecord(
        account_id="acct1",
        node_id="node1",
        sans=("node1.local",),
        certificate_sha256=rotated.certificate_sha256,
        public_key_sha256=rotated.public_key_sha256,
        serial_hex=rotated.serial_hex,
        issuer=rotated.issuer,
        not_before=rotated.not_before,
        not_after=rotated.not_after,
        enrolled_at=record.enrolled_at,
    )
    
    registry.rotate_peer_key(new_record)
    
    active = registry.active_peer("acct1", "node1")
    assert active.public_key_sha256 == rotated.public_key_sha256

def test_transfer_ownership(tmp_path: Path):
    ca = MeshCertificateAuthority.create("Test CA")
    registry = EnrollmentRegistry(tmp_path / "registry")
    
    node_dir = tmp_path / "node1"
    node_dir.mkdir(mode=0o700)
    
    enrollment = create_tls_enrollment(node_dir, account_id="old_acct", node_id="node1", sans=["node1.local"])
    
    issued = ca.issue_node_certificate(
        enrollment["csr_pem"],
        account_id="old_acct",
        node_id="node1",
        sans=["node1.local"],
    )
    
    record = MeshEnrollmentRecord(
        account_id="old_acct",
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
    
    # New enrollment for new account (requires a new CSR because account_id is in it, usually new key or same key is fine, we'll use new key)
    new_dir = tmp_path / "node1_transfer"
    new_dir.mkdir(mode=0o700)
    enrollment_new = create_tls_enrollment(new_dir, account_id="new_acct", node_id="node1", sans=["node1.local"])
    
    issued_new = ca.issue_node_certificate(
        enrollment_new["csr_pem"],
        account_id="new_acct",
        node_id="node1",
        sans=["node1.local"],
    )
    
    new_record = MeshEnrollmentRecord(
        account_id="new_acct",
        node_id="node1",
        sans=("node1.local",),
        certificate_sha256=issued_new.certificate_sha256,
        public_key_sha256=issued_new.public_key_sha256,
        serial_hex=issued_new.serial_hex,
        issuer=issued_new.issuer,
        not_before=issued_new.not_before,
        not_after=issued_new.not_after,
        enrolled_at=issued_new.not_before,
    )
    
    registry.transfer_ownership(
        account_id="old_acct",
        node_id="node1",
        new_account_id="new_acct",
        new_record=new_record,
    )
    
    with pytest.raises(AuthorizationError):
        registry.active_peer("old_acct", "node1") # old is revoked
        
    old_record = registry.record("old_acct", "node1")
    assert old_record.status == "revoked"
    
    active = registry.active_peer("new_acct", "node1")
    assert active.account_id == "new_acct"
