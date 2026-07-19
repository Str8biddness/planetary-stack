import pytest
from datetime import datetime, UTC, timedelta
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from services.unisync.mesh_identity import check_certificate_expiry
from services.unisync.mesh_common import MeshSecurityError

def generate_cert(days_valid: int) -> str:
    private_key = ec.generate_private_key(ec.SECP256R1())
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "test-node"),
    ])
    now = datetime.now(UTC)
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        private_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        now - timedelta(days=1)
    ).not_valid_after(
        now + timedelta(days=days_valid)
    ).sign(private_key, hashes.SHA256())
    
    return cert.public_bytes(serialization.Encoding.PEM).decode("ascii")

def test_check_certificate_expiry():
    # Test valid cert
    cert_pem = generate_cert(10)
    days = check_certificate_expiry(cert_pem)
    assert days == 9 or days == 10
    
    # Test exactly 1 day
    cert_pem_1 = generate_cert(1)
    days_1 = check_certificate_expiry(cert_pem_1)
    assert days_1 == 0 or days_1 == 1

def test_check_certificate_expiry_expired():
    cert_pem = generate_cert(-1)
    with pytest.raises(MeshSecurityError, match="certificate is already expired"):
        check_certificate_expiry(cert_pem)

def test_invalid_pem():
    with pytest.raises(MeshSecurityError, match="certificate material is not valid PEM"):
        check_certificate_expiry("invalid pem data")

def test_empty_pem():
    with pytest.raises(MeshSecurityError, match="certificate_pem must be a nonempty bounded PEM string"):
        check_certificate_expiry("")
