"""Same-key certificate renewal: node-side CSR + CA renewal (F-030)."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.unisync.mesh_authority import (
    EnrollmentRegistry,
    MeshCertificateAuthority,
    MeshEnrollmentRecord,
    MeshSecurityError,
)
from services.unisync.mesh_identity import create_renewal_csr, create_tls_enrollment


def _record(issued, account="acct1", node="node1"):
    return MeshEnrollmentRecord(
        account_id=account,
        node_id=node,
        sans=issued.sans,
        certificate_sha256=issued.certificate_sha256,
        public_key_sha256=issued.public_key_sha256,
        serial_hex=issued.serial_hex,
        issuer=issued.issuer,
        not_before=issued.not_before,
        not_after=issued.not_after,
        enrolled_at=issued.not_before,
    )


def test_same_key_renewal_keeps_key_and_reissues(tmp_path: Path):
    node_dir = tmp_path / "node1"
    node_dir.mkdir(mode=0o700)
    ca = MeshCertificateAuthority.create("Test CA")

    enrollment = create_tls_enrollment(
        node_dir, account_id="acct1", node_id="node1", sans=["node1.local"]
    )
    issued = ca.issue_node_certificate(
        enrollment["csr_pem"], account_id="acct1", node_id="node1", sans=["node1.local"]
    )
    record = _record(issued)

    # The node produces a renewal CSR from its EXISTING key — same public key,
    # and no private key material leaves the node.
    renewal = create_renewal_csr(node_dir, account_id="acct1", node_id="node1")
    assert renewal["tls_public_key_sha256"] == enrollment["tls_public_key_sha256"]
    assert "PRIVATE KEY" not in renewal["csr_pem"]

    renewed = ca.renew_certificate(renewal["csr_pem"], existing_record=record)
    # Same key, fresh certificate (new serial).
    assert renewed.public_key_sha256 == issued.public_key_sha256
    assert renewed.serial_hex != issued.serial_hex
    assert renewed.certificate_sha256 != issued.certificate_sha256


def test_renewal_csr_requires_existing_enrollment(tmp_path: Path):
    empty = tmp_path / "unenrolled"
    empty.mkdir(mode=0o700)
    with pytest.raises(MeshSecurityError, match="not been enrolled"):
        create_renewal_csr(empty, account_id="acct1", node_id="node1")


def test_revoked_enrollment_cannot_be_renewed(tmp_path: Path):
    node_dir = tmp_path / "node1"
    node_dir.mkdir(mode=0o700)
    ca = MeshCertificateAuthority.create("Test CA")
    registry = EnrollmentRegistry(tmp_path / "registry")
    enrollment = create_tls_enrollment(
        node_dir, account_id="acct1", node_id="node1", sans=["node1.local"]
    )
    issued = ca.issue_node_certificate(
        enrollment["csr_pem"], account_id="acct1", node_id="node1", sans=["node1.local"]
    )
    record = _record(issued)
    registry.register(record)
    registry.revoke("acct1", "node1", reason="node_health")
    revoked = registry.record("acct1", "node1")
    renewal = create_renewal_csr(node_dir, account_id="acct1", node_id="node1")
    with pytest.raises(MeshSecurityError, match="cannot renew a revoked"):
        ca.renew_certificate(renewal["csr_pem"], existing_record=revoked)
