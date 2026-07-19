import os
import hashlib
from typing import Optional

from services.unisync.mesh_common import MeshSecurityError

class LocalCASWrapper:
    """
    Local Content-Addressable Storage (CAS) wrapper for Planetary Drive.
    Stores encrypted immutable objects keyed by their cryptographic hash.
    Enforces strict path-traversal prevention.
    """
    def __init__(self, root_dir: str):
        self.root_dir = os.path.abspath(root_dir)
        os.makedirs(self.root_dir, exist_ok=True)

    def _resolve_path(self, content_hash: str) -> str:
        """
        Resolves the hash to a local path and strictly ensures it does not
        escape the configured root_dir.
        Raises MeshSecurityError on traversal attempt.
        """
        target_path = os.path.abspath(os.path.join(self.root_dir, content_hash))
        
        # Security: Prevent path traversal
        try:
            common = os.path.commonpath([self.root_dir, target_path])
            if common != self.root_dir:
                raise MeshSecurityError(f"Path traversal detected: {content_hash}")
        except ValueError:
            # e.g. different drives on Windows
            raise MeshSecurityError(f"Path traversal detected: {content_hash}")
            
        # Optional additional check: don't allow modifying root_dir itself
        if target_path == self.root_dir:
            raise MeshSecurityError(f"Target path cannot be the root directory: {content_hash}")
            
        return target_path

    def put(self, data: bytes) -> str:
        """
        Hashes the provided data, writes it to the CAS if it doesn't exist,
        and returns the content hash (SHA-256).
        """
        content_hash = hashlib.sha256(data).hexdigest()
        target_path = self._resolve_path(content_hash)
        
        if not os.path.exists(target_path):
            tmp_path = target_path + ".tmp"
            with open(tmp_path, "wb") as f:
                f.write(data)
            os.rename(tmp_path, target_path)
            
        return content_hash

    def get(self, content_hash: str) -> Optional[bytes]:
        """
        Retrieves the immutable object by its hash.
        Returns None if not found.
        Raises MeshSecurityError if hash contains path traversal.
        """
        target_path = self._resolve_path(content_hash)
        if not os.path.exists(target_path):
            return None
            
        with open(target_path, "rb") as f:
            return f.read()
