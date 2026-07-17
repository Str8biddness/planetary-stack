from __future__ import annotations

import hashlib
import ipaddress
import ssl
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytest.importorskip("cryptography")

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from services.unisync import (
    AuthorizationError,
    BackpressureError,
    CancellationToken,
    ContentAddressedStore,
    EnrolledPeerIdentity,
    FRAME_ACK,
    FRAME_START,
    TLSConfigurationError,
    TLSCredentials,
    TrustedLanClient,
    TrustedLanServer,
    encode_frame,
)
from services.unisync.tls import _client_context, _server_context
from services.unisync.tls import _derive_authenticated_peer_identity
from services.unisync.tls import _require_peer_san

from .conftest import StrictValidator, make_context


@dataclass(frozen=True)
class CertMaterial:
    ca: Path
    server_cert: Path
    server_key: Path
    expired_server_cert: Path
    expired_server_key: Path
    client_cert: Path
    client_key: Path
    bad_client_cert: Path
    bad_client_key: Path


def _key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _name(common_name: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def _write_key(path: Path, key) -> None:
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    path.chmod(0o600)


def _write_cert(path: Path, cert: x509.Certificate) -> None:
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    path.chmod(0o600)


def _make_ca(common_name: str):
    key = _key()
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(_name(common_name))
        .issuer_name(_name(common_name))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=7))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    return key, cert


