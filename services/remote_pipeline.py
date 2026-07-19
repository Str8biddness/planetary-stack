"""Secure construction of the desktop→worker remote job pipeline.

Release A is a same-account private mesh: the desktop controller is the trust
root. This module gives the controller a persistent, owner-only Ed25519
signing identity (controller + scheduler roles), enrolls the configured worker
over the pinned SSH carrier, registers its signed inventory in a persistent
vSource control plane, and constructs a `LocalJobPipeline` whose backend runs
the real model on that worker.

Unlike the placeholder wiring this replaces, every document is really signed
and every binding is real: no fabricated keys, no fabricated signatures. If
the worker cannot be reached (or config is absent), construction fails closed
and returns None — the controller reports remote jobs unavailable rather than
crashing or pretending.

Not yet included (documented, not faked): returning the result *bytes* to the
desktop over mTLS. The signed response already carries the content-addressed
result digest and execution evidence, which the desktop presents; fetching the
bytes over the lease-bound mTLS transfer is a separate reviewed step.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import os
import stat
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from contracts.chal_vsource.v1.models import CapabilityDocument
from services.job_pipeline import LocalJobPipeline
from services.private_mesh.ssh_smoke import (
    MemoryResolver,
    NodeTarget,
    SshCarrier,
    _validate_enrollment,
)
from services.remote_backend import RemoteExecutionBackend
from services.remote_worker_config import RemoteWorkerConfig
from services.vsource import (
    Ed25519DocumentSigner,
    KeyRecord,
    LocalVSourceControlPlane,
    VSourceStatus,
    sign_contract_document,
)

log = logging.getLogger("synthesusd.remote")

_WIRE_TIME = "%Y-%m-%dT%H:%M:%SZ"
_RESOURCE_VECTOR = {
    "cpu_millicores": 1000,
    "memory_bytes": 1_073_741_824,
    "gpu_count": 0,
    "gpu_memory_bytes": 0,
    "storage_bytes": 0,
    "ingress_bps": 0,
    "egress_bps": 0,
}


class RemotePipelineError(RuntimeError):
    """Fail-closed construction error."""


class _ClockObject:
    """Adapt a ``Callable[[], datetime]`` to the control plane's ``.now()``."""

    def __init__(self, fn: Callable[[], datetime]) -> None:
        self._fn = fn

    def now(self) -> datetime:
        return self._fn()


def _owner_only_dir(path: Path) -> Path:
    path = path.expanduser()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise RemotePipelineError("authority directory is not a real directory")
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise RemotePipelineError("authority directory is not owner-only")
    return path


def _load_or_create_signer(directory: Path, filename: str, key_id: str) -> Ed25519DocumentSigner:
    """Load a persistent Ed25519 signer or create it owner-only (0600)."""

    key_path = directory / filename
    if key_path.exists():
        info = key_path.lstat()
        if stat.S_ISLNK(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
            raise RemotePipelineError("authority key file is not owner-only")
        raw = key_path.read_bytes()
        if len(raw) != 32:
            raise RemotePipelineError("authority key file is corrupt")
        return Ed25519DocumentSigner(key_id, Ed25519PrivateKey.from_private_bytes(raw))
    private_key = Ed25519PrivateKey.generate()
    raw = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(key_path, flags, 0o600)
    try:
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)
    return Ed25519DocumentSigner(key_id, private_key)


def _public_bytes(signer: Ed25519DocumentSigner) -> bytes:
    return signer.private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def _key_payload(record: KeyRecord) -> dict[str, Any]:
    import base64

    return {
        "key_id": record.key_id,
        "public_key_base64": base64.urlsafe_b64encode(record.public_key_bytes())
        .rstrip(b"=")
        .decode("ascii"),
        "account_id": record.account_id,
        "audiences": sorted(record.audiences),
        "subject_id": record.subject_id,
        "node_id": record.node_id,
    }


