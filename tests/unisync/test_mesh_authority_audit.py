import logging
import pytest
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from services.unisync.mesh_authority import (
    MeshCertificateAuthority,
    EnrollmentRegistry,
    MeshEnrollmentRecord,
    MeshSecurityError
)

def test_audit_logs_on_register(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    registry = EnrollmentRegistry(tmp_path)
    
    # Fake record
    record = MeshEnrollmentRecord(
        account_id="acct-1",
        node_id="node-1",
        sans=("node-1.local",),
        certificate_sha256="a"*64,
        public_key_sha256="b"*64,
        serial_hex="1234",
        issuer="CN=Test",
        not_before="2026-01-01T00:00:00Z",
        not_after="2027-01-01T00:00:00Z",
        enrolled_at="2026-01-01T00:00:00Z",
    )
    
    with caplog.at_level(logging.INFO):
        registry.register(record)
        
    assert "Enrollment registered" in caplog.text
    assert "Enrollment registered" in caplog.text
    assert caplog.records[-1].account_id == "acct-1"
    assert caplog.records[-1].node_id == "node-1"

def test_audit_logs_on_rejection(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    registry = EnrollmentRegistry(tmp_path)
    
    record = MeshEnrollmentRecord(
        account_id="acct-1",
        node_id="node-1",
        sans=("node-1.local",),
        certificate_sha256="a"*64,
        public_key_sha256="b"*64,
        serial_hex="1234",
        issuer="CN=Test",
        not_before="2026-01-01T00:00:00Z",
        not_after="2027-01-01T00:00:00Z",
        enrolled_at="2026-01-01T00:00:00Z",
    )
    
    registry.register(record)
    caplog.clear()
    
    with caplog.at_level(logging.WARNING):
        with pytest.raises(MeshSecurityError):
            registry.register(record)
            
    assert "Enrollment registration rejected" in caplog.text
    assert "Enrollment registration rejected" in caplog.text
    assert caplog.records[-1].reason == "node is already enrolled"

def test_audit_logs_on_revoke(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    registry = EnrollmentRegistry(tmp_path)
    
    record = MeshEnrollmentRecord(
        account_id="acct-1",
        node_id="node-1",
        sans=("node-1.local",),
        certificate_sha256="a"*64,
        public_key_sha256="b"*64,
        serial_hex="1234",
        issuer="CN=Test",
        not_before="2026-01-01T00:00:00Z",
        not_after="2027-01-01T00:00:00Z",
        enrolled_at="2026-01-01T00:00:00Z",
    )
    
    registry.register(record)
    caplog.clear()
    
    with caplog.at_level(logging.INFO):
        registry.revoke("acct-1", "node-1", reason="lost device")
        
    assert "Enrollment revoked" in caplog.text
    assert "Enrollment revoked" in caplog.text
    assert caplog.records[-1].reason == "lost device"
