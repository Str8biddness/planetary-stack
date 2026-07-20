"""Synthesusd desktop-initiated pull result_loader wiring.

Covers the pure helpers that construct the firewall-free result pull: the
pinned-ssh argv is hardened, the worker listen address is parsed from ssh -G,
and loader construction fails closed (returns None) when the address cannot be
resolved. The full pull path is proven physically elsewhere.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

import synthesusd


def _fake_config():
    target = SimpleNamespace(
        node_id="node:private-mesh:worker",
        ssh_alias="worker-alias",
        ssh_host_fingerprint="SHA256:" + "A" * 43,
        remote_python="/opt/venv/bin/python",
        remote_repo="/home/worker/repo",
        remote_state_dir="/home/worker/state",
    )
    return SimpleNamespace(
        target=target,
        account_id="account:test:home",
        subject_id="subject:test:owner",
        known_hosts=Path("/tmp/known_hosts"),
        ssh_identity=Path("/tmp/id_ed25519"),
    )


def test_pinned_ssh_argv_is_hardened():
    argv = synthesusd._pinned_ssh_argv(_fake_config(), "echo hi")
    joined = " ".join(argv)
    for flag in (
        "BatchMode=yes",
        "PasswordAuthentication=no",
        "StrictHostKeyChecking=yes",
        "UserKnownHostsFile=/tmp/known_hosts",
        "GlobalKnownHostsFile=/dev/null",
        "IdentitiesOnly=yes",
        "HostKeyAlgorithms=ssh-ed25519",
    ):
        assert flag in joined, flag
    assert "/tmp/id_ed25519" in argv
    assert argv[-2] == "worker-alias"
    assert argv[-1] == "echo hi"


def test_resolve_worker_listen_ip_parses_ssh_g(monkeypatch):
    def fake_run(argv, capture_output, text, timeout, check):
        assert argv[:2] == ["ssh", "-G"]
        return SimpleNamespace(
            returncode=0,
            stdout="user root\nhostname 192.168.68.54\nport 22\n",
        )

    monkeypatch.setattr(synthesusd.subprocess, "run", fake_run)
    assert synthesusd._resolve_worker_listen_ip("worker-alias") == "192.168.68.54"


def test_resolve_worker_listen_ip_fails_closed(monkeypatch):
    def fake_run(argv, capture_output, text, timeout, check):
        return SimpleNamespace(returncode=255, stdout="")

    monkeypatch.setattr(synthesusd.subprocess, "run", fake_run)
    assert synthesusd._resolve_worker_listen_ip("worker-alias") is None


def test_pull_loader_none_when_worker_unresolvable(monkeypatch):
    # If the worker address cannot be resolved, no loader is built (result bytes
    # are simply unavailable, never fatal).
    monkeypatch.setattr(synthesusd, "_resolve_worker_listen_ip", lambda alias: None)
    assert synthesusd._build_pull_result_loader(_fake_config()) is None
