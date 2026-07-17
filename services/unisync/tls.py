"""Trusted-LAN mTLS Unisync backend.

This backend intentionally covers only declared loopback/private/VPN peers. It
does not implement public discovery, enrollment, relays, NAT traversal, or
scheduling.
"""

from __future__ import annotations

import ipaddress
import socket
import ssl
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .contracts import (
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
        for path in (self.ca_file, self.cert_file, self.key_file):
            if not Path(path).is_file():
                raise TLSConfigurationError(f"TLS credential file is missing: {path}")


def _set_tls13_minimum(context: ssl.SSLContext) -> None:
    if hasattr(ssl, "TLSVersion") and hasattr(ssl.TLSVersion, "TLSv1_3"):
        context.minimum_version = ssl.TLSVersion.TLSv1_3


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


def _literal_allowed_address(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise TLSConfigurationError("listener address must be a literal IP address") from exc
    if address.is_unspecified:
        raise TLSConfigurationError("wildcard listener addresses are prohibited")
    carrier_grade_nat = ipaddress.ip_network("100.64.0.0/10")
    if address.is_loopback or address.is_private or address in carrier_grade_nat:
        return address
    raise TLSConfigurationError("listener address must be loopback, private, or declared VPN space")


def _extract_peer_sans(peer_cert: dict[str, object]) -> set[str]:
    sans: set[str] = set()
    for kind, value in peer_cert.get("subjectAltName", ()):  # type: ignore[union-attr]
        if kind in {"DNS", "IP Address"}:
            sans.add(str(value))
    return sans


def _require_peer_san(peer_cert: dict[str, object], allowed_sans: set[str]) -> None:
    if not allowed_sans:
        raise TLSConfigurationError("at least one declared peer SAN is required")
    peer_sans = _extract_peer_sans(peer_cert)
    if peer_sans.isdisjoint(allowed_sans):
        raise AuthorizationError("mTLS peer certificate is not in the declared peer allowlist")


def _is_timeout(exc: BaseException) -> bool:
    return isinstance(exc, (socket.timeout, TimeoutError, DeadlineExceededError))


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
        limits: FrameLimits = DEFAULT_LIMITS,
        backpressure: BackpressureController | None = None,
    ) -> None:
        self.bind_host = bind_host
        self.port = port
        self.credentials = credentials
        self.destination_root = Path(destination_root)
        self.validator = validator
        self.declared_listener_addresses = set(declared_listener_addresses)
        self.allowed_client_sans = set(allowed_client_sans)
        self.limits = limits
        self.backpressure = backpressure
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._closed = threading.Event()
        self.errors: list[BaseException] = []

    @property
    def address(self) -> tuple[str, int]:
        if self._socket is None:
            raise TLSConfigurationError("server is not started")
        host, port = self._socket.getsockname()[:2]
        return str(host), int(port)

    def validate_listener_config(self) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
        address = _literal_allowed_address(self.bind_host)
        if str(address) not in self.declared_listener_addresses:
            raise TLSConfigurationError("listener address must be explicitly declared before binding")
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
                    self.errors.append(exc)
                break
            threading.Thread(target=self._handle_socket, args=(context, client_sock), daemon=True).start()

    def _handle_socket(self, context: ssl.SSLContext, client_sock: socket.socket) -> None:
        try:
            with context.wrap_socket(client_sock, server_side=True) as tls_sock:
                peer_cert = tls_sock.getpeercert()
                if not peer_cert:
                    raise AuthorizationError("client certificate is required")
                _require_peer_san(peer_cert, self.allowed_client_sans)
                self._receive_upload(tls_sock)
        except BaseException as exc:
            if not self._closed.is_set() and not isinstance(exc, (ssl.SSLError, ConnectionError, OSError)):
                self.errors.append(exc)
        finally:
            try:
                client_sock.close()
            except OSError:
                pass

    def _receive_upload(self, tls_sock: ssl.SSLSocket) -> None:
        assembler = None
        try:
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
                    return
                if frame.frame_type == FRAME_CHUNK:
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
                    digest = assembler.finalize()
                    send_frame(
                        tls_sock,
                        encode_frame(
                            FRAME_ACK,
                            context=transfer_context.to_wire(),
                            extra={"object_sha256": digest},
                            limits=self.limits,
                        ),
                    )
                    return
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


class TrustedLanClient:
    """mTLS object sender for a declared trusted-LAN peer."""

    transport_id = "lan_mtls"

    def __init__(
        self,
        *,
        credentials: TLSCredentials,
        server_hostname: str,
        validator: AuthorizationLeaseValidator | None,
        limits: FrameLimits = DEFAULT_LIMITS,
        chunk_size: int | None = None,
        backpressure: BackpressureController | None = None,
    ) -> None:
        if not server_hostname:
            raise TLSConfigurationError("server_hostname is required for SAN verification")
        self.credentials = credentials
        self.server_hostname = server_hostname
        self.validator = validator
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
        token = cancellation or CancellationToken()
        source = ContentAddressedStore(source_root)
        if source.stat_size(context.object_sha256) != context.byte_length:
            raise ValueError("source object size does not match transfer context")
        ssl_context = _client_context(self.credentials)
        with socket.create_connection((host, port), timeout=timeout) as raw_sock:
            raw_sock.settimeout(timeout)
            with ssl_context.wrap_socket(raw_sock, server_hostname=self.server_hostname) as tls_sock:
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
        require_authorized(
            context,
            validator=self.validator,
            transport_id=self.transport_id,
            max_total_bytes=self.limits.max_total_bytes,
        )
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
        resumed_from = int(ack.header.get("resume_offset", 0))
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
        if ack.frame_type != FRAME_ACK or ack.header.get("object_sha256") != context.object_sha256:
            raise TLSConfigurationError("server finalization acknowledgement is invalid")
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
        )
