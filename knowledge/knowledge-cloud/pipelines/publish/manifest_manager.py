import json
import hashlib
import time
from pathlib import Path
from typing import Dict, Any

"""Manifest management for knowledge integration artifacts.

This module provides utilities to create, save, and load manifest files that
track the integrity and metadata of knowledge base artifacts such as FAISS
indices and KNDB files.
"""

MANIFEST_PATH = Path("/home/workspace/synthesus_repo/data/manifest.json")

def get_file_hash(path: Path) -> str:
    """Computes the SHA-256 hash of a file.

    Args:
        path: Path to the file.

    Returns:
        The hex-encoded SHA-256 hash of the file, or an empty string if the
        file does not exist.
    """
    if not path.exists():
        return ""
    sha256_hash = hashlib.sha256()
    with open(path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def create_initial_manifest() -> Dict[str, Any]:
    """Generates a new manifest dictionary based on current local artifacts.

    Scans the data directory for FAISS indices and database files, computes
    their hashes, and extracts metadata like vector counts if possible.

    Returns:
        A dictionary representing the system manifest.
    """
    data_dir = Path("/home/workspace/synthesus_repo/data")
    
    # Identify key artifacts (using defaults or common names)
    faiss_path = data_dir / "faiss.index"
    if not faiss_path.exists():
        faiss_path = data_dir / "knowledge.faiss"
        
    kn_path = data_dir / "knowledge.kndb"
    meta_path = data_dir / "knowledge.kndb.meta.db"
    
    manifest = {
        "index_hash": get_file_hash(faiss_path),
        "metadata_hash": get_file_hash(meta_path),
        "kn_db_hash": get_file_hash(kn_path),
        "source_dataset_version": "Jeopardy_v1",
        "embedder_version": "SwarmEmbedder_v1",
        "schema_version": "1.0",
        "vector_count": 0, # To be filled by health check
        "build_time": time.time(),
        "checksums": {
            "faiss.index": get_file_hash(faiss_path),
            "knowledge.kndb": get_file_hash(kn_path),
            "knowledge.kndb.meta.db": get_file_hash(meta_path)
        }
    }
    
    # Try to get vector count if faiss is available
    try:
        import faiss
        if faiss_path.exists():
            index = faiss.read_index(str(faiss_path))
            manifest["vector_count"] = index.ntotal
    except ImportError:
        pass
        
    return manifest

def save_manifest(manifest: Dict[str, Any]):
    """Saves a manifest dictionary to the standard manifest JSON file.

    Args:
        manifest: The manifest dictionary to save.
    """
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)

def load_manifest() -> Dict[str, Any]:
    """Loads the manifest dictionary from the standard manifest JSON file.

    Returns:
        The loaded manifest dictionary, or an empty dictionary if the file
        does not exist.
    """
    if not MANIFEST_PATH.exists():
        return {}
    with open(MANIFEST_PATH, "r") as f:
        return json.load(f)

if __name__ == "__main__":
    m = create_initial_manifest()
    save_manifest(m)
    print(f"Manifest created at {MANIFEST_PATH}")
