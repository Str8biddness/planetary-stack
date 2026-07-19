"""Audit log: redaction, owner-only permissions, round-trip, stable codes."""

from __future__ import annotations

import json
import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from services.observability.audit import (
    DENYLIST_KEY_SUBSTRINGS,
    AuditLogError,
    AuditReader,
    AuditRecord,
    AuditWriter,
    DetailTooLargeError,
    EventCategory,
    EventCode,
    SecretRedactionError,
    scrub_detail,
)


class _Clock:
    """Deterministic monotonic UTC clock for reproducible timestamps."""

    def __init__(self) -> None:
        self._t = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        self._t += timedelta(seconds=1)
        return self._t


def _writer(tmp_path: Path, **kwargs) -> AuditWriter:
    return AuditWriter(tmp_path / "obs", clock=_Clock().now, **kwargs)


# --------------------------------------------------------------------------
# Secret redaction / refusal
# --------------------------------------------------------------------------


def test_denylist_keys_are_redacted_by_default(tmp_path: Path) -> None:
    writer = _writer(tmp_path)
    secret_value = "super-secret-value-should-not-appear"
    record = writer.write(
        EventCode.AUTH_ACCEPTED,
        EventCategory.SECURITY,
        {
            "api_key": secret_value,
            "jwt_secret": secret_value,
            "authorization": f"Bearer {secret_value}",
            "password": secret_value,
            "access_token": secret_value,
            "bundle_base64": secret_value,
            "account_id": "account:001",
        },
    )
    # Redacted values in the returned record.
    for k in ("api_key", "jwt_secret", "authorization", "password",
              "access_token", "bundle_base64"):
        assert record.detail[k] == "[REDACTED]"
    assert record.detail["account_id"] == "account:001"

    # And nothing secret hit the raw bytes on disk.
    raw = writer.path.read_bytes()
    assert secret_value.encode() not in raw
    assert b"[REDACTED]" in raw


def test_nested_secret_keys_are_scrubbed(tmp_path: Path) -> None:
    writer = _writer(tmp_path)
    record = writer.write(
        EventCode.JOB_ACCEPTED,
        EventCategory.EXECUTION,
        {"context": {"lease": "lease:1", "signing_key": "PRIVATE-XYZ"}},
    )
    assert record.detail["context"]["lease"] == "lease:1"
    assert record.detail["context"]["signing_key"] == "[REDACTED]"
    assert b"PRIVATE-XYZ" not in writer.path.read_bytes()


def test_raw_prompt_and_user_content_never_written(tmp_path: Path) -> None:
    writer = _writer(tmp_path)
    prompt = "the user typed this private prompt text"
    record = writer.write(
        EventCode.JOB_ACCEPTED,
        EventCategory.EXECUTION,
        {"prompt": prompt, "user_content": prompt, "output_text": prompt},
    )
    for k in ("prompt", "user_content", "output_text"):
        assert record.detail[k] == "[REDACTED]"
    assert prompt.encode() not in writer.path.read_bytes()


def test_strict_mode_refuses_secret_fields(tmp_path: Path) -> None:
    writer = _writer(tmp_path, strict_secrets=True)
    with pytest.raises(SecretRedactionError):
        writer.write(
            EventCode.AUTH_REJECTED,
            EventCategory.SECURITY,
            {"password": "nope"},
        )
    # The refused write must not have appended anything.
    assert writer.path.read_bytes() == b""


def test_denylist_covers_required_substrings() -> None:
    for required in (
        "token",
        "secret",
        "key",
        "password",
        "authorization",
        "bundle_base64",
    ):
        assert required in DENYLIST_KEY_SUBSTRINGS


def test_scrub_bounds_reject_oversized_and_truncate(tmp_path: Path) -> None:
    # Too many keys is rejected.
    with pytest.raises(DetailTooLargeError):
        scrub_detail({f"k{i}": i for i in range(33)})
    # Deep nesting is rejected.
    deep: dict = {"a": {"b": {"c": {"d": {"e": 1}}}}}
    with pytest.raises(DetailTooLargeError):
        scrub_detail(deep)
    # Long strings are truncated, not rejected.
    scrubbed = scrub_detail({"note": "x" * 5000})
    assert scrubbed["note"].endswith("...[TRUNCATED]")
    assert len(scrubbed["note"]) <= 512


# --------------------------------------------------------------------------
# Owner-only permissions
# --------------------------------------------------------------------------


