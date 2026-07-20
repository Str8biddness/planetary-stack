"""Trusted-LAN mTLS Unisync backend.

This backend intentionally covers only declared loopback/private/VPN peers. It
does not implement public discovery, enrollment, relays, NAT traversal, or
scheduling.
"""

from __future__ import annotations

import hashlib
import ipaddress
import os
import socket
import ssl
import stat
import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .contracts import (
    AuthenticatedPeerIdentity,
    AuthorizationLeaseValidator,
    BackpressureController,
    CancellationToken,
    Deadline,
    ProgressCallback,
    TransferContext,
    TransferProgress,
    TransferResult,
    require_authorized,
)
from .errors import (
    AuthorizationError,
    BackpressureError,
    CancellationError,
    DeadlineExceededError,
    TLSConfigurationError,
    UnisyncError,
)
from .framing import (
    DEFAULT_LIMITS,
    FRAME_ACK,
    FRAME_CANCEL,
    FRAME_CHUNK,
    FRAME_COMPLETE,
    FRAME_ERROR,
    FRAME_START,
    FrameLimits,
    encode_frame,
    read_frame,
    send_frame,
)
from .storage import ContentAddressedStore


@dataclass(frozen=True, slots=True)
class TLSCredentials:
    ca_file: Path
    cert_file: Path
    key_file: Path

    def require_files(self) -> None:
        for label, configured_path in (
            ("CA", self.ca_file),
            ("certificate", self.cert_file),
            ("private key", self.key_file),
        ):
            path = Path(configured_path)
            try:
                metadata = path.lstat()
            except FileNotFoundError as exc:
                raise TLSConfigurationError(f"TLS credential file is missing: {path}") from exc
            if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
                raise TLSConfigurationError(f"TLS {label} must be a regular non-symlink file")
            if metadata.st_uid != os.getuid():
                raise TLSConfigurationError(f"TLS {label} must be owned by the current user")
            mode = stat.S_IMODE(metadata.st_mode)
            if label == "private key" and mode != 0o600:
                raise TLSConfigurationError("TLS private key must have mode 0600")
            if label != "private key" and mode & 0o022:
                raise TLSConfigurationError(f"TLS {label} must not be group/other writable")


@dataclass(frozen=True, slots=True)
class EnrolledPeerIdentity:
    """Control-plane enrollment binding for one TLS certificate identity."""

    account_id: str
    node_id: str
    sans: frozenset[str]
    certificate_sha256: str | None = None
    public_key_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.account_id or not self.node_id:
            raise TLSConfigurationError("enrolled peer requires account_id and node_id")
        if not self.sans:
            raise TLSConfigurationError("enrolled peer requires at least one SAN")
        if self.certificate_sha256 is None and self.public_key_sha256 is None:
            raise TLSConfigurationError("enrolled peer requires a certificate or public-key fingerprint")
        for digest in (self.certificate_sha256, self.public_key_sha256):
            if digest is not None and (len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest)):
                raise TLSConfigurationError("enrolled peer fingerprint must be lowercase SHA-256 hex")

    def normalized_sans(self) -> frozenset[str]:
        return frozenset(_normalize_san(value) for value in self.sans)


def _set_tls13_minimum(context: ssl.SSLContext) -> None:
    if (
        not getattr(ssl, "HAS_TLSv1_3", False)
        or not hasattr(ssl, "TLSVersion")
        or not hasattr(ssl.TLSVersion, "TLSv1_3")
    ):
        raise TLSConfigurationError("this runtime does not support required TLSv1.3")
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    if context.minimum_version != ssl.TLSVersion.TLSv1_3:
        raise TLSConfigurationError("TLSv1.3 minimum version could not be enforced")


def _server_context(credentials: TLSCredentials) -> ssl.SSLContext:
    credentials.require_files()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    _set_tls13_minimum(context)
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(cafile=str(credentials.ca_file))
    context.load_cert_chain(certfile=str(credentials.cert_file), keyfile=str(credentials.key_file))
    return context


