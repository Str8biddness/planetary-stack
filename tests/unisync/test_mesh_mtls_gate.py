from __future__ import annotations

import json
import os
import sqlite3
import stat
import sys
from dataclasses import replace
from datetime import UTC, datetime
from multiprocessing import get_context
from pathlib import Path

import pytest

pytest.importorskip("cryptography")

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from services.unisync import (
    AuthorizationError,
    ContentAddressedStore,
    InvalidFrameError,
    TLSConfigurationError,
    TransferContext,
    encode_frame,
)
from services.unisync import mesh_authority as mesh_authority_module
from services.unisync.mesh_authority import (
    EnrollmentRegistry,
    MeshCertificateAuthority,
    MeshEnrollmentRecord,
    REGISTRY_LOCK_FILE,
)
from services.unisync.mesh_common import (
    MeshSecurityError,
    b64url_decode,
    strict_json,
    wire_time,
)
from services.unisync.mesh_identity import (
    CONTRACT_IDENTITY_FILE,
    CONTRACT_KEY_FILE,
    MESH_TRUST_FILE,
    TLS_CA_FILE,
    TLS_CERTIFICATE_FILE,
    TLS_IDENTITY_FILE,
    TLS_KEY_FILE,
    create_tls_enrollment,
    install_certificate,
    install_mesh_trust,
    load_mesh_trust,
    load_or_create_contract_identity,
    load_tls_credential_paths,
)
from services.unisync.mesh_lease import LeaseUseStore, SignedLeaseValidator
from services.unisync.mesh_smoke import (
    LocalMeshCarrier,
    MeshNodeConfig,
    MeshSmokeConfig,
    run_mesh_mtls_smoke,
)
from services.unisync.tls import (
    EnrolledPeerIdentity,
    _derive_authenticated_peer_identity,
    _literal_allowed_address,
)


def _public_ed25519() -> bytes:
    return Ed25519PrivateKey.generate().public_key().public_bytes(
        Encoding.Raw,
        PublicFormat.Raw,
    )


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.lstat().st_mode)


def _record(account_id: str, node_id: str, issued, *, enrolled_at: str) -> MeshEnrollmentRecord:
    return MeshEnrollmentRecord(
        account_id=account_id,
        node_id=node_id,
        sans=issued.sans,
        certificate_sha256=issued.certificate_sha256,
        public_key_sha256=issued.public_key_sha256,
        serial_hex=issued.serial_hex,
        issuer=issued.issuer,
        not_before=issued.not_before,
        not_after=issued.not_after,
        enrolled_at=enrolled_at,
    )


def test_node_local_enrollment_registry_and_revocation_are_fail_closed(
    tmp_path: Path,
) -> None:
    account_id = "account:test:mesh"
    node_id = "node:test:source"
    state = tmp_path / "node-state"
    enrollment = create_tls_enrollment(
        state,
        account_id=account_id,
        node_id=node_id,
        sans=["source.test", "127.0.0.1"],
    )
    rendered = json.dumps(enrollment, sort_keys=True)
    assert "PRIVATE KEY" not in rendered
    assert _mode(state) == 0o700
    assert _mode(state / TLS_KEY_FILE) == 0o600
    assert _mode(state / TLS_IDENTITY_FILE) == 0o600

    csr = x509.load_pem_x509_csr(enrollment["csr_pem"].encode("ascii"))
    assert csr.is_signature_valid
    assert csr.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value == node_id
    assert (
        csr.subject.get_attributes_for_oid(x509.oid.NameOID.ORGANIZATION_NAME)[0].value
        == account_id
    )

    authority = MeshCertificateAuthority.create("Test Mesh CA")
    issued = authority.issue_node_certificate(
        enrollment["csr_pem"],
        account_id=account_id,
        node_id=node_id,
        sans=["127.0.0.1", "source.test"],
    )
    metadata = install_certificate(
        state,
        account_id=account_id,
        node_id=node_id,
        certificate_pem=issued.certificate_pem,
        ca_pem=issued.ca_pem,
        expected_certificate_sha256=issued.certificate_sha256,
        expected_public_key_sha256=issued.public_key_sha256,
    )
    controller_public = _public_ed25519()
    scheduler_public = _public_ed25519()
    install_mesh_trust(
        state,
        account_id=account_id,
        node_id=node_id,
        controller_key_id="key:controller:test",
        controller_public_key=controller_public,
        scheduler_key_id="key:scheduler:test",
        scheduler_public_key=scheduler_public,
    )
    paths, loaded_metadata = load_tls_credential_paths(
        state,
        account_id=account_id,
        node_id=node_id,
    )
    assert metadata == loaded_metadata
    assert paths["key_file"] == state / TLS_KEY_FILE
    assert load_mesh_trust(state, account_id=account_id, node_id=node_id) == {
        "controller_key_id": "key:controller:test",
        "controller_public_key": controller_public,
        "scheduler_key_id": "key:scheduler:test",
        "scheduler_public_key": scheduler_public,
    }
    for name in (TLS_CERTIFICATE_FILE, TLS_CA_FILE, MESH_TRUST_FILE):
        assert _mode(state / name) == 0o600

    registry_dir = tmp_path / "registry"
    registry = EnrollmentRegistry(registry_dir)
    record = _record(
        account_id,
        node_id,
        issued,
        enrolled_at=wire_time(datetime.now(UTC)),
    )
    registry.register(record)
    assert registry.active_peer(account_id, node_id).certificate_sha256 == issued.certificate_sha256
    assert _mode(registry_dir) == 0o700
    assert _mode(registry.path) == 0o600

    restarted = EnrollmentRegistry(registry_dir)
    restarted.revoke(account_id, node_id, reason="operator test revocation")
    restarted.revoke(account_id, node_id, reason="operator test revocation")
    with pytest.raises(AuthorizationError, match="revoked"):
        EnrollmentRegistry(registry_dir).active_peer(account_id, node_id)


