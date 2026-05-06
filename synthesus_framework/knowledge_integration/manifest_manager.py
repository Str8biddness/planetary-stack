import json
import hashlib
import time
from pathlib import Path
from typing import Dict, Any

MANIFEST_PATH = Path("/home/workspace/synthesus_repo/data/manifest.json")

def get_file_hash(path: Path) -> str:
    if not path.exists():
        return ""
    sha256_hash = hashlib.sha256()
    with open(path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def create_initial_manifest() -> Dict[str, Any]:
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
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)

def load_manifest() -> Dict[str, Any]:
    if not MANIFEST_PATH.exists():
        return {}
    with open(MANIFEST_PATH, "r") as f:
        return json.load(f)

if __name__ == "__main__":
    m = create_initial_manifest()
    save_manifest(m)
    print(f"Manifest created at {MANIFEST_PATH}")
