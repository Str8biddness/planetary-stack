"""In-process unit coverage for the three-node cell acceptance harness.

These tests exercise the real ``worker_cli.execute_job`` boundary through the
``LocalCarrier`` pattern (the same one used by ``test_worker_cli.py``); they do
NOT mock the worker.  They validate the orchestration logic only -- this is the
harness, not a physical three-node acceptance run.
"""

from __future__ import annotations

import hashlib
import sqlite3
import stat
from pathlib import Path
from typing import Any

import pytest

from services.private_mesh.cell_smoke import run_three_node_cell
from services.private_mesh.ssh_smoke import NodeTarget
from services.private_mesh.worker_cli import enroll_node, execute_job


ACCOUNT = "account:owner:private-mesh"
SUBJECT = "node-agent:private-mesh"


class LocalCarrier:
    """In-process carrier that drives the real worker CLI (no mocks)."""

    def verify_pinned_host(self, target: NodeTarget) -> dict[str, Any]:
        return {
            "ssh_alias": target.ssh_alias,
            "resolved_host": target.ssh_alias,
            "resolved_port": 22,
            "ssh_host_fingerprint": target.ssh_host_fingerprint,
        }

    def enroll(
        self,
        target: NodeTarget,
        *,
        account_id: str,
        subject_id: str,
    ) -> dict[str, Any]:
        result = enroll_node(
            state_dir=Path(target.remote_state_dir),
            account_id=account_id,
            node_id=target.node_id,
            authenticated_subject_id=subject_id,
        )
        result["hostname"] = f"host-{target.ssh_alias}"
        return result

    def execute(self, target: NodeTarget, job: dict[str, Any]) -> dict[str, Any]:
        result = execute_job(state_dir=Path(target.remote_state_dir), payload=job)
        result["hostname"] = f"host-{target.ssh_alias}"
        return result


class DisappearingCarrier(LocalCarrier):
    """LocalCarrier that lets one node enroll once, then it "disappears".

    The first ``enroll`` for ``vanish_node_id`` succeeds (initial enrollment);
    every subsequent contact of that node raises, simulating a worker that
    becomes unreachable after allocation.  ``execute`` on that node also raises.
    """

    def __init__(self, vanish_node_id: str) -> None:
        self._vanish = vanish_node_id
        self._enroll_calls: dict[str, int] = {}

    def enroll(
        self,
        target: NodeTarget,
        *,
        account_id: str,
        subject_id: str,
    ) -> dict[str, Any]:
        count = self._enroll_calls.get(target.node_id, 0) + 1
        self._enroll_calls[target.node_id] = count
        if target.node_id == self._vanish and count >= 2:
            raise ConnectionError("worker vanished after allocation")
        return super().enroll(
            target, account_id=account_id, subject_id=subject_id
        )

    def execute(self, target: NodeTarget, job: dict[str, Any]) -> dict[str, Any]:
        if target.node_id == self._vanish:
            raise ConnectionError("worker vanished after allocation")
        return super().execute(target, job)


def _targets(directory: str) -> list[NodeTarget]:
    return [
        NodeTarget(
            node_id=f"node:owner:cell{i}",
            ssh_alias=f"cell{i}",
            ssh_host_fingerprint=f"SHA256:{character * 43}",
            remote_python="/fixed/python",
            remote_repo="/fixed/repo",
            remote_state_dir=f"{directory}/state{i}",
        )
        for i, character in enumerate(("A", "B", "C"))
    ]


def test_cell_requires_exactly_three_distinct_nodes(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="exactly three worker targets"):
        run_three_node_cell(
            _targets(str(tmp_path))[:2],
            account_id=ACCOUNT,
            subject_id=SUBJECT,
            carrier=LocalCarrier(),
        )


