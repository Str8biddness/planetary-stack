"""Durable node-side execution authority for admitted AIVM workloads.

This replaces test-only authority verifiers in production wiring.  The node
agent registers the exact signed lease revision it verified (issuer: the
vSource control plane, whose signature chain the agent has already checked),
and the executor atomically consumes that revision here immediately before
container start.  The store is an owner-only SQLite file, so consumption
survives process restarts and is race-safe across executor processes.

One lease scope (account, node, lease) executes at most once: after a
revision is consumed, no further revision of that lease may be registered
or consumed on this node.
"""

from __future__ import annotations

import os
import re
import sqlite3
import stat
from datetime import UTC, datetime
from pathlib import Path

from .podman import (
    AdmittedExecutionRequest,
    AuthorityStatus,
    AuthorityVerification,
)

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_MAX_SAFE_INTEGER = 9_007_199_254_740_991
_WIRE_TIME = "%Y-%m-%dT%H:%M:%SZ"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS authority_bindings (
    account_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    lease_id TEXT NOT NULL,
    fencing_token INTEGER NOT NULL,
    lease_sha256 TEXT NOT NULL,
    manifest_sha256 TEXT NOT NULL,
    workload_id TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    registered_at TEXT NOT NULL,
    consumed INTEGER NOT NULL DEFAULT 0,
    consumed_at TEXT,
    PRIMARY KEY (account_id, node_id, lease_id, fencing_token)
)
"""


class AuthorityRegistrationError(ValueError):
    """Fail-closed registration rejection with a stable public code."""


def _require_identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise AuthorityRegistrationError(f"invalid_{name}")
    return value


def _require_sha256(name: str, value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise AuthorityRegistrationError(f"invalid_{name}")
    return value


def _require_utc(name: str, value: object) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise AuthorityRegistrationError(f"invalid_{name}")
    return value.astimezone(UTC).replace(microsecond=0)


def _wire_time(value: datetime) -> str:
    return value.strftime(_WIRE_TIME)


def _private_state_dir(path: Path) -> Path:
    path = path.expanduser()
    if not path.is_absolute():
        raise AuthorityRegistrationError("authority_directory_must_be_absolute")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise AuthorityRegistrationError("authority_directory_not_real")
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise AuthorityRegistrationError("authority_directory_not_owner_only")
    return path.resolve(strict=True)


class PersistentExecutionAuthority:
    """SQLite-backed issuer-binding store implementing ExecutionAuthorityVerifier."""

    def __init__(self, state_dir: Path, *, verifier_id: str) -> None:
        self._verifier_id = _require_identifier("verifier_id", verifier_id)
        directory = _private_state_dir(state_dir)
        self._db_path = directory / "execution_authority.sqlite3"
        connection = self._connect()
        try:
            with connection:
                connection.execute(_SCHEMA)
        finally:
            connection.close()
        os.chmod(self._db_path, 0o600)

    @property
    def verifier_id(self) -> str:
        return self._verifier_id

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path, timeout=5.0)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def register(
        self,
        *,
        account_id: str,
        node_id: str,
        lease_id: str,
        lease_sha256: str,
        fencing_token: int,
        manifest_sha256: str,
        workload_id: str,
        expires_at: datetime,
        now: datetime,
    ) -> None:
        """Register one verified signed lease revision for later consumption.

        The caller must already have verified the vSource signature chain on
        the lease and the workload manifest; this store only pins the exact
        binding so execution can consume it once.
        """

        _require_identifier("account_id", account_id)
        _require_identifier("node_id", node_id)
        _require_identifier("lease_id", lease_id)
        _require_identifier("workload_id", workload_id)
        _require_sha256("lease_sha256", lease_sha256)
        _require_sha256("manifest_sha256", manifest_sha256)
        if (
            isinstance(fencing_token, bool)
            or not isinstance(fencing_token, int)
            or not 1 <= fencing_token <= _MAX_SAFE_INTEGER
        ):
            raise AuthorityRegistrationError("invalid_fencing_token")
        expires = _require_utc("expires_at", expires_at)
        current = _require_utc("now", now)
        if expires <= current:
            raise AuthorityRegistrationError("binding_already_expired")
        row = (
            account_id,
            node_id,
            lease_id,
            fencing_token,
            lease_sha256,
            manifest_sha256,
            workload_id,
            _wire_time(expires),
            _wire_time(current),
        )
        connection = self._connect()
        try:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    "SELECT fencing_token, lease_sha256, manifest_sha256, workload_id,"
                    " expires_at, consumed FROM authority_bindings"
                    " WHERE account_id = ? AND node_id = ? AND lease_id = ?",
                    (account_id, node_id, lease_id),
                )
                existing = cursor.fetchall()
                for (
                    known_token,
                    known_lease_sha256,
                    known_manifest_sha256,
                    known_workload_id,
                    known_expires_at,
                    known_consumed,
                ) in existing:
                    if known_consumed:
                        raise AuthorityRegistrationError("lease_scope_already_consumed")
                    if known_token > fencing_token:
                        raise AuthorityRegistrationError("stale_fencing_token")
                    if known_token == fencing_token:
                        identical = (
                            known_lease_sha256 == lease_sha256
                            and known_manifest_sha256 == manifest_sha256
                            and known_workload_id == workload_id
                            and known_expires_at == _wire_time(expires)
                        )
                        if not identical:
                            raise AuthorityRegistrationError("conflicting_lease_revision")
                        return
                connection.execute(
                    "INSERT INTO authority_bindings (account_id, node_id, lease_id,"
                    " fencing_token, lease_sha256, manifest_sha256, workload_id,"
                    " expires_at, registered_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    row,
                )
        finally:
            connection.close()

    def verify_and_consume(
        self,
        request: AdmittedExecutionRequest,
        *,
        expected_account_id: str,
        expected_node_id: str,
        now: datetime,
    ) -> AuthorityVerification:
        if type(request) is not AdmittedExecutionRequest:
            return AuthorityVerification(AuthorityStatus.REJECTED, self._verifier_id)
        try:
            current = _require_utc("now", now)
        except AuthorityRegistrationError:
            return AuthorityVerification(AuthorityStatus.UNAVAILABLE, self._verifier_id)
        lease = request.lease
        if (
            lease.account_id != expected_account_id
            or lease.node_id != expected_node_id
            or request.manifest.account_id != expected_account_id
        ):
            return AuthorityVerification(AuthorityStatus.REJECTED, self._verifier_id)
        try:
            connection = self._connect()
        except sqlite3.Error:
            return AuthorityVerification(AuthorityStatus.UNAVAILABLE, self._verifier_id)
        try:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    "SELECT MAX(fencing_token) FROM authority_bindings"
                    " WHERE account_id = ? AND node_id = ? AND lease_id = ?",
                    (lease.account_id, lease.node_id, lease.lease_id),
                )
                newest = cursor.fetchone()[0]
                if newest is None or newest != lease.fencing_token:
                    return AuthorityVerification(
                        AuthorityStatus.REJECTED, self._verifier_id
                    )
                consumed = connection.execute(
                    "UPDATE authority_bindings SET consumed = 1, consumed_at = ?"
                    " WHERE account_id = ? AND node_id = ? AND lease_id = ?"
                    " AND fencing_token = ? AND lease_sha256 = ?"
                    " AND manifest_sha256 = ? AND workload_id = ?"
                    " AND consumed = 0 AND expires_at > ?",
                    (
                        _wire_time(current),
                        lease.account_id,
                        lease.node_id,
                        lease.lease_id,
                        lease.fencing_token,
                        lease.lease_sha256,
                        request.manifest_sha256,
                        request.manifest.workload_id,
                        _wire_time(current),
                    ),
                )
                if consumed.rowcount != 1:
                    return AuthorityVerification(
                        AuthorityStatus.REJECTED, self._verifier_id
                    )
        except sqlite3.Error:
            return AuthorityVerification(AuthorityStatus.UNAVAILABLE, self._verifier_id)
        finally:
            connection.close()
        return AuthorityVerification(
            AuthorityStatus.VERIFIED,
            self._verifier_id,
            manifest_sha256=request.manifest_sha256,
            account_id=lease.account_id,
            workload_id=request.manifest.workload_id,
            node_id=lease.node_id,
            lease_id=lease.lease_id,
            lease_sha256=lease.lease_sha256,
            fencing_token=lease.fencing_token,
            consumed=True,
        )