def test_registry_lock_serializes_register_and_revoke_without_resurrection(
    tmp_path: Path,
) -> None:
    account_id = "account:test:mesh"
    authority = MeshCertificateAuthority.create("Concurrent Registry Test CA")

    def issued_record(node_id: str) -> MeshEnrollmentRecord:
        enrollment = create_tls_enrollment(
            tmp_path / node_id.rsplit(":", 1)[-1],
            account_id=account_id,
            node_id=node_id,
            sans=[f"{node_id.rsplit(':', 1)[-1]}.test"],
        )
        issued = authority.issue_node_certificate(
            enrollment["csr_pem"],
            account_id=account_id,
            node_id=node_id,
            sans=enrollment["sans"],
        )
        return _record(
            account_id,
            node_id,
            issued,
            enrolled_at=wire_time(datetime.now(UTC)),
        )

    first = issued_record("node:test:first")
    second = issued_record("node:test:second")
    registry_dir = tmp_path / "registry"
    EnrollmentRegistry(registry_dir).register(first)
    registering = EnrollmentRegistry(registry_dir)
    revoking = EnrollmentRegistry(registry_dir)
    process_context = get_context("fork")
    save_entered = process_context.Event()
    allow_save = process_context.Event()
    revoke_started = process_context.Event()
    revoke_lock_attempted = process_context.Event()
    revoke_lock_blocked = process_context.Event()
    revoke_lock_acquired_early = process_context.Event()
    revoke_finished = process_context.Event()
    results = process_context.Queue()
    original_save = registering._save

    def paused_save() -> None:
        save_entered.set()
        if not allow_save.wait(10):
            raise AssertionError("timed out waiting to release registry save")
        original_save()

    registering._save = paused_save  # type: ignore[method-assign]

    def register_second() -> None:
        try:
            registering.register(second)
            results.put(("register", "ok"))
        except BaseException as exc:
            results.put(("register", repr(exc)))

    def revoke_first() -> None:
        revoke_started.set()
        real_flock = mesh_authority_module.fcntl.flock

        def observed_flock(descriptor: int, operation: int) -> object:
            if operation == mesh_authority_module.fcntl.LOCK_EX:
                revoke_lock_attempted.set()
                try:
                    return real_flock(
                        descriptor,
                        mesh_authority_module.fcntl.LOCK_EX
                        | mesh_authority_module.fcntl.LOCK_NB,
                    )
                except BlockingIOError:
                    revoke_lock_blocked.set()
                    return real_flock(descriptor, operation)
                finally:
                    if not revoke_lock_blocked.is_set():
                        revoke_lock_acquired_early.set()
            return real_flock(descriptor, operation)

        mesh_authority_module.fcntl.flock = observed_flock
        try:
            revoking.revoke(account_id, first.node_id, reason="concurrent revocation")
            results.put(("revoke", "ok"))
        except BaseException as exc:
            results.put(("revoke", repr(exc)))
        finally:
            revoke_finished.set()

    register_process = process_context.Process(target=register_second)
    revoke_process = process_context.Process(target=revoke_first)
    register_process.start()
    revoke_started_by_parent = False
    try:
        assert save_entered.wait(2)
        revoke_process.start()
        revoke_started_by_parent = True
        assert revoke_started.wait(2)
        assert revoke_lock_attempted.wait(2)
        assert revoke_lock_blocked.wait(2)
        assert not revoke_lock_acquired_early.is_set()
        assert not revoke_finished.is_set()
    finally:
        allow_save.set()
        register_process.join(2)
        if revoke_started_by_parent:
            revoke_process.join(2)

    assert not register_process.is_alive()
    assert register_process.exitcode == 0
    assert revoke_started_by_parent
    assert not revoke_process.is_alive()
    assert revoke_process.exitcode == 0
    outcomes = sorted(results.get(timeout=2) for _ in range(2))
    assert outcomes == [("register", "ok"), ("revoke", "ok")]
    final = EnrollmentRegistry(registry_dir)
    with pytest.raises(AuthorizationError, match="revoked"):
        final.active_peer(account_id, first.node_id)
    assert final.active_peer(account_id, second.node_id).node_id == second.node_id
    assert _mode(registry_dir / REGISTRY_LOCK_FILE) == 0o600


