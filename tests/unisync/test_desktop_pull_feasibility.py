"""Feasibility guard for desktop-initiated result pull (the firewall-free design).

The sellable result-return design has the DESKTOP dial OUTBOUND to the worker
(so a customer's desktop never opens an inbound port) yet act as the mTLS
*receiver*. That only works because a TLS server/client role is independent of
which side opened the TCP connection: the TCP dialer can run `server_side=True`.

This test pins that invariant with real sockets and mutual-certificate auth:
the TCP *listener* (worker role) is the TLS CLIENT + sender, and the TCP
*dialer* (desktop role) is the TLS SERVER + receiver, over TLS 1.3, each
verifying the other's certificate. If this ever regresses, the design's premise
is gone. It uses throwaway EC certs and does not touch the production transport.
"""

from __future__ import annotations

import datetime
import socket
import ssl
import threading
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

_PAYLOAD = b'{"label":"positive","scores":{"negative":0.414381,"positive":0.585619}}'


def _make_cert(common_name: str, directory: Path) -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(minutes=30))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(common_name)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_path = directory / f"{common_name}.crt"
    key_path = directory / f"{common_name}.key"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return str(cert_path), str(key_path)


def test_tcp_dialer_can_be_tls_server_and_receiver(tmp_path: Path):
    desk_crt, desk_key = _make_cert("desktop", tmp_path)
    work_crt, work_key = _make_cert("worker", tmp_path)
    shared: dict[str, object] = {}
    ready = threading.Event()

    def worker_listener() -> None:
        # Worker LISTENS (inbound — acceptable for a provisioned worker) but is
        # the TLS CLIENT + object SENDER.
        listen = socket.socket()
        listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listen.bind(("127.0.0.1", 0))
        listen.listen(1)
        shared["port"] = listen.getsockname()[1]
        ready.set()
        conn, _ = listen.accept()
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        ctx.load_cert_chain(work_crt, work_key)
        ctx.load_verify_locations(desk_crt)
        ctx.check_hostname = True
        tls = ctx.wrap_socket(conn, server_side=False, server_hostname="desktop")
        shared["negotiated"] = tls.version()
        shared["worker_saw_desktop_cert"] = bool(tls.getpeercert())
        tls.sendall(_PAYLOAD)
        tls.close()
        listen.close()

    thread = threading.Thread(target=worker_listener)
    thread.start()
    try:
        ready.wait(timeout=10)
        # Desktop DIALS OUTBOUND (no inbound firewall) but is the TLS SERVER +
        # object RECEIVER, requiring the worker's client certificate.
        raw = socket.create_connection(("127.0.0.1", shared["port"]), timeout=10)
        server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        server_ctx.load_cert_chain(desk_crt, desk_key)
        server_ctx.load_verify_locations(work_crt)
        server_ctx.verify_mode = ssl.CERT_REQUIRED
        tls = server_ctx.wrap_socket(raw, server_side=True)
        desktop_saw_worker_cert = bool(tls.getpeercert())
        received = b""
        while len(received) < len(_PAYLOAD):
            chunk = tls.recv(4096)
            if not chunk:
                break
            received += chunk
        tls.close()
    finally:
        thread.join(timeout=10)

    assert shared["negotiated"] == "TLSv1.3"
    assert shared["worker_saw_desktop_cert"] is True  # worker verified desktop
    assert desktop_saw_worker_cert is True            # desktop verified worker
    assert received == _PAYLOAD                        # dialer received the bytes
