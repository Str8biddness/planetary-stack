"""Versioned, encrypted per-account namespace for Planetary Drive.

Stores encrypted immutable objects in a node-local content-addressed store and
tracks a versioned manifest per logical path in an owner-only SQLite database.
Supports atomic replacement, tombstone deletion, full version history, and
restore of an earlier version. Manifest signing, replica placement, quotas,
repair, and the multi-node read-only projection (SSI-RO-001) are separate
F-060 concerns and are not implemented here.
"""

from __future__ import annotations

import os
import sqlite3
import stat
import uuid
from datetime import datetime, timezone
from pathlib import Path

from services.planetary_drive.encrypted_store import EncryptedObjectStore
from services.planetary_drive.manifests import FileManifest


def _owner_only_file(path: Path) -> None:
    os.chmod(path, 0o600)
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
        raise PermissionError("namespace database is not owner-only")


class NamespaceManager:
    """Versioned encrypted namespace over a node-local CAS root."""

    def __init__(self, root_dir: str | Path, db_path: str | Path, *, key: bytes) -> None:
        self.store = EncryptedObjectStore(root_dir, key=key)
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.db_path.parent, 0o700)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    def _init_db(self) -> None:
        created = not self.db_path.exists()
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS manifests (
                    path TEXT PRIMARY KEY,
                    file_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    manifest_data TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS versions (
                    path TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    manifest_data TEXT NOT NULL,
                    PRIMARY KEY (path, version)
                )
                """
            )
            conn.commit()
        if created:
            _owner_only_file(self.db_path)
        else:
            os.chmod(self.db_path, 0o600)

    def _get_manifest(self, path: str) -> FileManifest | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT manifest_data FROM manifests WHERE path = ?", (path,)
            ).fetchone()
        return FileManifest.deserialize(row[0]) if row else None

    def _save(self, manifest: FileManifest) -> None:
        payload = manifest.serialize()
        with self._connect() as conn:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "INSERT OR REPLACE INTO manifests (path, file_id, version, manifest_data)"
                    " VALUES (?, ?, ?, ?)",
                    (manifest.path, manifest.file_id, manifest.version, payload),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO versions (path, version, manifest_data)"
                    " VALUES (?, ?, ?)",
                    (manifest.path, manifest.version, payload),
                )

    def put_file(self, path: str, data: bytes, node_id: str) -> FileManifest:
        """Encrypt+store data and record a new version of the file atomically."""

        ref = self.store.put(data)
        existing = self._get_manifest(path)
        now = datetime.now(timezone.utc)
        if existing is not None:
            existing.content_hash = ref.plaintext_sha256
            existing.storage_hash = ref.storage_sha256
            existing.size_bytes = ref.plaintext_size
            existing.version += 1
            existing.last_modified = now
            existing.is_deleted = False
            existing.vector_clock[node_id] = existing.vector_clock.get(node_id, 0) + 1
            manifest = existing
        else:
            manifest = FileManifest(
                file_id=str(uuid.uuid4()),
                path=path,
                content_hash=ref.plaintext_sha256,
                storage_hash=ref.storage_sha256,
                size_bytes=ref.plaintext_size,
                version=1,
                vector_clock={node_id: 1},
                is_deleted=False,
            )
        self._save(manifest)
        return manifest

    def get_file(self, path: str) -> tuple[FileManifest, bytes] | None:
        """Return (manifest, decrypted content), or None if absent/tombstoned."""

        manifest = self._get_manifest(path)
        if manifest is None or manifest.is_deleted:
            return None
        data = self.store.get(
            manifest.storage_hash, expected_plaintext_sha256=manifest.content_hash
        )
        if data is None:
            return None
        return manifest, data

    def delete_file(self, path: str, node_id: str) -> FileManifest | None:
        """Tombstone the file (new version); return the manifest or None."""

        manifest = self._get_manifest(path)
        if manifest is None or manifest.is_deleted:
            return None
        manifest.is_deleted = True
        manifest.version += 1
        manifest.last_modified = datetime.now(timezone.utc)
        manifest.vector_clock[node_id] = manifest.vector_clock.get(node_id, 0) + 1
        self._save(manifest)
        return manifest

    def get_manifest(self, path: str) -> FileManifest | None:
        return self._get_manifest(path)

    def list_versions(self, path: str) -> list[int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT version FROM versions WHERE path = ? ORDER BY version", (path,)
            ).fetchall()
        return [r[0] for r in rows]

    def get_version_manifest(self, path: str, version: int) -> FileManifest | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT manifest_data FROM versions WHERE path = ? AND version = ?",
                (path, version),
            ).fetchone()
        return FileManifest.deserialize(row[0]) if row else None

    def restore(self, path: str, version: int, node_id: str) -> FileManifest | None:
        """Restore an earlier version's content as a new head version."""

        old = self.get_version_manifest(path, version)
        current = self._get_manifest(path)
        if old is None or current is None or old.is_deleted:
            return None
        current.content_hash = old.content_hash
        current.storage_hash = old.storage_hash
        current.size_bytes = old.size_bytes
        current.is_deleted = False
        current.version += 1
        current.last_modified = datetime.now(timezone.utc)
        current.vector_clock[node_id] = current.vector_clock.get(node_id, 0) + 1
        self._save(current)
        return current