def _make_leaf(
    *,
    common_name: str,
    ca_key,
    ca_cert,
    dns_names: list[str],
    ip_addresses: list[str] | None = None,
    server: bool = False,
    client: bool = False,
    expired: bool = False,
):
    key = _key()
    now = datetime.now(timezone.utc)
    if expired:
        not_before = now - timedelta(days=5)
        not_after = now - timedelta(days=1)
    else:
        not_before = now - timedelta(minutes=5)
        not_after = now + timedelta(days=1)
    usages = []
    if server:
        usages.append(ExtendedKeyUsageOID.SERVER_AUTH)
    if client:
        usages.append(ExtendedKeyUsageOID.CLIENT_AUTH)
    san_entries = [x509.DNSName(name) for name in dns_names]
    for address in ip_addresses or []:
        san_entries.append(x509.IPAddress(ipaddress.ip_address(address)))
    cert = (
        x509.CertificateBuilder()
        .subject_name(_name(common_name))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
        .add_extension(x509.ExtendedKeyUsage(usages), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    return key, cert


@pytest.fixture
def certs(tmp_path) -> CertMaterial:
    ca_key, ca_cert = _make_ca("Unisync Test CA")
    bad_ca_key, bad_ca_cert = _make_ca("Unisync Unknown CA")
    server_key, server_cert = _make_leaf(
        common_name="server.test",
        ca_key=ca_key,
        ca_cert=ca_cert,
        dns_names=["server.test"],
        ip_addresses=["127.0.0.1"],
        server=True,
    )
    expired_key, expired_cert = _make_leaf(
        common_name="server.test",
        ca_key=ca_key,
        ca_cert=ca_cert,
        dns_names=["server.test"],
        ip_addresses=["127.0.0.1"],
        server=True,
        expired=True,
    )
    client_key, client_cert = _make_leaf(
        common_name="client.test",
        ca_key=ca_key,
        ca_cert=ca_cert,
        dns_names=["client.test"],
        client=True,
    )
    bad_client_key, bad_client_cert = _make_leaf(
        common_name="client.test",
        ca_key=bad_ca_key,
        ca_cert=bad_ca_cert,
        dns_names=["client.test"],
        client=True,
    )
    paths = {
        "ca": tmp_path / "ca.pem",
        "server_cert": tmp_path / "server.pem",
        "server_key": tmp_path / "server.key",
        "expired_server_cert": tmp_path / "expired-server.pem",
        "expired_server_key": tmp_path / "expired-server.key",
        "client_cert": tmp_path / "client.pem",
        "client_key": tmp_path / "client.key",
        "bad_client_cert": tmp_path / "bad-client.pem",
        "bad_client_key": tmp_path / "bad-client.key",
    }
    _write_cert(paths["ca"], ca_cert)
    _write_cert(paths["server_cert"], server_cert)
    _write_key(paths["server_key"], server_key)
    _write_cert(paths["expired_server_cert"], expired_cert)
    _write_key(paths["expired_server_key"], expired_key)
    _write_cert(paths["client_cert"], client_cert)
    _write_key(paths["client_key"], client_key)
    _write_cert(paths["bad_client_cert"], bad_client_cert)
    _write_key(paths["bad_client_key"], bad_client_key)
    return CertMaterial(**paths)


def _server_credentials(certs: CertMaterial, *, expired: bool = False) -> TLSCredentials:
    if expired:
        return TLSCredentials(
            ca_file=certs.ca,
            cert_file=certs.expired_server_cert,
            key_file=certs.expired_server_key,
        )
    return TLSCredentials(ca_file=certs.ca, cert_file=certs.server_cert, key_file=certs.server_key)


def _client_credentials(certs: CertMaterial, *, unknown_ca: bool = False) -> TLSCredentials:
    if unknown_ca:
        return TLSCredentials(ca_file=certs.ca, cert_file=certs.bad_client_cert, key_file=certs.bad_client_key)
    return TLSCredentials(ca_file=certs.ca, cert_file=certs.client_cert, key_file=certs.client_key)


def _cert_fingerprints(cert_path: Path) -> tuple[str, str]:
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    cert_der = cert.public_bytes(serialization.Encoding.DER)
    public_key_der = cert.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return hashlib.sha256(cert_der).hexdigest(), hashlib.sha256(public_key_der).hexdigest()


def _client_enrollment(
    certs: CertMaterial,
    *,
    account_id: str = "account:local",
    node_id: str = "node:source",
) -> EnrolledPeerIdentity:
    certificate_sha256, public_key_sha256 = _cert_fingerprints(certs.client_cert)
    return EnrolledPeerIdentity(
        account_id=account_id,
        node_id=node_id,
        sans=frozenset({"client.test"}),
        certificate_sha256=certificate_sha256,
        public_key_sha256=public_key_sha256,
    )


def _server_instance(tmp_path, certs: CertMaterial, *, expired: bool = False, **kwargs) -> TrustedLanServer:
    enrolled_client_identities = kwargs.pop("enrolled_client_identities", {_client_enrollment(certs)})
    return TrustedLanServer(
        bind_host="127.0.0.1",
        port=0,
        credentials=_server_credentials(certs, expired=expired),
        destination_root=tmp_path / "destination",
        validator=StrictValidator(),
        declared_listener_addresses={"127.0.0.1"},
        allowed_client_sans={"client.test"},
        enrolled_client_identities=enrolled_client_identities,
        **kwargs,
    )


class _MemoryTLSStream:
    def __init__(self, pair: "_MemoryTLSPair", side: str) -> None:
        self._pair = pair
        self._side = side

    @property
    def _ssl_object(self) -> ssl.SSLObject:
        return self._pair.client_ssl if self._side == "client" else self._pair.server_ssl

    def sendall(self, payload: bytes) -> None:
        view = memoryview(payload)
        sent = 0
        deadline = time.monotonic() + 5
        while sent < len(payload):
            with self._pair.condition:
                try:
                    written = self._ssl_object.write(view[sent:])
                    sent += written
                    self._pair.pump_unlocked()
                    self._pair.condition.notify_all()
                except ssl.SSLWantReadError:
                    self._pair.pump_unlocked()
                    if time.monotonic() > deadline:
                        raise TimeoutError("memory TLS send timed out")
                    self._pair.condition.wait(0.01)

    def recv(self, byte_count: int) -> bytes:
        deadline = time.monotonic() + 5
        while True:
            with self._pair.condition:
                try:
                    data = self._ssl_object.read(byte_count)
                    self._pair.pump_unlocked()
                    self._pair.condition.notify_all()
                    return data
                except ssl.SSLWantReadError:
                    self._pair.pump_unlocked()
                    if time.monotonic() > deadline:
                        raise TimeoutError("memory TLS recv timed out")
                    self._pair.condition.wait(0.01)


class _MemoryTLSPair:
    def __init__(self, *, server_context: ssl.SSLContext, client_context: ssl.SSLContext, server_hostname: str) -> None:
        self.server_in = ssl.MemoryBIO()
        self.server_out = ssl.MemoryBIO()
        self.client_in = ssl.MemoryBIO()
        self.client_out = ssl.MemoryBIO()
        self.server_ssl = server_context.wrap_bio(self.server_in, self.server_out, server_side=True)
        self.client_ssl = client_context.wrap_bio(
            self.client_in,
            self.client_out,
            server_side=False,
            server_hostname=server_hostname,
        )
        self.condition = threading.Condition()
        self.client_stream = _MemoryTLSStream(self, "client")
        self.server_stream = _MemoryTLSStream(self, "server")

    def pump_unlocked(self) -> None:
        while True:
            moved = False
            data = self.client_out.read()
            if data:
                self.server_in.write(data)
                moved = True
            data = self.server_out.read()
            if data:
                self.client_in.write(data)
                moved = True
            if not moved:
                return

    def handshake(self) -> None:
        client_done = False
        server_done = False
        deadline = time.monotonic() + 5
        while not (client_done and server_done):
            with self.condition:
                if not client_done:
                    try:
                        self.client_ssl.do_handshake()
                        client_done = True
                    except ssl.SSLWantReadError:
                        pass
                self.pump_unlocked()
                if not server_done:
                    try:
                        self.server_ssl.do_handshake()
                        server_done = True
                    except ssl.SSLWantReadError:
                        pass
                self.pump_unlocked()
                self.condition.notify_all()
            if time.monotonic() > deadline:
                raise TimeoutError("memory TLS handshake timed out")


def _make_memory_tls_pair(
    *,
    server: TrustedLanServer,
    client: TrustedLanClient,
) -> _MemoryTLSPair:
    pair = _MemoryTLSPair(
        server_context=_server_context(server.credentials),
        client_context=_client_context(client.credentials),
        server_hostname=client.server_hostname,
    )
    pair.handshake()
    _require_peer_san(pair.server_ssl.getpeercert(), server.allowed_client_sans)
    return pair


def _run_socketpair_upload(
    *,
    server: TrustedLanServer,
    client: TrustedLanClient,
    context,
    source_root: Path,
):
    pair = _make_memory_tls_pair(server=server, client=client)
    server_errors: list[BaseException] = []

    def serve() -> None:
        try:
            peer_identity = _derive_authenticated_peer_identity(
                peer_cert=pair.server_ssl.getpeercert(),
                der_bytes=pair.server_ssl.getpeercert(binary_form=True),
                enrollments=server.enrolled_client_identities,
            )
            server._receive_upload(pair.server_stream, peer_identity=peer_identity)
        except BaseException as exc:
            server_errors.append(exc)

    thread = threading.Thread(target=serve)
    thread.start()
    try:
        return client.upload_object_over_tls_socket(
            tls_sock=pair.client_stream,
            context=context,
            source_root=source_root,
        )
    finally:
        thread.join(timeout=2.0)
        if thread.is_alive():
            raise AssertionError("TLS server thread did not exit")
        if server_errors:
            raise server_errors[0]


class _ScriptedStream:
    def __init__(self, responses: list[bytes]) -> None:
        self._buffer = b"".join(responses)
        self.sent: list[bytes] = []

    def sendall(self, payload: bytes) -> None:
        self.sent.append(payload)

    def recv(self, byte_count: int) -> bytes:
        if not self._buffer:
            return b""
        chunk = self._buffer[:byte_count]
        self._buffer = self._buffer[byte_count:]
        return chunk


class _CloseOnlySocket:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_loopback_mtls_transfer_moves_object(tmp_path, payload: bytes, certs: CertMaterial) -> None:
    source = ContentAddressedStore(tmp_path / "source")
    digest = source.put_bytes(payload)
    server = _server_instance(tmp_path, certs)
    server.validate_listener_config()
    client = TrustedLanClient(
        credentials=_client_credentials(certs),
        server_hostname="server.test",
        validator=StrictValidator(),
        chunk_size=80,
    )
    context = make_context(payload, transport="lan_mtls")
    result = _run_socketpair_upload(
        server=server,
        client=client,
        context=context,
        source_root=source.root,
    )

    destination = ContentAddressedStore(tmp_path / "destination")
    assert result.object_sha256 == digest
    assert destination.read_bytes(digest) == payload
    assert result.verified_receipt_sha256 == context.receipt_sha256(digest)
    assert isinstance(server.validator, StrictValidator)
    assert server.validator.peer_identities
    assert server.validator.peer_identities[-1] is not None
    assert server.validator.peer_identities[-1].node_id == "node:source"


@pytest.mark.parametrize(
    ("enrollment_changes", "message"),
    [
        ({"node_id": "node:other"}, "source node"),
        ({"account_id": "account:other"}, "account"),
    ],
)
def test_client_certificate_identity_must_match_transfer_context(
    tmp_path,
    payload: bytes,
    certs: CertMaterial,
    enrollment_changes: dict[str, str],
    message: str,
) -> None:
    source = ContentAddressedStore(tmp_path / "source")
    digest = source.put_bytes(payload)
    server = _server_instance(
        tmp_path,
        certs,
        enrolled_client_identities={_client_enrollment(certs, **enrollment_changes)},
    )
    client = TrustedLanClient(
        credentials=_client_credentials(certs),
        server_hostname="server.test",
        validator=StrictValidator(),
        chunk_size=80,
    )

    with pytest.raises(AuthorizationError, match=message):
        _run_socketpair_upload(
            server=server,
            client=client,
            context=make_context(payload, transport="lan_mtls"),
            source_root=source.root,
        )
    assert not ContentAddressedStore(tmp_path / "destination").has(digest)


def test_missing_client_certificate_is_refused(tmp_path, payload: bytes, certs: CertMaterial) -> None:
    server = _server_instance(tmp_path, certs)
    client_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(certs.ca))
    if hasattr(ssl, "TLSVersion"):
        client_context.minimum_version = ssl.TLSVersion.TLSv1_3
    pair = _MemoryTLSPair(
        server_context=_server_context(server.credentials),
        client_context=client_context,
        server_hostname="server.test",
    )
    with pytest.raises(ssl.SSLError):
        pair.handshake()
    assert not any((tmp_path / "destination").rglob("objects/*/*"))


def test_unknown_client_ca_is_refused(tmp_path, payload: bytes, certs: CertMaterial) -> None:
    source = ContentAddressedStore(tmp_path / "source")
    source.put_bytes(payload)
    server = _server_instance(tmp_path, certs)
    client = TrustedLanClient(
        credentials=_client_credentials(certs, unknown_ca=True),
        server_hostname="server.test",
        validator=StrictValidator(),
    )
    with pytest.raises(ssl.SSLError):
        _run_socketpair_upload(
            server=server,
            client=client,
            context=make_context(payload, transport="lan_mtls"),
            source_root=source.root,
        )


def test_wrong_server_san_is_refused(tmp_path, payload: bytes, certs: CertMaterial) -> None:
    source = ContentAddressedStore(tmp_path / "source")
    source.put_bytes(payload)
    server = _server_instance(tmp_path, certs)
    client = TrustedLanClient(
        credentials=_client_credentials(certs),
        server_hostname="wrong.test",
        validator=StrictValidator(),
    )
    with pytest.raises((ssl.SSLCertVerificationError, ssl.CertificateError)):
        _run_socketpair_upload(
            server=server,
            client=client,
            context=make_context(payload, transport="lan_mtls"),
            source_root=source.root,
        )


def test_expired_server_certificate_is_refused(tmp_path, payload: bytes, certs: CertMaterial) -> None:
    source = ContentAddressedStore(tmp_path / "source")
    source.put_bytes(payload)
    server = _server_instance(tmp_path, certs, expired=True)
    client = TrustedLanClient(
        credentials=_client_credentials(certs),
        server_hostname="server.test",
        validator=StrictValidator(),
    )
    with pytest.raises(ssl.SSLCertVerificationError):
        _run_socketpair_upload(
            server=server,
            client=client,
            context=make_context(payload, transport="lan_mtls"),
            source_root=source.root,
        )


@pytest.mark.parametrize(
    "bind_host",
    [
        "0.0.0.0",
        "::",
        "::ffff:0.0.0.0",
        "255.255.255.255",
        "224.0.0.1",
        "192.0.2.1",
        "8.8.8.8",
    ],
)
def test_wildcard_and_public_binds_are_rejected(tmp_path, certs: CertMaterial, bind_host: str) -> None:
    server = TrustedLanServer(
        bind_host=bind_host,
        port=0,
        credentials=_server_credentials(certs),
        destination_root=tmp_path / "destination",
        validator=StrictValidator(),
        declared_listener_addresses={bind_host},
        allowed_client_sans={"client.test"},
    )
    with pytest.raises(TLSConfigurationError):
        server.start()


def test_explicit_vpn_cidr_listener_is_allowed(tmp_path, certs: CertMaterial) -> None:
    server = TrustedLanServer(
        bind_host="100.64.1.10",
        port=0,
        credentials=_server_credentials(certs),
        destination_root=tmp_path / "destination",
        validator=StrictValidator(),
        declared_listener_addresses={"100.64.1.10"},
        declared_vpn_cidrs={"100.64.0.0/10"},
        allowed_client_sans={"client.test"},
        enrolled_client_identities={_client_enrollment(certs)},
    )
    assert str(server.validate_listener_config()) == "100.64.1.10"


def test_tls_worker_limit_and_error_retention_are_bounded(tmp_path, certs: CertMaterial) -> None:
    server = _server_instance(tmp_path, certs, max_workers=1, max_errors=2)
    assert server._worker_slots.acquire(blocking=False)
    refused = _CloseOnlySocket()
    try:
        assert server._dispatch_client(_server_context(server.credentials), refused) is False
    finally:
        server._worker_slots.release()
    assert refused.closed is True
    assert len(server.errors) == 1
    assert isinstance(server.errors[0], BackpressureError)

    server._record_error(RuntimeError("first"))
    server._record_error(RuntimeError("second"))
    server._record_error(RuntimeError("third"))
    assert len(server.errors) == 2
    assert str(server.errors[0]) == "second"


def test_undeclared_listener_address_is_rejected(tmp_path, certs: CertMaterial) -> None:
    server = TrustedLanServer(
        bind_host="127.0.0.1",
        port=0,
        credentials=_server_credentials(certs),
        destination_root=tmp_path / "destination",
        validator=StrictValidator(),
        declared_listener_addresses={"127.0.0.2"},
        allowed_client_sans={"client.test"},
    )
    with pytest.raises(TLSConfigurationError, match="declared"):
        server.start()


def test_plaintext_is_refused_by_tls_listener(tmp_path, payload: bytes, certs: CertMaterial) -> None:
    server = _server_instance(tmp_path, certs)
    server_context = _server_context(server.credentials)
    server_in = ssl.MemoryBIO()
    server_out = ssl.MemoryBIO()
    server_ssl = server_context.wrap_bio(server_in, server_out, server_side=True)
    context = make_context(payload, transport="lan_mtls")
    frame = encode_frame(FRAME_START, context=context.to_wire(), total_length=context.byte_length)
    server_in.write(frame)
    with pytest.raises(ssl.SSLError):
        server_ssl.do_handshake()
    assert not any((tmp_path / "destination").rglob("objects/*/*"))


def test_forged_resume_ack_cannot_claim_oversized_success(tmp_path, payload: bytes, certs: CertMaterial) -> None:
    source = ContentAddressedStore(tmp_path / "source")
    source.put_bytes(payload)
    context = make_context(payload, transport="lan_mtls")
    forged_ack = encode_frame(
        FRAME_ACK,
        context=context.to_wire(),
        extra={"resume_offset": context.byte_length + 1},
    )
    client = TrustedLanClient(
        credentials=_client_credentials(certs),
        server_hostname="server.test",
        validator=StrictValidator(),
    )

    with pytest.raises(TLSConfigurationError, match="resume_offset"):
        client._upload_over_socket(
            tls_sock=_ScriptedStream([forged_ack]),
            context=context,
            source=source,
            cancellation=CancellationToken(),
            deadline=None,
            progress=None,
        )


def test_final_ack_requires_receiver_verified_receipt(tmp_path, payload: bytes, certs: CertMaterial) -> None:
    source = ContentAddressedStore(tmp_path / "source")
    source.put_bytes(payload)
    context = make_context(payload, transport="lan_mtls")
    start_ack = encode_frame(
        FRAME_ACK,
        context=context.to_wire(),
        extra={"resume_offset": 0},
    )
    chunk_ack = encode_frame(
        FRAME_ACK,
        context=context.to_wire(),
        extra={"resume_offset": context.byte_length},
    )
    forged_final = encode_frame(
        FRAME_ACK,
        context=context.to_wire(),
        extra={"object_sha256": context.object_sha256},
    )
    client = TrustedLanClient(
        credentials=_client_credentials(certs),
        server_hostname="server.test",
        validator=StrictValidator(),
        chunk_size=context.byte_length,
    )

    with pytest.raises(TLSConfigurationError, match="receipt"):
        client._upload_over_socket(
            tls_sock=_ScriptedStream([start_ack, chunk_ack, forged_final]),
            context=context,
            source=source,
            cancellation=CancellationToken(),
            deadline=None,
            progress=None,
        )


def test_tls_client_also_requires_injected_admission(tmp_path, payload: bytes, certs: CertMaterial) -> None:
    source = ContentAddressedStore(tmp_path / "source")
    source.put_bytes(payload)
    client = TrustedLanClient(
        credentials=_client_credentials(certs),
        server_hostname="server.test",
        validator=StrictValidator(allow=False),
    )
    with pytest.raises(AuthorizationError, match="denied"):
        client.upload_object(
            context=make_context(payload, transport="lan_mtls"),
            source_root=source.root,
            host="127.0.0.1",
            port=9,
        )