def test_directory_and_file_are_owner_only(tmp_path: Path) -> None:
    writer = _writer(tmp_path)
    writer.write(EventCode.LEASE_GRANTED, EventCategory.LIFECYCLE, {"lease": "l1"})

    dir_mode = stat.S_IMODE(os.lstat(writer.path.parent).st_mode)
    file_mode = stat.S_IMODE(os.lstat(writer.path).st_mode)
    assert dir_mode == 0o700, oct(dir_mode)
    assert file_mode == 0o600, oct(file_mode)
    # No group/other bits anywhere.
    assert file_mode & (stat.S_IRWXG | stat.S_IRWXO) == 0
    assert dir_mode & (stat.S_IRWXG | stat.S_IRWXO) == 0


def test_group_readable_directory_is_refused(tmp_path: Path) -> None:
    bad = tmp_path / "loose"
    bad.mkdir(mode=0o755)
    os.chmod(bad, 0o750)  # group-readable
    with pytest.raises(AuditLogError):
        AuditWriter(bad)


def test_symlinked_directory_is_refused(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(AuditLogError):
        AuditWriter(link)


# --------------------------------------------------------------------------
# Round-trip and format
# --------------------------------------------------------------------------


def test_records_round_trip(tmp_path: Path) -> None:
    writer = _writer(tmp_path)
    r1 = writer.write(EventCode.JOB_ACCEPTED, EventCategory.EXECUTION, {"job": "j1"})
    r2 = writer.write(EventCode.JOB_COMPLETED, EventCategory.EXECUTION,
                      {"job": "j1", "outputs": 2})

    parsed = AuditReader(writer.path).records()
    assert parsed == [r1, r2]
    assert parsed[0].code == "job.accepted"
    assert parsed[1].detail == {"job": "j1", "outputs": 2}


def test_each_record_is_one_canonical_line(tmp_path: Path) -> None:
    writer = _writer(tmp_path)
    for i in range(5):
        writer.write(EventCode.JOB_ACCEPTED, EventCategory.EXECUTION, {"n": i})
    lines = writer.path.read_text().splitlines()
    assert len(lines) == 5
    for line in lines:
        obj = json.loads(line)
        # Canonical (RFC 8785) ordering: keys are sorted.
        assert list(obj.keys()) == sorted(obj.keys())
        assert set(obj) == {"code", "category", "ts", "detail"}


def test_timestamp_is_utc_zulu(tmp_path: Path) -> None:
    writer = _writer(tmp_path)
    rec = writer.write(EventCode.JOB_ACCEPTED, EventCategory.EXECUTION, {})
    assert rec.ts.endswith("Z")
    # Parseable back to an aware UTC datetime.
    parsed = datetime.fromisoformat(rec.ts.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None


def test_append_only_preserves_prior_records(tmp_path: Path) -> None:
    writer = _writer(tmp_path)
    writer.write(EventCode.LEASE_GRANTED, EventCategory.LIFECYCLE, {"lease": "a"})
    # A fresh writer over the same directory must not clobber history.
    writer2 = AuditWriter(tmp_path / "obs", clock=_Clock().now)
    writer2.write(EventCode.LEASE_REVOKED, EventCategory.LIFECYCLE, {"lease": "a"})
    parsed = AuditReader(writer2.path).records()
    assert [r.code for r in parsed] == ["lease.granted", "lease.revoked"]


# --------------------------------------------------------------------------
# Stable codes
# --------------------------------------------------------------------------


def test_event_codes_are_stable_strings() -> None:
    # These exact string values are a format contract; pin them.
    expected = {
        "AUTH_ACCEPTED": "auth.accepted",
        "AUTH_REJECTED": "auth.rejected",
        "ADMISSION_REJECTED": "admission.rejected",
        "SECRET_REDACTED": "audit.secret_redacted",
        "JOB_ACCEPTED": "job.accepted",
        "JOB_COMPLETED": "job.completed",
        "JOB_FAILED": "job.failed",
        "JOB_CANCELLED": "job.cancelled",
        "LEASE_GRANTED": "lease.granted",
        "LEASE_REVOKED": "lease.revoked",
        "TRANSPORT_OBJECT_SENT": "transport.object_sent",
        "TRANSPORT_OBJECT_RECEIVED": "transport.object_received",
        "TRANSPORT_REPLAY_REJECTED": "transport.replay_rejected",
    }
    actual = {member.name: member.value for member in EventCode}
    assert actual == expected


def test_categories_are_stable_strings() -> None:
    assert {c.value for c in EventCategory} == {
        "security",
        "execution",
        "lifecycle",
        "transport",
        "control",
        "audit",
    }


def test_record_canonical_bytes_are_stable() -> None:
    rec = AuditRecord(
        code="job.accepted",
        category="execution",
        ts="2026-07-18T12:00:01.000Z",
        detail={"b": 2, "a": 1},
    )
    assert rec.to_canonical_json() == (
        b'{"category":"execution","code":"job.accepted",'
        b'"detail":{"a":1,"b":2},"ts":"2026-07-18T12:00:01.000Z"}'
    )