def _client_context(credentials: TLSCredentials) -> ssl.SSLContext:
    credentials.require_files()
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(credentials.ca_file))
    _set_tls13_minimum(context)
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = True
    context.load_cert_chain(certfile=str(credentials.cert_file), keyfile=str(credentials.key_file))
    if context.verify_mode == ssl.CERT_NONE or not context.check_hostname:
        raise TLSConfigurationError("client TLS context must verify server certificates and hostnames")
    return context


DOCUMENTATION_CIDRS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "192.0.2.0/24",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "2001:db8::/32",
    )
)
RFC1918_CIDRS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
    )
)
ULA_CIDR = ipaddress.ip_network("fc00::/7")
CGNAT_CIDR = ipaddress.ip_network("100.64.0.0/10")
LIMITED_BROADCAST = ipaddress.ip_address("255.255.255.255")


def _normalize_san(value: str) -> str:
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return value.lower()


def _parse_vpn_cidrs(values: Iterable[str]) -> tuple[ipaddress._BaseNetwork, ...]:
    try:
        networks = tuple(ipaddress.ip_network(value, strict=False) for value in values)
    except ValueError as exc:
        raise TLSConfigurationError("declared VPN CIDRs must be valid IP networks") from exc
    allowed_spaces = (*RFC1918_CIDRS, CGNAT_CIDR, ULA_CIDR)
    for network in networks:
        if not any(
            network.version == allowed.version and network.subnet_of(allowed)
            for allowed in allowed_spaces
        ):
            raise TLSConfigurationError(
                "declared VPN CIDRs must remain inside private, CGNAT, or ULA space"
            )
    return networks


def _is_documentation_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return any(address in network for network in DOCUMENTATION_CIDRS)


def _is_private_listener_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(address, ipaddress.IPv4Address):
        return any(address in network for network in RFC1918_CIDRS)
    return address in ULA_CIDR


def _literal_allowed_address(
    host: str,
    *,
    declared_vpn_cidrs: Iterable[str] = (),
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise TLSConfigurationError("listener address must be a literal IP address") from exc
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        raise TLSConfigurationError("IPv4-mapped listener addresses are prohibited")
    if address.is_unspecified:
        raise TLSConfigurationError("wildcard listener addresses are prohibited")
    if address == LIMITED_BROADCAST:
        raise TLSConfigurationError("broadcast listener addresses are prohibited")
    if address.is_multicast:
        raise TLSConfigurationError("multicast listener addresses are prohibited")
    if address.is_reserved:
        raise TLSConfigurationError("reserved listener addresses are prohibited")
    if _is_documentation_address(address):
        raise TLSConfigurationError("documentation listener addresses are prohibited")
    vpn_cidrs = _parse_vpn_cidrs(declared_vpn_cidrs)
    if address.is_loopback or _is_private_listener_address(address) or any(address in network for network in vpn_cidrs):
        return address
    raise TLSConfigurationError("listener address must be loopback, private, or declared VPN space")


def _extract_peer_sans(peer_cert: dict[str, object]) -> set[str]:
    sans: set[str] = set()
    for kind, value in peer_cert.get("subjectAltName", ()):  # type: ignore[union-attr]
        if kind in {"DNS", "IP Address"}:
            sans.add(_normalize_san(str(value)))
    return sans


def _require_peer_san(peer_cert: dict[str, object], allowed_sans: set[str]) -> None:
    if not allowed_sans:
        raise TLSConfigurationError("at least one declared peer SAN is required")
    peer_sans = _extract_peer_sans(peer_cert)
    normalized_allowed = {_normalize_san(value) for value in allowed_sans}
    if peer_sans.isdisjoint(normalized_allowed):
        raise AuthorizationError("mTLS peer certificate is not in the declared peer allowlist")


def _certificate_identity_from_der(
    der_bytes: bytes,
) -> tuple[set[str], str, str, str, str]:
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        from cryptography.x509.oid import ExtensionOID, NameOID
    except ImportError as exc:
        raise TLSConfigurationError("cryptography is required for TLS peer identity binding") from exc
    try:
        certificate = x509.load_der_x509_certificate(der_bytes)
        san_extension = certificate.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME).value
    except Exception as exc:
        raise AuthorizationError("mTLS peer certificate SANs could not be parsed") from exc
    sans: set[str] = set()
    for name in san_extension:
        sans.add(_normalize_san(str(name.value)))
    if not sans:
        raise AuthorizationError("mTLS peer certificate has no SANs")
    account_names = certificate.subject.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)
    node_names = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    if len(account_names) != 1 or len(node_names) != 1:
        raise AuthorizationError(
            "mTLS peer certificate does not bind exactly one account and node"
        )
    certificate_account_id = account_names[0].value
    certificate_node_id = node_names[0].value
    certificate_sha256 = hashlib.sha256(der_bytes).hexdigest()
    public_key_der = certificate.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_key_sha256 = hashlib.sha256(public_key_der).hexdigest()
    return (
        sans,
        certificate_sha256,
        public_key_sha256,
        certificate_account_id,
        certificate_node_id,
    )