def test_enrollment_rejects_changed_identity_substituted_key_and_symlink(
    tmp_path: Path,
) -> None:
    authority = MeshCertificateAuthority.create("Identity Test CA")
    first_state = tmp_path / "first"
    first = create_tls_enrollment(
        first_state,
        account_id="account:test:mesh",
        node_id="node:test:first",
        sans=["first.test"],
    )
    with pytest.raises(MeshSecurityError, match="subject"):
        authority.issue_node_certificate(
            first["csr_pem"],
            account_id="account:test:mesh",
            node_id="node:test:changed",
            sans=["first.test"],
        )
    with pytest.raises(MeshSecurityError, match="account"):
        authority.issue_node_certificate(
            first["csr_pem"],
            account_id="account:test:other",
            node_id="node:test:first",
            sans=["first.test"],
        )

    second_state = tmp_path / "second"
    second = create_tls_enrollment(
        second_state,
        account_id="account:test:mesh",
        node_id="node:test:second",
        sans=["second.test"],
    )
    substituted = authority.issue_node_certificate(
        second["csr_pem"],
        account_id="account:test:mesh",
        node_id="node:test:second",
        sans=["second.test"],
    )
    with pytest.raises(MeshSecurityError, match="node|SAN|public key"):
        install_certificate(
            first_state,
            account_id="account:test:mesh",
            node_id="node:test:first",
            certificate_pem=substituted.certificate_pem,
            ca_pem=substituted.ca_pem,
            expected_certificate_sha256=substituted.certificate_sha256,
            expected_public_key_sha256=substituted.public_key_sha256,
        )

    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    linked = tmp_path / "linked"
    os.symlink(real, linked)
    with pytest.raises(MeshSecurityError, match="symlink"):
        create_tls_enrollment(
            linked,
            account_id="account:test:mesh",
            node_id="node:test:linked",
            sans=["linked.test"],
        )