def build_remote_pipeline(
    config: RemoteWorkerConfig,
    *,
    state_dir: Path,
    clock: Callable[[], datetime],
    carrier: Any | None = None,
) -> LocalJobPipeline | None:
    """Construct the secure remote job pipeline, or None if unavailable.

    Fails closed (returns None, logs) when the worker cannot be enrolled.
    Raises RemotePipelineError only for owner-only state integrity problems.
    """

    directory = _owner_only_dir(state_dir)
    account_id = config.account_id
    subject_id = config.subject_id
    node_id = config.target.node_id

    controller = _load_or_create_signer(directory, "controller.key", "key:controller:desktop")
    scheduler = _load_or_create_signer(directory, "scheduler.key", "key:scheduler:desktop")
    scheduler_id = "scheduler:desktop:001"
    capability_id = f"capability:remote:{secrets.token_hex(8)}"

    active_carrier = carrier or SshCarrier(
        known_hosts=config.known_hosts,
        identity_file=config.ssh_identity,
        timeout_seconds=60,
    )
    try:
        enrollment = active_carrier.enroll(
            config.target, account_id=account_id, subject_id=subject_id
        )
        inventory, node_public = _validate_enrollment(
            config.target, enrollment, account_id=account_id
        )
    except Exception as exc:
        log.warning("remote worker %s unreachable; remote jobs unavailable: %s", node_id, exc)
        return None

    resolver = MemoryResolver()
    resolver.add(
        KeyRecord(
            key_id=controller.key_id,
            public_key=_public_bytes(controller),
            account_id=account_id,
            audiences=(scheduler_id,),
            subject_id=subject_id,
        )
    )
    node_record = KeyRecord(
        key_id=enrollment["key_id"],
        public_key=node_public,
        account_id=account_id,
        audiences=(scheduler_id,),
        subject_id=subject_id,
        node_id=node_id,
    )
    resolver.add(node_record)

    control_plane = LocalVSourceControlPlane(
        directory / "vsource.sqlite3",
        key_resolver=resolver,
        signer=scheduler,
        clock=_ClockObject(clock),
        scheduler_id=scheduler_id,
    )
    registered = control_plane.register_inventory(inventory)
    # Across desktop restarts the same worker is already registered in the
    # persistent control plane; every replay variant means "already known",
    # which is not a failure for this same-account cell. Only genuine
    # verification/availability failures fail closed.
    _registered_ok = {
        VSourceStatus.ACCEPTED,
        VSourceStatus.IDEMPOTENT_REPLAY,
        VSourceStatus.REPLAY,
    }
    if registered.status not in _registered_ok:
        log.warning("worker inventory rejected; remote jobs unavailable: %s", registered.status)
        return None

    worker_keys = sorted(
        [
            _key_payload(
                KeyRecord(
                    key_id=controller.key_id,
                    public_key=_public_bytes(controller),
                    account_id=account_id,
                    audiences=(node_id,),
                    subject_id=subject_id,
                )
            ),
            _key_payload(
                KeyRecord(
                    key_id=scheduler.key_id,
                    public_key=_public_bytes(scheduler),
                    account_id=account_id,
                    audiences=(node_id,),
                )
            ),
            _key_payload(
                KeyRecord(
                    key_id=node_record.key_id,
                    public_key=node_record.public_key_bytes(),
                    account_id=account_id,
                    audiences=(node_id,),
                    subject_id=subject_id,
                    node_id=node_id,
                )
            ),
        ],
        key=lambda value: value["key_id"],
    )

    backend = RemoteExecutionBackend(
        carrier=active_carrier,
        keys=worker_keys,
        inventory=inventory.model_dump(mode="json", by_alias=True),
        **config.to_backend_kwargs(),
    )

    # One stable capability per session: all jobs share `_CAPABILITY_ID`, so the
    # signed document must be identical across submissions (otherwise the second
    # allocation collides as a capability replay). Built once and reused; it is
    # refreshed only when it nears expiry so long-lived controllers keep working.
    _capability_cache: dict[str, Any] = {}

    def capability_provider() -> CapabilityDocument:
        now = clock()
        cached = _capability_cache.get("doc")
        cached_nb = _capability_cache.get("not_before")
        if cached is not None and cached_nb is not None and (now - cached_nb).total_seconds() < 2700:
            return cached
        payload = {
            "schema": "planetary.chal.capability.v1",
            "capability_id": capability_id,
            "issuer_id": "controller:desktop",
            "subject_id": subject_id,
            "account_id": account_id,
            "audience_node_ids": [node_id],
            "actions": ["execute", "reserve"],
            "constraints": {
                "resources": dict(_RESOURCE_VECTOR),
                "minimum_attestation": "unverified",
                # The node agent advertises the "evaluation" workload kind for
                # the bounded model executor profile.
                "workload_kinds": ["evaluation"],
                "transports": ["local_process"],
                "resource_prefixes": ["chal://aivm/"],
            },
            "not_before": now.strftime(_WIRE_TIME),
            "ttl_seconds": 3600,
            "nonce": hashlib.sha256(os.urandom(16)).hexdigest()[:32],
            "revocation_epoch": 0,
            "delegable": False,
        }
        doc = sign_contract_document(CapabilityDocument, payload, controller)
        _capability_cache["doc"] = doc
        _capability_cache["not_before"] = now
        return doc

    return LocalJobPipeline(
        control_plane=control_plane,
        backend=backend,
        request_signer=controller,
        capability_provider=capability_provider,
        authenticated_subject_id=subject_id,
        account_id=account_id,
        capability_id=capability_id,
        device_uri="chal://aivm/evaluation",
        clock=clock,
        resource_vector=dict(_RESOURCE_VECTOR),
    )
