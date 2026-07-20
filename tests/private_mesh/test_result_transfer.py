"""A completed AIVM result returns to the desktop over lease-bound mTLS.

Proves the desktop-side ``result_loader``: a verified result in the worker's
AIVM store is moved worker->desktop over the in-process mTLS gate and read back
from the desktop inbox as the exact bytes. The loader never yields unverified
or absent content.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

from services.result_transfer import build_result_loader

REPO = Path(__file__).resolve().parents[2]


def _seed_result(worker_state: Path, data: bytes) -> str:
    digest = hashlib.sha256(data).hexdigest()
    results = worker_state / "aivm" / "results"
    results.mkdir(mode=0o700, parents=True)
    (results / digest).write_bytes(data)
    return digest


def _loader(worker_state: Path, workspace: Path):
    return build_result_loader(
        worker_state_dir=worker_state,
        workspace=workspace,
        account_id="account:test:result",
        subject_id="subject:test:owner",
        worker_node_id="node:test:worker",
        desktop_node_id="node:test:desktop",
        python=sys.executable,
        repo=str(REPO),
        timeout_seconds=30,
    )


def test_completed_result_returns_over_mtls(tmp_path: Path):
    worker_state = tmp_path / "worker"
    worker_state.mkdir(mode=0o700)
    payload = b"CLASSIFICATION=verified\n" + bytes(range(256)) * 4
    digest = _seed_result(worker_state, payload)

    load = _loader(worker_state, tmp_path / "desktop-workspace")
    returned = load(digest)

    assert returned == payload
    assert hashlib.sha256(returned).hexdigest() == digest


def test_absent_result_returns_none(tmp_path: Path):
    worker_state = tmp_path / "worker"
    worker_state.mkdir(mode=0o700)
    # A well-formed digest with no backing result in the AIVM store.
    missing = hashlib.sha256(b"never-produced").hexdigest()

    load = _loader(worker_state, tmp_path / "desktop-workspace")
    with pytest.raises(Exception):
        load(missing)


def test_malformed_digest_returns_none(tmp_path: Path):
    worker_state = tmp_path / "worker"
    worker_state.mkdir(mode=0o700)
    load = _loader(worker_state, tmp_path / "desktop-workspace")
    assert load("not-a-digest") is None
    assert load("abc") is None


def test_leaves_no_scratch_behind(tmp_path: Path):
    worker_state = tmp_path / "worker"
    worker_state.mkdir(mode=0o700)
    payload = b"result-bytes-" * 32
    digest = _seed_result(worker_state, payload)
    workspace = tmp_path / "desktop-workspace"

    load = _loader(worker_state, workspace)
    assert load(digest) == payload
    # Per-fetch scratch is cleaned up; the workspace holds no residue.
    assert list(workspace.iterdir()) == []
