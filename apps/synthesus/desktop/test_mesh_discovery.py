"""Discovery of enrolled mesh nodes — and the guarantee that it grants nothing.

The registry files here are written by hand in the exact wire shape the mesh
itself produces (`planetary.unisync.mesh_enrollment_record.v1`, copied from
docs/evidence/F020_DESKTOP_INITIATED_PULL_PHYSICAL_2026-07-20.evidence.json),
so no test needs a real mesh. That also means these tests prove the PARSING and
the PERMISSION BOUNDARY, and prove nothing about a live mesh: no enrolled node
was contacted here.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import pytest

from mesh_discovery import (
    REASON_ALL_KNOWN,
    REASON_EMPTY,
    REASON_MISSING,
    REASON_UNREADABLE,
    discover_enrolled_nodes,
    registry_path_from_environment,
)

REGISTRY_SCHEMA = "planetary.unisync.mesh_enrollment_registry.v1"
RECORD_SCHEMA = "planetary.unisync.mesh_enrollment_record.v1"

WORKER = "node:private-mesh:dakin-ms-7c95"
DESKTOP = "node:private-mesh:dakin-chronos"


def _record(node_id, *, not_after="2026-07-27T18:41:12Z", status="active", **overrides):
    digest = hashlib.sha256(node_id.encode("utf-8")).hexdigest()
    record = {
        "schema": RECORD_SCHEMA,
        "account_id": "account:private-mesh:home",
        "node_id": node_id,
        "sans": ["worker.mesh"],
        "certificate_sha256": digest,
        "public_key_sha256": digest[::-1],
        "serial_hex": "18a6e72395e56464a52c5e795a5d1975b995bbbd",
        "issuer": "CN=Unisync Mesh CA 0fcbbe87a678631f",
        "not_before": "2026-07-20T18:36:12Z",
        "not_after": not_after,
        "status": status,
        "revocation_reason": None,
        "enrolled_at": "2026-07-20T18:41:12Z",
        "revoked_at": None,
    }
    record.update(overrides)
    return record


def _write(tmp_path, records, name="enrollments.json"):
    path = tmp_path / name
    path.write_text(
        json.dumps({"schema": REGISTRY_SCHEMA, "records": records}), encoding="utf-8"
    )
    path.chmod(0o600)
    return path


BEFORE_EXPIRY = datetime(2026, 7, 21, tzinfo=UTC)
AFTER_EXPIRY = datetime(2026, 8, 1, tzinfo=UTC)


def test_enrolled_nodes_are_offered_as_candidates(tmp_path):
    path = _write(tmp_path, [_record(WORKER), _record(DESKTOP, sans=["desktop.mesh"])])
    found = discover_enrolled_nodes(path, now=BEFORE_EXPIRY)
    assert found["reason"] is None
    assert [c["node_id"] for c in found["candidates"]] == [DESKTOP, WORKER]
    worker = found["candidates"][1]
    assert worker["suggested_display_name"] == "dakin-ms-7c95"
    assert worker["sans"] == ["worker.mesh"]
    assert worker["not_after"] == "2026-07-27T18:41:12Z"
    assert worker["certificate_sha256_short"] == worker["certificate_sha256"][:16]
    assert worker["available"] is True


def test_a_candidate_carries_no_capability_field_at_all(tmp_path):
    """Discovery is not a permission surface; it must not even speak of them."""
    path = _write(tmp_path, [_record(WORKER)])
    candidate = discover_enrolled_nodes(path, now=BEFORE_EXPIRY)["candidates"][0]
    assert "capabilities" not in candidate
    assert not any("capabilit" in key for key in candidate)


def test_devices_already_in_the_policy_are_not_offered_again(tmp_path):
    path = _write(tmp_path, [_record(WORKER), _record(DESKTOP)])
    found = discover_enrolled_nodes(path, known_device_ids=[WORKER], now=BEFORE_EXPIRY)
    assert [c["node_id"] for c in found["candidates"]] == [DESKTOP]

    both = discover_enrolled_nodes(
        path, known_device_ids=[WORKER, DESKTOP], now=BEFORE_EXPIRY
    )
    assert both["candidates"] == []
    assert both["reason"] == REASON_ALL_KNOWN


def test_an_expired_enrollment_is_flagged_and_not_available(tmp_path):
    path = _write(tmp_path, [_record(WORKER)])
    candidate = discover_enrolled_nodes(path, now=AFTER_EXPIRY)["candidates"][0]
    assert candidate["expired"] is True
    assert candidate["available"] is False
    # Still listed: silently dropping it would leave the owner guessing.
    assert candidate["not_after"] == "2026-07-27T18:41:12Z"


def test_a_revoked_enrollment_is_flagged_and_not_available(tmp_path):
    path = _write(
        tmp_path,
        [
            _record(
                WORKER,
                status="revoked",
                revocation_reason="key compromise",
                revoked_at="2026-07-21T10:00:00Z",
            )
        ],
    )
    candidate = discover_enrolled_nodes(path, now=BEFORE_EXPIRY)["candidates"][0]
    assert candidate["revoked"] is True
    assert candidate["available"] is False
    assert candidate["revocation_reason"] == "key compromise"


def test_a_missing_registry_yields_an_empty_list_with_a_reason(tmp_path):
    found = discover_enrolled_nodes(tmp_path / "nope.json", now=BEFORE_EXPIRY)
    assert found["candidates"] == []
    assert found["reason"] == REASON_MISSING
    assert found["detail"]


def test_an_empty_registry_says_so(tmp_path):
    found = discover_enrolled_nodes(_write(tmp_path, []), now=BEFORE_EXPIRY)
    assert found["candidates"] == []
    assert found["reason"] == REASON_EMPTY


@pytest.mark.parametrize(
    "content",
    [
        "not json at all",
        json.dumps({"schema": "some.other.schema.v1", "records": []}),
        json.dumps({"schema": REGISTRY_SCHEMA, "records": {"not": "a list"}}),
        # One structurally invalid record poisons the whole read: a registry we
        # only partly understand is a registry we do not understand.
        json.dumps(
            {
                "schema": REGISTRY_SCHEMA,
                "records": [_record(WORKER), {"node_id": "node:evil:made-up"}],
            }
        ),
    ],
)
def test_a_malformed_registry_never_produces_a_device(tmp_path, content):
    path = tmp_path / "enrollments.json"
    path.write_text(content, encoding="utf-8")
    found = discover_enrolled_nodes(path, now=BEFORE_EXPIRY)
    assert found["candidates"] == []
    assert found["reason"] == REASON_UNREADABLE
    assert found["detail"]


def test_a_directory_in_place_of_the_registry_is_refused(tmp_path):
    directory = tmp_path / "enrollments.json"
    directory.mkdir()
    found = discover_enrolled_nodes(directory, now=BEFORE_EXPIRY)
    assert found["candidates"] == []
    assert found["reason"] == REASON_UNREADABLE


def test_registry_path_is_configurable_by_environment(tmp_path):
    assert registry_path_from_environment({}).name == "enrollments.json"
    chosen = registry_path_from_environment(
        {"SYNTHESUS_MESH_REGISTRY": str(tmp_path / "elsewhere.json")}
    )
    assert chosen == tmp_path / "elsewhere.json"