def _derive_authenticated_peer_identity(
    *,
    peer_cert: dict[str, object] | None,
    der_bytes: bytes | None,
    enrollments: Iterable[EnrolledPeerIdentity],
) -> AuthenticatedPeerIdentity:
    if not peer_cert or not der_bytes:
        raise AuthorizationError("peer certificate is required")
    (
        sans,
        certificate_sha256,
        public_key_sha256,
        certificate_account_id,
        certificate_node_id,
    ) = _certificate_identity_from_der(der_bytes)
    for enrollment in enrollments:
        if (
            enrollment.account_id != certificate_account_id
            or enrollment.node_id != certificate_node_id
        ):
            continue
        if sans.isdisjoint(enrollment.normalized_sans()):
            continue
        if enrollment.certificate_sha256 is not None and enrollment.certificate_sha256 != certificate_sha256:
            continue
        if enrollment.public_key_sha256 is not None and enrollment.public_key_sha256 != public_key_sha256:
            continue
        return AuthenticatedPeerIdentity(
            account_id=enrollment.account_id,
            node_id=enrollment.node_id,
            sans=tuple(sorted(sans)),
            certificate_sha256=certificate_sha256,
            public_key_sha256=public_key_sha256,
        )
    raise AuthorizationError("mTLS peer certificate is not enrolled for this transfer")


def _is_timeout(exc: BaseException) -> bool:
    return isinstance(exc, (socket.timeout, TimeoutError, DeadlineExceededError))


def _require_ack_context(frame_context: object, context: TransferContext) -> None:
    if frame_context != context.to_wire():
        raise AuthorizationError("acknowledgement transfer context does not match the requested transfer")


def _require_resume_offset(value: object, context: TransferContext) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TLSConfigurationError("resume_offset must be an integer")
    if value < 0 or value > context.byte_length:
        raise TLSConfigurationError("resume_offset is outside the transfer byte range")
    return value


def _require_verified_receipt(value: object, context: TransferContext) -> None:
    if value != context.receipt_sha256(context.object_sha256):
        raise TLSConfigurationError("server finalization receipt is invalid")