def test_tls_peer_matcher_rejects_registry_account_or_node_relabeling(
    tmp_path: Path,
) -> None:
    account_id = "account:test:alpha"
    node_id = "node:test:identity"
    enrollment = create_tls_enrollment(
        tmp_path / "identity",
        account_id=account_id,
        node_id=node_id,
        sans=["identity.test"],
    )
    issued = MeshCertificateAuthority.create("Peer Subject Test CA").issue_node_certificate(
        enrollment["csr_pem"],
        account_id=account_id,
        node_id=node_id,
        sans=enrollment["sans"],
    )
    certificate = x509.load_pem_x509_certificate(issued.certificate_pem.encode("ascii"))
    certificate_der = certificate.public_bytes(Encoding.DER)

    def peer(record_account_id: str, record_node_id: str) -> EnrolledPeerIdentity:
        return EnrolledPeerIdentity(
            account_id=record_account_id,
            node_id=record_node_id,
            sans=frozenset(issued.sans),
            certificate_sha256=issued.certificate_sha256,
            public_key_sha256=issued.public_key_sha256,
        )

    peer_certificate = {"subjectAltName": (("DNS", "identity.test"),)}
    with pytest.raises(AuthorizationError, match="not enrolled"):
        _derive_authenticated_peer_identity(
            peer_cert=peer_certificate,
            der_bytes=certificate_der,
            enrollments=(peer("account:test:beta", node_id),),
        )
    with pytest.raises(AuthorizationError, match="not enrolled"):
        _derive_authenticated_peer_identity(
            peer_cert=peer_certificate,
            der_bytes=certificate_der,
            enrollments=(peer(account_id, "node:test:other"),),
        )
    authenticated = _derive_authenticated_peer_identity(
        peer_cert=peer_certificate,
        der_bytes=certificate_der,
        enrollments=(peer(account_id, node_id),),
    )
    assert authenticated.account_id == account_id
    assert authenticated.node_id == node_id


def test_strict_mesh_json_and_frame_json_reject_ambiguity() -> None:
    with pytest.raises(MeshSecurityError, match="duplicate"):
        strict_json('{"schema":"one","schema":"two"}')
    with pytest.raises(MeshSecurityError, match="non-I-JSON"):
        strict_json('{"value":NaN}')
    with pytest.raises(InvalidFrameError, match="I-JSON"):
        encode_frame("error", extra={"unexpected": float("nan")})


@pytest.mark.parametrize("cidr", ["8.8.8.8/32", "0.0.0.0/0", "2000::/3"])
def test_declared_vpn_cidr_cannot_widen_listener_to_public_space(cidr: str) -> None:
    with pytest.raises(TLSConfigurationError, match="VPN CIDRs"):
        _literal_allowed_address("8.8.8.8", declared_vpn_cidrs=[cidr])


@pytest.fixture
def local_mesh_evidence(tmp_path: Path) -> tuple[dict[str, object], MeshSmokeConfig]:
    config = _local_mesh_config(tmp_path)
    return run_mesh_mtls_smoke(config, LocalMeshCarrier(timeout_seconds=15)), config


def _local_mesh_config(tmp_path: Path) -> MeshSmokeConfig:
    repo = Path(__file__).resolve().parents[2]
    source = MeshNodeConfig(
        node_id="node:test:source",
        python=sys.executable,
        repo=str(repo),
        state_dir=str(tmp_path / "source"),
        tls_sans=("source.test",),
        ssh_alias=None,
        ssh_host_fingerprint=None,
    )
    destination = MeshNodeConfig(
        node_id="node:test:destination",
        python=sys.executable,
        repo=str(repo),
        state_dir=str(tmp_path / "destination"),
        tls_sans=("127.0.0.1",),
        ssh_alias=None,
        ssh_host_fingerprint=None,
    )
    return MeshSmokeConfig(
        account_id="account:test:mesh",
        subject_id="subject:test:owner",
        carrier="local",
        known_hosts=None,
        identity_file=None,
        timeout_seconds=15,
        object_bytes=4096,
        lease_ttl_seconds=90,
        registry_dir=tmp_path / "registry",
        state_db=tmp_path / "vsource.sqlite3",
        output=tmp_path / "evidence.json",
        source=source,
        destination=destination,
        bind_address="127.0.0.1",
        port=0,
        server_hostname="127.0.0.1",
        declared_vpn_cidrs=(),
    )


class _FailingServeCarrier(LocalMeshCarrier):
    def start_serve(self, *args: object, **kwargs: object) -> object:
        raise MeshSecurityError("injected serve startup failure")


def test_transfer_start_failure_durably_revokes_allocated_lease(tmp_path: Path) -> None:
    config = _local_mesh_config(tmp_path)
    with pytest.raises(MeshSecurityError, match="injected serve startup failure"):
        run_mesh_mtls_smoke(
            config,
            _FailingServeCarrier(timeout_seconds=config.timeout_seconds),
        )

    with sqlite3.connect(config.state_db) as connection:
        rows = connection.execute(
            "SELECT state, terminal_state FROM leases"
        ).fetchall()
    assert rows == [("revoked", "revoked")]