def test_three_node_cell_runs_one_execution_node_and_verifies_chain(
    tmp_path: Path,
) -> None:
    state_db = tmp_path / "cell-smoke.sqlite3"
    evidence = run_three_node_cell(
        _targets(str(tmp_path)),
        account_id=ACCOUNT,
        subject_id=SUBJECT,
        carrier=LocalCarrier(),
        execution_node_index=1,
        state_db_path=state_db,
    )

    assert evidence["passed"] is True
    assert evidence["degraded"] is False
    assert evidence["node_count"] == 3
    assert evidence["contract_transport"] == "local_process"
    assert evidence["execution_node"] == "node:owner:cell1"

    # Three enrolled members, distinct identities, distinct hostnames.
    assert len(evidence["members"]) == 3
    assert len({m["node_id"] for m in evidence["members"]}) == 3
    assert len({m["hostname"] for m in evidence["members"]}) == 3
    assert len({m["node_key_fingerprint"] for m in evidence["members"]}) == 3
    execution_members = [m for m in evidence["members"] if m["is_execution_node"]]
    assert len(execution_members) == 1
    assert execution_members[0]["node_id"] == "node:owner:cell1"
    assert all(m["reachable"] for m in evidence["members"])

    # Explicit non-claims must be present and false.
    assert evidence["claims"]["physical_cell_proven"] is False
    assert evidence["claims"]["podman_model_execution"] is False
    assert evidence["claims"]["unisync_mtls_proven"] is False
    assert evidence["claims"]["three_distinct_node_signing_keys"] is True

    # Signed-document digests recorded for the execution node.
    execution = evidence["execution"]
    for key in (
        "request_sha256",
        "capability_sha256",
        "active_lease_sha256",
        "released_lease_sha256",
        "response_sha256",
        "report_sha256",
    ):
        assert len(execution[key]) == 64
    assert execution["report_size_bytes"] > 0
    assert len(execution["worker_trust_records"]) == 3

    # Persistent state was actually written and the recorded digest matches.
    assert evidence["sqlite_state"]["persistent"] is True
    assert stat.S_IMODE(state_db.stat().st_mode) == 0o600
    assert evidence["sqlite_state"]["sha256"] == hashlib.sha256(
        state_db.read_bytes()
    ).hexdigest()
    with sqlite3.connect(f"file:{state_db}?mode=ro", uri=True) as connection:
        # Exactly one fenced lease was allocated (single execution node).
        assert connection.execute("SELECT count(*) FROM leases").fetchone() == (1,)


def test_non_execution_worker_disappearance_completes_degraded(
    tmp_path: Path,
) -> None:
    # Execution node is index 0; a NON-execution node (index 2) disappears
    # after allocation.  The cell must still complete on the healthy node.
    carrier = DisappearingCarrier("node:owner:cell2")
    evidence = run_three_node_cell(
        _targets(str(tmp_path)),
        account_id=ACCOUNT,
        subject_id=SUBJECT,
        carrier=carrier,
        execution_node_index=0,
    )

    assert evidence["passed"] is True
    assert evidence["degraded"] is True
    assert evidence["execution_node"] == "node:owner:cell0"

    vanished = next(
        m for m in evidence["members"] if m["node_id"] == "node:owner:cell2"
    )
    # The unreachable member is honestly recorded, never fabricated as healthy.
    assert vanished["reachable"] is False
    assert "ConnectionError" in vanished["health_reason"]
    assert vanished["is_execution_node"] is False

    # The execution node still produced a fully verified signed chain.
    assert len(evidence["execution"]["response_sha256"]) == 64
    assert evidence["execution"]["report_size_bytes"] > 0


def test_worker_disappearance_can_fail_closed_with_explicit_reason(
    tmp_path: Path,
) -> None:
    carrier = DisappearingCarrier("node:owner:cell2")
    with pytest.raises(RuntimeError, match="failed closed") as excinfo:
        run_three_node_cell(
            _targets(str(tmp_path)),
            account_id=ACCOUNT,
            subject_id=SUBJECT,
            carrier=carrier,
            execution_node_index=0,
            require_all_members_reachable=True,
        )
    # Fail-closed carries an explicit reason naming the unreachable member.
    assert "node:owner:cell2" in str(excinfo.value)


def test_execution_node_disappearance_never_fabricates_success(
    tmp_path: Path,
) -> None:
    # If the EXECUTION node itself vanishes, the cell must surface the carrier
    # failure rather than reporting a passed/fabricated result.
    carrier = DisappearingCarrier("node:owner:cell0")
    with pytest.raises(ConnectionError, match="vanished"):
        run_three_node_cell(
            _targets(str(tmp_path)),
            account_id=ACCOUNT,
            subject_id=SUBJECT,
            carrier=carrier,
            execution_node_index=0,
        )
