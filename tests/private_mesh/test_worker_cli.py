from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import stat
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from contracts.chal_vsource.v1.models import ErrorFrame
from services.private_mesh.ssh_smoke import (
    NodeTarget,
    SshCarrier,
    run_two_node_smoke,
)
from services.private_mesh.worker_cli import (
    IDENTITY_FILE,
    KEY_FILE,
    _strict_json,
    enroll_node,
    execute_job,
)


ACCOUNT = "account:owner:private-mesh"
SUBJECT = "node-agent:private-mesh"


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_enrollment_creates_stable_private_identity_with_strict_modes(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"

    first = enroll_node(
        state_dir=state,
        account_id=ACCOUNT,
        node_id="node:owner:stable",
        authenticated_subject_id=SUBJECT,
    )
    second = enroll_node(
        state_dir=state,
        account_id=ACCOUNT,
        node_id="node:owner:stable",
        authenticated_subject_id=SUBJECT,
    )

    assert _mode(state) == 0o700
    assert _mode(state / KEY_FILE) == 0o600
    assert _mode(state / IDENTITY_FILE) == 0o600
    assert first["public_key_base64"] == second["public_key_base64"]
    assert "private_key" not in json.dumps(first).lower()
    assert first["inventory"]["attestation"] == "unverified"
    assert first["inventory"]["transports"] == ["local_process"]
    assert first["inventory"]["resources"]["allocatable"]["ingress_bps"] == 0
    assert first["inventory"]["resources"]["allocatable"]["egress_bps"] == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("account_id", "bad/account"),
        ("node_id", "bad/node"),
        ("authenticated_subject_id", "bad/subject"),
    ],
)
def test_invalid_enrollment_identity_never_creates_a_key(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    values = {
        "account_id": ACCOUNT,
        "node_id": "node:owner:valid",
        "authenticated_subject_id": SUBJECT,
    }
    values[field] = value

    with pytest.raises(ValueError, match="canonical contract identifier"):
        enroll_node(state_dir=tmp_path / "state", **values)

    assert not (tmp_path / "state" / KEY_FILE).exists()
    assert not (tmp_path / "state" / IDENTITY_FILE).exists()


def test_unsupported_architecture_never_creates_a_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("services.private_mesh.worker_cli.platform.machine", lambda: "mips")

    with pytest.raises(ValueError, match="unsupported contract architecture"):
        enroll_node(
            state_dir=tmp_path / "state",
            account_id=ACCOUNT,
            node_id="node:owner:unsupported",
            authenticated_subject_id=SUBJECT,
        )

    assert not (tmp_path / "state" / KEY_FILE).exists()


def test_existing_identity_binding_cannot_be_changed(tmp_path: Path) -> None:
    state = tmp_path / "state"
    enroll_node(
        state_dir=state,
        account_id=ACCOUNT,
        node_id="node:owner:bound",
        authenticated_subject_id=SUBJECT,
    )

    with pytest.raises(ValueError, match="subject binding cannot be changed"):
        enroll_node(
            state_dir=state,
            account_id=ACCOUNT,
            node_id="node:owner:bound",
            authenticated_subject_id="node-agent:different",
        )
    with pytest.raises(ValueError, match="does not match"):
        enroll_node(
            state_dir=state,
            account_id="account:owner:different",
            node_id="node:owner:bound",
            authenticated_subject_id=SUBJECT,
        )


def test_execute_before_enrollment_fails_without_creating_identity(tmp_path: Path) -> None:
    state = tmp_path / "state"

    with pytest.raises(ValueError, match="has not been enrolled"):
        execute_job(
            state_dir=state,
            payload={
                "schema": "planetary.private_mesh.ssh_job.v1",
                "account_id": ACCOUNT,
                "node_id": "node:owner:missing",
                "audience": "node:owner:missing",
                "keys": [],
                "inventory": {},
                "request": {},
                "capability": {},
                "lease": {},
                "bundle_base64": "",
            },
        )

    assert not (state / KEY_FILE).exists()
    assert not (state / IDENTITY_FILE).exists()


def test_strict_json_rejects_duplicate_nan_and_non_utf8_wire_encodings() -> None:
    with pytest.raises(ValueError, match="duplicate JSON key"):
        _strict_json('{"a":1,"a":2}')
    with pytest.raises(ValueError, match="non-I-JSON"):
        _strict_json('{"a":NaN}')
    with pytest.raises(UnicodeDecodeError):
        _strict_json('{"a":1}'.encode("utf-16"))


class LocalCarrier:
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


def _targets(directory: str) -> list[NodeTarget]:
    return [
        NodeTarget(
            node_id=f"node:owner:local{i}",
            ssh_alias=f"local{i}",
            ssh_host_fingerprint=f"SHA256:{character * 43}",
            remote_python="/fixed/python",
            remote_repo="/fixed/repo",
            remote_state_dir=f"{directory}/state{i}",
        )
        for i, character in enumerate(("A", "B"))
    ]


def test_two_node_coordinator_ingests_fenced_signed_results(tmp_path: Path) -> None:
    state_db = tmp_path / "physical-smoke.sqlite3"
    evidence = run_two_node_smoke(
        _targets(str(tmp_path)),
        account_id=ACCOUNT,
        subject_id=SUBJECT,
        carrier=LocalCarrier(),
        state_db_path=state_db,
    )

    assert evidence["passed"] is True
    assert evidence["carrier"] == "ssh_stdio"
    assert evidence["contract_transport"] == "local_process"
    assert evidence["claims"]["unisync_mtls_proven"] is False
    assert evidence["claims"]["hardware_attestation_proven"] is False
    assert evidence["claims"]["persistent_sqlite_state"] is True
    assert evidence["claims"]["persistent_issuer_enrollment_proven"] is False
    assert evidence["sqlite_state"]["persistent"] is True
    assert _mode(state_db) == 0o600
    assert evidence["sqlite_state"]["sha256"] == hashlib.sha256(
        state_db.read_bytes()
    ).hexdigest()
    with sqlite3.connect(f"file:{state_db}?mode=ro", uri=True) as connection:
        assert connection.execute("SELECT count(*) FROM leases").fetchone() == (2,)
    assert evidence["sqlite_state"]["sha256"] == hashlib.sha256(
        state_db.read_bytes()
    ).hexdigest()
    assert evidence["trust_bundle"]["controller"]["public_key_base64"]
    assert len({node["hostname"] for node in evidence["nodes"]}) == 2
    assert len({node["node_key_fingerprint"] for node in evidence["nodes"]}) == 2
    assert all(len(node["worker_trust_records"]) == 3 for node in evidence["nodes"])
    assert all(node["report_size_bytes"] > 0 for node in evidence["nodes"])


def test_job_cannot_supply_its_own_authenticated_subject(tmp_path: Path) -> None:
    class SubjectInjectingCarrier(LocalCarrier):
        def execute(self, target: NodeTarget, job: dict[str, Any]) -> dict[str, Any]:
            job = dict(job)
            job["authenticated_subject_id"] = "node-agent:attacker"
            return super().execute(target, job)

    with pytest.raises(ValueError, match="job fields differ"):
        run_two_node_smoke(
            _targets(str(tmp_path)),
            account_id=ACCOUNT,
            subject_id=SUBJECT,
            carrier=SubjectInjectingCarrier(),
        )


def test_bundle_mismatch_returns_a_signed_error_frame(tmp_path: Path) -> None:
    captured: list[dict[str, Any]] = []

    class BundleTamperingCarrier(LocalCarrier):
        def execute(self, target: NodeTarget, job: dict[str, Any]) -> dict[str, Any]:
            job = dict(job)
            job["bundle_base64"] = "AA"
            result = super().execute(target, job)
            captured.append(result)
            return result

    with pytest.raises(RuntimeError, match="did not execute"):
        run_two_node_smoke(
            _targets(str(tmp_path)),
            account_id=ACCOUNT,
            subject_id=SUBJECT,
            carrier=BundleTamperingCarrier(),
        )

    assert captured
    execution = captured[0]["execution"]
    assert execution["status"] == "bundle_mismatch"
    assert execution["accepted"] is False
    error = ErrorFrame.model_validate_json(json.dumps(execution["error"]))
    assert error.code.value == "integrity_failure"


def test_target_parser_rejects_relative_or_traversal_paths() -> None:
    fingerprint = "SHA256:" + "A" * 43
    with pytest.raises(ValueError, match="safe absolute path"):
        NodeTarget.parse(
            f"node:owner:a|host|{fingerprint}|python|/repo|/state"
        )
    with pytest.raises(ValueError, match="safe absolute path"):
        NodeTarget.parse(
            f"node:owner:a|host|{fingerprint}|/python|/repo/../escape|/state"
        )


def test_ssh_carrier_requires_one_raw_ed25519_pin_and_disables_other_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private_key = Ed25519PrivateKey.generate()
    open_ssh = private_key.public_key().public_bytes(
        Encoding.OpenSSH, PublicFormat.OpenSSH
    ).decode("ascii")
    _key_type, encoded_key = open_ssh.split()
    fingerprint = "SHA256:" + base64.b64encode(
        hashlib.sha256(base64.b64decode(encoded_key)).digest()
    ).rstrip(b"=").decode("ascii")
    known_hosts = tmp_path / "known_hosts"
    line = f"worker-pin {open_ssh}\n"
    known_hosts.write_text(line, encoding="utf-8")
    carrier = SshCarrier(
        known_hosts=known_hosts,
        identity_file=None,
        timeout_seconds=10,
    )
    target = NodeTarget(
        "node:owner:pinned",
        "worker",
        fingerprint,
        "/python",
        "/repo",
        "/state",
    )
    monkeypatch.setattr(
        carrier,
        "_ssh_config",
        lambda _alias: ("192.0.2.1", 22, "worker-pin"),
    )

    assert carrier.verify_pinned_host(target)["ssh_host_fingerprint"] == fingerprint
    argv = carrier._base_argv(target.ssh_alias)
    assert "GlobalKnownHostsFile=/dev/null" in argv
    assert "VerifyHostKeyDNS=no" in argv
    assert "UpdateHostKeys=no" in argv
    assert "HostKeyAlgorithms=ssh-ed25519" in argv
    assert "KnownHostsCommand=none" in argv
    assert "ControlMaster=no" in argv
    assert "ControlPath=none" in argv
    assert "NoHostAuthenticationForLocalhost=no" in argv
    assert "ForwardX11=no" in argv
    assert "Tunnel=no" in argv
    assert "PermitLocalCommand=no" in argv

    known_hosts.write_text(line + line, encoding="utf-8")
    with pytest.raises(RuntimeError, match="exactly the expected host key"):
        carrier.verify_pinned_host(target)
