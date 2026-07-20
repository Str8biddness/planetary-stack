"""HybridMeshCarrier routes per-node and the hybrid topology guards fail closed.

The hybrid carrier is the desktop-as-destination topology: the local node (no
SSH alias) runs its mesh CLI as a local subprocess while the remote node (SSH
alias + pinned host key) runs over the pinned SSH carrier. A full physical
transfer additionally needs the local receiver to accept the worker's inbound
mTLS connection; these tests cover the routing and the run-time topology guards
without a live transfer.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from services.unisync.mesh_common import MeshSecurityError
from services.unisync.mesh_smoke import (
    HybridMeshCarrier,
    LocalMeshCarrier,
    MeshNodeConfig,
    MeshSmokeConfig,
    SshMeshCarrier,
    run_mesh_mtls_smoke,
)

REPO = Path(__file__).resolve().parents[2]


def _local_node(node_id: str, state_dir: str) -> MeshNodeConfig:
    return MeshNodeConfig(
        node_id=node_id,
        python=sys.executable,
        repo=str(REPO),
        state_dir=state_dir,
        tls_sans=("127.0.0.1",),
        ssh_alias=None,
        ssh_host_fingerprint=None,
    )


def _ssh_node(node_id: str, state_dir: str) -> MeshNodeConfig:
    return MeshNodeConfig(
        node_id=node_id,
        python=sys.executable,
        repo=str(REPO),
        state_dir=state_dir,
        tls_sans=("worker.mesh",),
        ssh_alias="worker",
        ssh_host_fingerprint="SHA256:" + "A" * 43,
    )


def _carrier(tmp_path: Path) -> HybridMeshCarrier:
    kh = tmp_path / "known_hosts"
    kh.write_text("worker ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAExampleKeyMaterial\n")
    return HybridMeshCarrier(known_hosts=kh, identity_file=None, timeout_seconds=15)


def test_routes_local_and_ssh_nodes_to_distinct_subcarriers(tmp_path: Path):
    carrier = _carrier(tmp_path)
    local = _local_node("node:desktop", str(tmp_path / "desktop"))
    remote = _ssh_node("node:worker", str(tmp_path / "worker"))
    assert isinstance(carrier._carrier_for(local), LocalMeshCarrier)
    assert isinstance(carrier._carrier_for(remote), SshMeshCarrier)
    # The remote node routes to the SAME pinned SSH carrier instance every time.
    assert carrier._carrier_for(remote) is carrier._carrier_for(_ssh_node("n2", "x"))


def _hybrid_config(source: MeshNodeConfig, destination: MeshNodeConfig, tmp_path: Path) -> MeshSmokeConfig:
    return MeshSmokeConfig(
        account_id="account:test:mesh",
        subject_id="subject:test:owner",
        carrier="hybrid",
        known_hosts=tmp_path / "known_hosts",
        identity_file=None,
        timeout_seconds=15,
        object_bytes=16,
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
        prepare_mode="existing",
        existing_object_sha256="0" * 64,
    )


def test_rejects_ssh_destination(tmp_path: Path):
    # The desktop destination must be local; an SSH destination is refused.
    source = _ssh_node("node:worker", str(tmp_path / "worker"))
    destination = _ssh_node("node:desktop", str(tmp_path / "desktop"))
    config = _hybrid_config(source, destination, tmp_path)
    with pytest.raises(MeshSecurityError, match="destination .* must be local"):
        run_mesh_mtls_smoke(config, _carrier(tmp_path))


def test_rejects_local_source(tmp_path: Path):
    # The worker source must be a pinned SSH endpoint; a local source is refused.
    source = _local_node("node:worker", str(tmp_path / "worker"))
    destination = _local_node("node:desktop", str(tmp_path / "desktop"))
    config = _hybrid_config(source, destination, tmp_path)
    with pytest.raises(MeshSecurityError, match="source .* pinned SSH"):
        run_mesh_mtls_smoke(config, _carrier(tmp_path))