class TrustedLanServer:
    """Loopback/private-address mTLS object receiver."""

    transport_id = "lan_mtls"

    def __init__(
        self,
        *,
        bind_host: str,
        port: int,
        credentials: TLSCredentials,
        destination_root: Path,
        validator: AuthorizationLeaseValidator | None,
        declared_listener_addresses: Iterable[str],
        allowed_client_sans: Iterable[str],
        enrolled_client_identities: Iterable[EnrolledPeerIdentity] = (),
        declared_vpn_cidrs: Iterable[str] = (),
        limits: FrameLimits = DEFAULT_LIMITS,
        backpressure: BackpressureController | None = None,
        max_workers: int = 16,
        handshake_timeout: float = 5.0,
        idle_timeout: float = 5.0,
        max_errors: int = 64,
        max_audit_events: int = 128,
    ) -> None:
        if max_workers <= 0:
            raise ValueError("max_workers must be positive")
        if handshake_timeout <= 0 or idle_timeout <= 0:
            raise ValueError("TLS timeouts must be positive")
        self.bind_host = bind_host
        self.port = port
        self.credentials = credentials
        self.destination_root = Path(destination_root)
        self.validator = validator
        self.declared_listener_addresses = {_normalize_san(value) for value in declared_listener_addresses}
        self.allowed_client_sans = {_normalize_san(value) for value in allowed_client_sans}
        self.enrolled_client_identities = tuple(enrolled_client_identities)
        self.declared_vpn_cidrs = tuple(declared_vpn_cidrs)
        if not self.allowed_client_sans:
            self.allowed_client_sans = {
                san for enrollment in self.enrolled_client_identities for san in enrollment.normalized_sans()
            }
        self.limits = limits
        self.backpressure = backpressure
        self.max_workers = max_workers
        self.handshake_timeout = handshake_timeout
        self.idle_timeout = idle_timeout
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._closed = threading.Event()
        self._worker_slots = threading.BoundedSemaphore(max_workers)
        self._errors: deque[BaseException] = deque(maxlen=max_errors)
        self._audit_events: deque[str] = deque(maxlen=max_audit_events)

    @property
    def errors(self) -> list[BaseException]:
        return list(self._errors)

    @property
    def audit_events(self) -> list[str]:
        return list(self._audit_events)

    def _record_error(self, exc: BaseException) -> None:
        self._errors.append(exc)

    def _record_audit(self, message: str) -> None:
        self._audit_events.append(message)

    @property
    def address(self) -> tuple[str, int]:
        if self._socket is None:
            raise TLSConfigurationError("server is not started")
        host, port = self._socket.getsockname()[:2]
        return str(host), int(port)

    def validate_listener_config(self) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
        address = _literal_allowed_address(self.bind_host, declared_vpn_cidrs=self.declared_vpn_cidrs)
        if _normalize_san(str(address)) not in self.declared_listener_addresses:
            raise TLSConfigurationError("listener address must be explicitly declared before binding")
        if not self.enrolled_client_identities:
            raise TLSConfigurationError("server requires enrolled client certificate identities")
        if not self.allowed_client_sans:
            raise TLSConfigurationError("server requires declared client certificate SANs")
        return address

    def start(self) -> None:
        address = self.validate_listener_config()
        context = _server_context(self.credentials)
        family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((str(address), self.port))
        sock.listen(8)
        sock.settimeout(0.2)
        self._socket = sock
        self._thread = threading.Thread(target=self._serve, args=(context,), daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._closed.set()
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def __enter__(self) -> "TrustedLanServer":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _serve(self, context: ssl.SSLContext) -> None:
        assert self._socket is not None
        while not self._closed.is_set():
            try:
                client_sock, _ = self._socket.accept()
            except socket.timeout:
                continue
            except OSError as exc:
                if not self._closed.is_set():
                    self._record_error(exc)
                break
            self._dispatch_client(context, client_sock)

    def _dispatch_client(self, context: ssl.SSLContext, client_sock: socket.socket) -> bool:
        if not self._worker_slots.acquire(blocking=False):
            self._record_error(BackpressureError("TLS worker limit reached"))
            self._record_audit("worker_limit_refused_connection")
            try:
                client_sock.close()
            except OSError:
                pass
            return False
        thread = threading.Thread(target=self._handle_socket_with_slot, args=(context, client_sock), daemon=True)
        thread.start()
        return True

    def _handle_socket_with_slot(self, context: ssl.SSLContext, client_sock: socket.socket) -> None:
        try:
            self._handle_socket(context, client_sock)
        finally:
            self._worker_slots.release()

    def _handle_socket(self, context: ssl.SSLContext, client_sock: socket.socket) -> None:
        try:
            client_sock.settimeout(self.handshake_timeout)
            with context.wrap_socket(client_sock, server_side=True) as tls_sock:
                tls_sock.settimeout(self.idle_timeout)
                if tls_sock.version() != "TLSv1.3":
                    raise TLSConfigurationError("negotiated TLS version is not TLSv1.3")
                peer_cert = tls_sock.getpeercert()
                if not peer_cert:
                    raise AuthorizationError("client certificate is required")
                _require_peer_san(peer_cert, self.allowed_client_sans)
                peer_identity = _derive_authenticated_peer_identity(
                    peer_cert=peer_cert,
                    der_bytes=tls_sock.getpeercert(binary_form=True),
                    enrollments=self.enrolled_client_identities,
                )
                self._record_audit("client_identity_bound")
                self._receive_upload(tls_sock, peer_identity=peer_identity)
        except BaseException as exc:
            if not self._closed.is_set() and not isinstance(exc, (ssl.SSLError, ConnectionError, OSError)):
                self._record_error(exc)
        finally:
            try:
                client_sock.close()
            except OSError:
                pass

    def _receive_upload(
        self,
        tls_sock: ssl.SSLSocket,
        *,
        peer_identity: AuthenticatedPeerIdentity | None = None,
    ) -> dict[str, Any] | None:
        assembler = None
        transfer_context: TransferContext | None = None
        try:
            if peer_identity is None:
                raise AuthorizationError("authenticated client identity is required")
            if hasattr(tls_sock, "settimeout"):
                tls_sock.settimeout(self.idle_timeout)
            start = read_frame(tls_sock, limits=self.limits)
            if start.frame_type != FRAME_START:
                raise TLSConfigurationError("first TLS frame must be start")
            context_payload = start.header.get("transfer_context")
            if not isinstance(context_payload, dict):
                raise TLSConfigurationError("start frame is missing transfer_context")
            transfer_context = TransferContext.from_wire(context_payload)
            require_authorized(
                transfer_context,
                validator=self.validator,
                transport_id=self.transport_id,
                max_total_bytes=self.limits.max_total_bytes,
                peer_identity=peer_identity,
                expected_peer_role="source",
            )
            destination = ContentAddressedStore(self.destination_root)
            assembler = destination.start_receive(transfer_context, limits=self.limits)
            send_frame(
                tls_sock,
                encode_frame(
                    FRAME_ACK,
                    total_length=transfer_context.byte_length,
                    context=transfer_context.to_wire(),
                    extra={"resume_offset": assembler.offset},
                    limits=self.limits,
                ),
            )
            while True:
                frame = read_frame(tls_sock, limits=self.limits)
                if frame.header.get("transfer_context") != transfer_context.to_wire():
                    raise AuthorizationError("frame transfer context changed during upload")
                if frame.frame_type == FRAME_CANCEL:
                    assembler.abort()
                    send_frame(tls_sock, encode_frame(FRAME_ACK, context=transfer_context.to_wire(), limits=self.limits))
                    return {"cancelled": True}
                if frame.frame_type == FRAME_CHUNK:
                    require_authorized(
                        transfer_context,
                        validator=self.validator,
                        transport_id=self.transport_id,
                        max_total_bytes=self.limits.max_total_bytes,
                        peer_identity=peer_identity,
                        expected_peer_role="source",
                    )
                    if self.backpressure is not None:
                        self.backpressure.acquire(len(frame.payload))
                    try:
                        assembler.receive_chunk(
                            offset=int(frame.header["offset"]),
                            payload=frame.payload,
                            chunk_sha256=str(frame.header["payload_sha256"]),
                        )
                    finally:
                        if self.backpressure is not None:
                            self.backpressure.release(len(frame.payload))
                    send_frame(
                        tls_sock,
                        encode_frame(
                            FRAME_ACK,
                            context=transfer_context.to_wire(),
                            extra={"resume_offset": assembler.offset},
                            limits=self.limits,
                        ),
                    )
                    continue
                if frame.frame_type == FRAME_COMPLETE:
                    require_authorized(
                        transfer_context,
                        validator=self.validator,
                        transport_id=self.transport_id,
                        max_total_bytes=self.limits.max_total_bytes,
                        peer_identity=peer_identity,
                        expected_peer_role="source",
                    )
                    digest = assembler.finalize()
                    send_frame(
                        tls_sock,
                        encode_frame(
                            FRAME_ACK,
                            context=transfer_context.to_wire(),
                            extra={
                                "object_sha256": digest,
                                "verified_receipt_sha256": transfer_context.receipt_sha256(digest),
                            },
                            limits=self.limits,
                        ),
                    )
                    return {
                        "object_sha256": digest,
                        "byte_length": transfer_context.byte_length,
                        "verified_receipt_sha256": transfer_context.receipt_sha256(digest),
                    }
                raise TLSConfigurationError(f"unexpected frame type {frame.frame_type!r}")
        except BaseException as exc:
            if assembler is not None:
                assembler.abort()
            try:
                send_frame(
                    tls_sock,
                    encode_frame(
                        FRAME_ERROR,
                        extra={"error_code": type(exc).__name__},
                        limits=self.limits,
                    ),
                )
            except BaseException:
                pass
            if not _is_timeout(exc):
                raise

    def receive_object_over_dialed_socket(
        self,
        raw_sock: socket.socket,
        *,
        handshake_timeout: float | None = None,
    ) -> dict[str, Any]:
        """Receive one object over a socket THIS side opened (desktop pull).

        Desktop-initiated pull: the desktop dials the TCP connection outbound
        (so it needs no inbound firewall) but is the TLS server and object
        receiver. The peer (worker) is therefore the authenticated *source*.
        The mutual-auth, SAN, lease binding, and receipt logic are identical to
        the listener path (`_handle_socket` -> `_receive_upload`); only which
        side opened the TCP socket differs. Raises on any failure and returns
        the verified receipt on success.
        """

        context = _server_context(self.credentials)
        raw_sock.settimeout(handshake_timeout or self.handshake_timeout)
        with context.wrap_socket(raw_sock, server_side=True) as tls_sock:
            tls_sock.settimeout(self.idle_timeout)
            if tls_sock.version() != "TLSv1.3":
                raise TLSConfigurationError("negotiated TLS version is not TLSv1.3")
            peer_cert = tls_sock.getpeercert()
            if not peer_cert:
                raise AuthorizationError("peer certificate is required")
            _require_peer_san(peer_cert, self.allowed_client_sans)
            peer_identity = _derive_authenticated_peer_identity(
                peer_cert=peer_cert,
                der_bytes=tls_sock.getpeercert(binary_form=True),
                enrollments=self.enrolled_client_identities,
            )
            self._record_audit("client_identity_bound")
            result = self._receive_upload(tls_sock, peer_identity=peer_identity)
            if not result or "object_sha256" not in result:
                raise TLSConfigurationError(
                    "pull did not complete a verified object receipt"
                )
            return result


class TrustedLanClient:
    """mTLS object sender for a declared trusted-LAN peer."""

    transport_id = "lan_mtls"

    def __init__(
        self,
        *,
        credentials: TLSCredentials,
        server_hostname: str,
        validator: AuthorizationLeaseValidator | None,
        enrolled_server_identities: Iterable[EnrolledPeerIdentity] = (),
        limits: FrameLimits = DEFAULT_LIMITS,
        chunk_size: int | None = None,
        backpressure: BackpressureController | None = None,
    ) -> None:
        if not server_hostname:
            raise TLSConfigurationError("server_hostname is required for SAN verification")
        self.credentials = credentials
        self.server_hostname = server_hostname
        self.validator = validator
        self.enrolled_server_identities = tuple(enrolled_server_identities)
        self.limits = limits
        self.chunk_size = chunk_size or limits.max_payload_bytes
        if self.chunk_size <= 0 or self.chunk_size > limits.max_payload_bytes:
            raise ValueError("chunk_size must be positive and no larger than max_payload_bytes")
        self.backpressure = backpressure

    def upload_object(
        self,
        *,
        context: TransferContext,
        source_root: Path,
        host: str,
        port: int,
        cancellation: CancellationToken | None = None,
        deadline: Deadline | None = None,
        progress: ProgressCallback | None = None,
        timeout: float = 5.0,
    ) -> TransferResult:
        require_authorized(
            context,
            validator=self.validator,
            transport_id=self.transport_id,
            max_total_bytes=self.limits.max_total_bytes,
        )
        if not self.enrolled_server_identities:
            raise TLSConfigurationError(
                "network mTLS requires an explicitly enrolled destination identity"
            )
        token = cancellation or CancellationToken()
        source = ContentAddressedStore(source_root)
        if source.stat_size(context.object_sha256) != context.byte_length:
            raise ValueError("source object size does not match transfer context")
        ssl_context = _client_context(self.credentials)
        with socket.create_connection((host, port), timeout=timeout) as raw_sock:
            raw_sock.settimeout(timeout)
            with ssl_context.wrap_socket(raw_sock, server_hostname=self.server_hostname) as tls_sock:
                self._require_authenticated_destination(tls_sock, context)
                return self._upload_over_socket(
                    tls_sock=tls_sock,
                    context=context,
                    source=source,
                    cancellation=token,
                    deadline=deadline,
                    progress=progress,
                )

    def upload_object_over_tls_socket(
        self,
        *,
        tls_sock: ssl.SSLSocket,
        context: TransferContext,
        source_root: Path,
        cancellation: CancellationToken | None = None,
        deadline: Deadline | None = None,
        progress: ProgressCallback | None = None,
    ) -> TransferResult:
        self._require_authenticated_destination(tls_sock, context)
        source = ContentAddressedStore(source_root)
        if source.stat_size(context.object_sha256) != context.byte_length:
            raise ValueError("source object size does not match transfer context")
        token = cancellation or CancellationToken()
        return self._upload_over_socket(
            tls_sock=tls_sock,
            context=context,
            source=source,
            cancellation=token,
            deadline=deadline,
            progress=progress,
        )

    def _require_authenticated_destination(
        self,
        tls_sock: ssl.SSLSocket,
        context: TransferContext,
    ) -> AuthenticatedPeerIdentity:
        """Bind every TLS upload path to the enrolled destination node."""

        if not self.enrolled_server_identities:
            raise TLSConfigurationError(
                "network mTLS requires an explicitly enrolled destination identity"
            )
        try:
            version = tls_sock.version()
            peer_cert = tls_sock.getpeercert()
            peer_der = tls_sock.getpeercert(binary_form=True)
        except (AttributeError, OSError, ssl.SSLError) as exc:
            raise TLSConfigurationError(
                "TLS socket cannot provide authenticated peer evidence"
            ) from exc
        if version != "TLSv1.3":
            raise TLSConfigurationError("negotiated TLS version is not TLSv1.3")
        server_identity = _derive_authenticated_peer_identity(
            peer_cert=peer_cert,
            der_bytes=peer_der,
            enrollments=self.enrolled_server_identities,
        )
        require_authorized(
            context,
            validator=self.validator,
            transport_id=self.transport_id,
            max_total_bytes=self.limits.max_total_bytes,
            peer_identity=server_identity,
            expected_peer_role="destination",
        )
        return server_identity

    def _upload_over_socket(
        self,
        *,
        tls_sock: ssl.SSLSocket,
        context: TransferContext,
        source: ContentAddressedStore,
        cancellation: CancellationToken,
        deadline: Deadline | None,
        progress: ProgressCallback | None,
    ) -> TransferResult:
        if deadline is not None:
            deadline.raise_if_expired()
        send_frame(
            tls_sock,
            encode_frame(
                FRAME_START,
                context=context.to_wire(),
                total_length=context.byte_length,
                limits=self.limits,
            ),
        )
        ack = read_frame(tls_sock, limits=self.limits)
        if ack.frame_type == FRAME_ERROR:
            raise AuthorizationError("server refused transfer start")
        if ack.frame_type != FRAME_ACK:
            raise TLSConfigurationError("server did not acknowledge transfer start")
        _require_ack_context(ack.header.get("transfer_context"), context)
        resumed_from = _require_resume_offset(ack.header.get("resume_offset", 0), context)
        transferred = resumed_from
        with source.open_read(context.object_sha256, offset=resumed_from) as handle:
            sequence = 0
            offset = resumed_from
            while offset < context.byte_length:
                cancellation.raise_if_cancelled()
                if deadline is not None:
                    deadline.raise_if_expired()
                payload = handle.read(min(self.chunk_size, context.byte_length - offset))
                if not payload:
                    break
                require_authorized(
                    context,
                    validator=self.validator,
                    transport_id=self.transport_id,
                    max_total_bytes=self.limits.max_total_bytes,
                )
                if self.backpressure is not None:
                    self.backpressure.acquire(len(payload))
                try:
                    send_frame(
                        tls_sock,
                        encode_frame(
                            FRAME_CHUNK,
                            payload=payload,
                            sequence=sequence,
                            offset=offset,
                            total_length=context.byte_length,
                            context=context.to_wire(),
                            limits=self.limits,
                        ),
                    )
                    ack = read_frame(tls_sock, limits=self.limits)
                    if ack.frame_type == FRAME_ERROR:
                        raise BackpressureError("server refused chunk")
                    if ack.frame_type != FRAME_ACK:
                        raise TLSConfigurationError("server did not acknowledge chunk")
                    _require_ack_context(ack.header.get("transfer_context"), context)
                    acknowledged = _require_resume_offset(ack.header.get("resume_offset", 0), context)
                    if acknowledged != offset + len(payload):
                        raise TLSConfigurationError("server chunk acknowledgement offset is invalid")
                finally:
                    if self.backpressure is not None:
                        self.backpressure.release(len(payload))
                offset += len(payload)
                transferred = offset
                sequence += 1
                if progress is not None:
                    progress(
                        TransferProgress(
                            context=context,
                            bytes_transferred=transferred,
                            total_bytes=context.byte_length,
                            chunk_index=sequence,
                            resumed_from=resumed_from,
                        )
                    )
            if cancellation.cancelled:
                send_frame(tls_sock, encode_frame(FRAME_CANCEL, context=context.to_wire(), limits=self.limits))
                raise CancellationError("transfer cancelled")
            if offset != context.byte_length:
                raise TLSConfigurationError("source object ended before declared transfer length")
        require_authorized(
            context,
            validator=self.validator,
            transport_id=self.transport_id,
            max_total_bytes=self.limits.max_total_bytes,
        )
        send_frame(
            tls_sock,
            encode_frame(
                FRAME_COMPLETE,
                sequence=sequence,
                offset=context.byte_length,
                total_length=context.byte_length,
                context=context.to_wire(),
                extra={"object_sha256": context.object_sha256},
                limits=self.limits,
            ),
        )
        ack = read_frame(tls_sock, limits=self.limits)
        if ack.frame_type == FRAME_ERROR:
            raise TLSConfigurationError("server refused finalization")
        if ack.frame_type != FRAME_ACK:
            raise TLSConfigurationError("server finalization acknowledgement is invalid")
        _require_ack_context(ack.header.get("transfer_context"), context)
        if ack.header.get("object_sha256") != context.object_sha256:
            raise TLSConfigurationError("server finalization acknowledgement is invalid")
        _require_verified_receipt(ack.header.get("verified_receipt_sha256"), context)
        if progress is not None:
            progress(
                TransferProgress(
                    context=context,
                    bytes_transferred=context.byte_length,
                    total_bytes=context.byte_length,
                    chunk_index=sequence,
                    resumed_from=resumed_from,
                    complete=True,
                )
            )
        return TransferResult(
            context=context,
            object_sha256=context.object_sha256,
            bytes_transferred=transferred - resumed_from,
            resumed_from=resumed_from,
            transport_id=self.transport_id,
            verified_receipt_sha256=context.receipt_sha256(context.object_sha256),
        )
