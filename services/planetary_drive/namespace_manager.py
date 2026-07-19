import os
import uuid
import sqlite3
from typing import Optional, Tuple
from datetime import datetime, timezone

from services.planetary_drive.manifests import FileManifest
from services.planetary_drive.local_cas import LocalCASWrapper

class NamespaceManager:
    """
    Manages the versioned file namespace for Planetary Drive.
    Integrates LocalCASWrapper for object storage and an SQLite database for manifest tracking.
    """
    def __init__(self, cas_wrapper: LocalCASWrapper, db_path: str):
        self.cas = cas_wrapper
        self.db_path = os.path.abspath(db_path)
        self._init_db()

    def _init_db(self):
        # Create directory for db if it doesn't exist
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS manifests (
                    path TEXT PRIMARY KEY,
                    file_id TEXT NOT NULL,
                    manifest_data TEXT NOT NULL
                )
            ''')
            conn.commit()

    def _get_manifest(self, path: str) -> Optional[FileManifest]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT manifest_data FROM manifests WHERE path = ?", (path,))
            row = cursor.fetchone()
            if row:
                return FileManifest.deserialize(row[0])
        return None

    def _save_manifest(self, manifest: FileManifest):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO manifests (path, file_id, manifest_data) VALUES (?, ?, ?)",
                (manifest.path, manifest.file_id, manifest.serialize())
            )
            conn.commit()

    def put_file(self, path: str, data: bytes, node_id: str) -> FileManifest:
        """
        Creates a new version of a file atomically. 
        Hashes the data into CAS and generates/updates the manifest.
        """
        content_hash = self.cas.put(data)
        size_bytes = len(data)
        
        manifest = self._get_manifest(path)
        if manifest:
            # Update existing manifest
            manifest.content_hash = content_hash
            manifest.size_bytes = size_bytes
            manifest.version += 1
            manifest.last_modified = datetime.now(timezone.utc)
            manifest.is_deleted = False
            # Update vector clock
            manifest.vector_clock[node_id] = manifest.vector_clock.get(node_id, 0) + 1
        else:
            # Create new manifest
            file_id = str(uuid.uuid4())
            manifest = FileManifest(
                file_id=file_id,
                path=path,
                content_hash=content_hash,
                size_bytes=size_bytes,
                version=1,
                vector_clock={node_id: 1},
                is_deleted=False
            )
            
        self._save_manifest(manifest)
        return manifest

    def get_file(self, path: str) -> Optional[Tuple[FileManifest, bytes]]:
        """
        Retrieves the file manifest and its corresponding data from CAS.
        Returns None if the file doesn't exist or is a tombstone.
        """
        manifest = self._get_manifest(path)
        if not manifest or manifest.is_deleted:
            return None
            
        data = self.cas.get(manifest.content_hash)
        if data is None:
            # Object missing from CAS
            return None
            
        return manifest, data

    def delete_file(self, path: str, node_id: str) -> Optional[FileManifest]:
        """
        Applies a tombstone deletion manifest to the file.
        Returns the updated manifest, or None if the file didn't exist.
        """
        manifest = self._get_manifest(path)
        if not manifest or manifest.is_deleted:
            return None # Already deleted or doesn't exist
            
        manifest.is_deleted = True
        manifest.version += 1
        manifest.last_modified = datetime.now(timezone.utc)
        manifest.vector_clock[node_id] = manifest.vector_clock.get(node_id, 0) + 1
        
        self._save_manifest(manifest)
        return manifest

    def get_manifest(self, path: str) -> Optional[FileManifest]:
        """Exposes manifest retrieval directly."""
        return self._get_manifest(path)