def test_real_tcp_tls13_gate_binds_signed_request_lease_and_both_peers(
    local_mesh_evidence: tuple[dict[str, object], MeshSmokeConfig],
) -> None:
    evidence, config = local_mesh_evidence
    transfer = evidence["transfer"]
    assert isinstance(transfer, dict)
    send_result = transfer["send_result"]
    serve_result = transfer["serve_result"]
    assert send_result["negotiated_tls_version"] == "TLSv1.3"
    assert send_result["transport_id"] == "lan_mtls"
    assert serve_result["received"] is True
    assert "client_identity_bound" in serve_result["audit_events"]
    assert transfer["verified_receipt_sha256"] == send_result["verified_receipt_sha256"]

    digest = transfer["object_sha256"]
    source = ContentAddressedStore(Path(config.source.state_dir) / "outbox")
    destination = ContentAddressedStore(Path(config.destination.state_dir) / "inbox")
    assert source.read_bytes(digest) == destination.read_bytes(digest)
    assert len(source.read_bytes(digest)) == config.object_bytes
    assert evidence["claims"]["workload_bytes_generated_on_source_node"] is True
    assert evidence["claims"]["workload_bytes_provisioned_to_source_via_bootstrap"] is False

    for node in (config.source, config.destination):
        state = Path(node.state_dir)
        assert _mode(state / "lease-use.json") == 0o600
        use_state = strict_json((state / "lease-use.json").read_bytes())
        assert use_state["records"][0]["state"] == "completed"


def test_signed_request_membership_pinned_authority_and_replay_fail_closed(
    local_mesh_evidence: tuple[dict[str, object], MeshSmokeConfig],
) -> None:
    evidence, config = local_mesh_evidence
    documents = evidence["documents"]
    trust = evidence["trust_bundle"]
    transfer = evidence["transfer"]
    context = TransferContext.from_wire(transfer["transfer_context"])
    scheduler_public = b64url_decode(
        trust["scheduler_public_key_base64"], expected_bytes=32
    )
    controller_public = b64url_decode(
        trust["controller_public_key_base64"], expected_bytes=32
    )
    SignedLeaseValidator(
        lease_wire=documents["active_lease"],
        request_wire=documents["request"],
        scheduler_key_id=trust["scheduler_key_id"],
        scheduler_public_key=scheduler_public,
        controller_key_id=trust["controller_key_id"],
        controller_public_key=controller_public,
        expected_context=context,
    )

    with pytest.raises(AuthorizationError, match="content reference"):
        SignedLeaseValidator(
            lease_wire=documents["active_lease"],
            request_wire=documents["request"],
            scheduler_key_id=trust["scheduler_key_id"],
            scheduler_public_key=scheduler_public,
            controller_key_id=trust["controller_key_id"],
            controller_public_key=controller_public,
            expected_context=replace(context, object_sha256="f" * 64),
        )
    with pytest.raises(AuthorizationError, match="signature"):
        SignedLeaseValidator(
            lease_wire=documents["active_lease"],
            request_wire=documents["request"],
            scheduler_key_id=trust["scheduler_key_id"],
            scheduler_public_key=_public_ed25519(),
            controller_key_id=trust["controller_key_id"],
            controller_public_key=controller_public,
            expected_context=context,
        )

    destination_use = LeaseUseStore(
        Path(config.destination.state_dir),
        account_id=config.account_id,
        node_id=config.destination.node_id,
    )
    with pytest.raises(AuthorizationError, match="already admitted"):
        destination_use.begin(context)


def test_contract_and_tls_private_keys_are_distinct(tmp_path: Path) -> None:
    state = tmp_path / "identity"
    create_tls_enrollment(
        state,
        account_id="account:test:mesh",
        node_id="node:test:identity",
        sans=["identity.test"],
    )
    load_or_create_contract_identity(
        state,
        account_id="account:test:mesh",
        node_id="node:test:identity",
    )
    assert (state / TLS_KEY_FILE).read_bytes() != (state / CONTRACT_KEY_FILE).read_bytes()
    assert _mode(state / CONTRACT_KEY_FILE) == 0o600
    assert _mode(state / CONTRACT_IDENTITY_FILE) == 0o600
