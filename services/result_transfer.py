"""Return a completed AIVM result to the desktop over lease-bound mTLS.

The desktop's Mesh Jobs window needs the *actual result bytes* of a completed
job, not just its digest. Those bytes live content-addressed in the worker's
owner-only AIVM result store. This module builds a ``result_loader`` closure —
the exact hook ``LocalJobPipeline.result`` calls — that moves one verified
result from the worker into the desktop over the same lease-bound Unisync mTLS
transport used for workloads, then reads the received bytes back from the
desktop's inbox.

Scope and honesty:

* This uses the ``existing`` prepare-mode of the mTLS gate: the verified result
  is staged into a source outbox (as ``stage-result`` does in-mesh) and the
  lease-bound ``send``/``serve`` moves it to the destination inbox. The bytes
  reach the desktop over TLS 1.3 mutual-auth only, never over the carrier.
* Each fetch performs a fresh enrollment + CA + signed lease. That proves the
  mechanism end-to-end but is NOT the production shape (persistent enrollment
  reused across fetches) and NOT a physical two-host run (it drives the
  in-process ``LocalMeshCarrier`` against a worker state dir on this host). Both
  remain documented gaps; nothing here claims otherwise.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from services.unisync.mesh_smoke import (
    HybridMeshCarrier,
    LocalMeshCarrier,
    MeshNodeConfig,
    MeshSmokeConfig,
    run_mesh_mtls_smoke,
)
from services.unisync.storage import ContentAddressedStore

_SHA256_RE = re.compile(r"[0-9a-f]{64}")

# (digest, remote_source_state_dir) -> byte_length, or None if the result is not
# present in the worker's AIVM store. The implementation stages the completed
# result into the fresh remote source outbox over pinned SSH (as stage-result
# does), so the desktop-initiated pull can return it.
StageOnWorker = Callable[[str, str], "int | None"]


def _owner_only(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


class ResultTransferError(RuntimeError):
    """A completed result could not be returned over the mesh."""


def build_result_loader(
    *,
    worker_state_dir: Path,
    workspace: Path,
    account_id: str,
    subject_id: str,
    worker_node_id: str,
    desktop_node_id: str,
    python: str,
    repo: str,
    timeout_seconds: int = 30,
    lease_ttl_seconds: int = 90,
) -> Callable[[str], bytes | None]:
    """Build the ``result_loader`` that returns result bytes over mesh mTLS.

    ``worker_state_dir`` is the worker's owner-only state root containing
    ``aivm/results/<digest>``. ``workspace`` is a desktop-owned scratch root for
    per-fetch enrollment/CA/lease state and the destination inbox. The returned
    closure takes an output digest and returns the exact verified result bytes,
    or ``None`` if the result is absent or the bound transfer does not deliver
    it. It never returns unverified content: the destination bytes must re-hash
    to the requested digest.
    """

    worker_state_dir = Path(worker_state_dir)
    workspace = _owner_only(Path(workspace))

    def _stage_verified_result(digest: str, source_outbox: Path) -> int:
        """Read + verify the AIVM result and stage it into a source outbox.

        This mirrors ``worker_cli.stage_result``: the result is re-hashed before
        it is placed into the outbox, and the stored digest is checked to equal
        the request. Returns the exact byte length for the transfer bound.
        """

        result_path = worker_state_dir / "aivm" / "results" / digest
        try:
            data = result_path.read_bytes()
        except OSError as exc:
            raise ResultTransferError("result absent from AIVM result store") from exc
        if hashlib.sha256(data).hexdigest() != digest:
            raise ResultTransferError("stored result does not match its digest")
        staged = ContentAddressedStore(source_outbox).put_bytes(data)
        if staged != digest:
            raise ResultTransferError("staged object digest mismatch")
        return len(data)

    def load(output_sha256: str) -> bytes | None:
        if not isinstance(output_sha256, str) or not _SHA256_RE.fullmatch(output_sha256):
            return None
        fetch_dir = Path(tempfile.mkdtemp(prefix="result-", dir=str(workspace)))
        try:
            source_state = _owner_only(fetch_dir / "source")
            dest_state = _owner_only(fetch_dir / "destination")
            byte_length = _stage_verified_result(
                output_sha256, source_state / "outbox"
            )
            config = MeshSmokeConfig(
                account_id=account_id,
                subject_id=subject_id,
                carrier="local",
                known_hosts=None,
                identity_file=None,
                timeout_seconds=timeout_seconds,
                object_bytes=byte_length,
                lease_ttl_seconds=lease_ttl_seconds,
                registry_dir=fetch_dir / "registry",
                state_db=fetch_dir / "vsource.sqlite3",
                output=fetch_dir / "evidence.json",
                source=MeshNodeConfig(
                    node_id=worker_node_id,
                    python=python,
                    repo=repo,
                    state_dir=str(source_state),
                    tls_sans=("worker.result.local",),
                    ssh_alias=None,
                    ssh_host_fingerprint=None,
                ),
                destination=MeshNodeConfig(
                    node_id=desktop_node_id,
                    python=python,
                    repo=repo,
                    state_dir=str(dest_state),
                    tls_sans=("127.0.0.1",),
                    ssh_alias=None,
                    ssh_host_fingerprint=None,
                ),
                bind_address="127.0.0.1",
                port=0,
                server_hostname="127.0.0.1",
                declared_vpn_cidrs=(),
                prepare_mode="existing",
                existing_object_sha256=output_sha256,
            )
            evidence = run_mesh_mtls_smoke(config, LocalMeshCarrier(timeout_seconds=timeout_seconds))
            if evidence.get("transfer", {}).get("object_sha256") != output_sha256:
                return None
            # Read the received bytes from the DESKTOP (destination) inbox — the
            # only path they arrive by is the bound mTLS receipt, not the carrier.
            inbox = ContentAddressedStore(dest_state / "inbox")
            if not inbox.has(output_sha256):
                return None
            received = inbox.read_bytes(output_sha256)
            if hashlib.sha256(received).hexdigest() != output_sha256:
                return None
            return received
        finally:
            shutil.rmtree(fetch_dir, ignore_errors=True)

    return load


def build_pull_result_loader(
    *,
    stage_on_worker: StageOnWorker,
    worker_source_dir_factory: Callable[[], str],
    cleanup_worker_dir: Callable[[str], None],
    carrier: object,
    workspace: Path,
    account_id: str,
    subject_id: str,
    worker_node_id: str,
    worker_python: str,
    worker_repo: str,
    worker_ssh_alias: str,
    worker_ssh_fingerprint: str,
    worker_listen_ip: str,
    desktop_node_id: str,
    desktop_python: str,
    desktop_repo: str,
    desktop_san: str,
    timeout_seconds: int = 60,
    lease_ttl_seconds: int = 120,
) -> Callable[[str], bytes | None]:
    """Build a ``result_loader`` that returns result bytes via a desktop pull.

    Firewall-free result return: the worker (remote, pinned SSH) stages the
    completed result and listens; this desktop dials OUTBOUND and receives it
    over lease-bound mTLS, needing no inbound port. ``stage_on_worker`` performs
    the SSH-side staging into a fresh remote source outbox and returns the byte
    length (or ``None`` when the result is absent). The returned closure yields
    the exact verified bytes, or ``None`` on absence/verification failure.
    """

    workspace = _owner_only(Path(workspace))

    def load(output_sha256: str) -> bytes | None:
        if not isinstance(output_sha256, str) or not _SHA256_RE.fullmatch(output_sha256):
            return None
        source_state_dir = worker_source_dir_factory()
        fetch_dir = Path(tempfile.mkdtemp(prefix="pull-", dir=str(workspace)))
        try:
            byte_length = stage_on_worker(output_sha256, source_state_dir)
            if not isinstance(byte_length, int) or byte_length <= 0:
                return None
            dest_state = _owner_only(fetch_dir / "destination")
            config = MeshSmokeConfig(
                account_id=account_id,
                subject_id=subject_id,
                carrier="hybrid",
                known_hosts=None,
                identity_file=None,
                timeout_seconds=timeout_seconds,
                object_bytes=byte_length,
                lease_ttl_seconds=lease_ttl_seconds,
                registry_dir=fetch_dir / "registry",
                state_db=fetch_dir / "vsource.sqlite3",
                output=fetch_dir / "evidence.json",
                source=MeshNodeConfig(
                    node_id=worker_node_id,
                    python=worker_python,
                    repo=worker_repo,
                    state_dir=source_state_dir,
                    tls_sans=("worker.result.mesh",),
                    ssh_alias=worker_ssh_alias,
                    ssh_host_fingerprint=worker_ssh_fingerprint,
                ),
                destination=MeshNodeConfig(
                    node_id=desktop_node_id,
                    python=desktop_python,
                    repo=desktop_repo,
                    state_dir=str(dest_state),
                    tls_sans=(desktop_san,),
                    ssh_alias=None,
                    ssh_host_fingerprint=None,
                ),
                bind_address=worker_listen_ip,
                port=0,
                server_hostname=desktop_san,
                declared_vpn_cidrs=(),
                prepare_mode="existing",
                existing_object_sha256=output_sha256,
                pull=True,
            )
            evidence = run_mesh_mtls_smoke(config, carrier)
            if evidence.get("transfer", {}).get("object_sha256") != output_sha256:
                return None
            inbox = ContentAddressedStore(dest_state / "inbox")
            if not inbox.has(output_sha256):
                return None
            received = inbox.read_bytes(output_sha256)
            if hashlib.sha256(received).hexdigest() != output_sha256:
                return None
            return received
        finally:
            try:
                cleanup_worker_dir(source_state_dir)
            except Exception:
                pass
            shutil.rmtree(fetch_dir, ignore_errors=True)

    return load
