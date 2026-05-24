import json
import time
import sys
import logging
from pathlib import Path
import numpy as np

# Add repo root to path
repo_root = Path("/home/workspace/synthesus_repo")
sys.path.insert(0, str(repo_root))

from knowledge_integration.manifest_manager import load_manifest, get_file_hash
from knowledge_integration.kn_populator import KNPopulator, MetadataDB
from ml.swarm_embedder import SwarmEmbedder

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("health_check")

GOLDEN_QUERIES = [
    "What is the capital of France?",
    "Who wrote the theory of relativity?",
    "What is the largest planet in our solar system?",
    "Who is the main character in the Great Gatsby?",
    "What is the chemical symbol for gold?"
]

LATENCY_THRESHOLD_MS = 100.0

def run_health_check():
    manifest = load_manifest()
    if not manifest:
        logger.error("No manifest found. Health check failed.")
        return False
    
    data_dir = repo_root / "data"
    faiss_path = data_dir / "faiss.index"
    if not faiss_path.exists():
        faiss_path = data_dir / "knowledge.faiss"
    kn_path = data_dir / "knowledge.kndb"
    meta_path = data_dir / "knowledge.kndb.meta.db"
    
    errors = []
    
    # 1. Check file integrity
    if get_file_hash(faiss_path) != manifest.get("index_hash"):
        errors.append("FAISS index hash mismatch")
    if get_file_hash(kn_path) != manifest.get("kn_db_hash"):
        errors.append("KNDB hash mismatch")
    
    # 2. Verify counts
    embedder = SwarmEmbedder(model_dir=data_dir / "embedder")
    pop = KNPopulator(kn_path=kn_path, faiss_path=faiss_path, embedder=embedder)
    
    # Trigger lazy load of FAISS index to get accurate stats
    pop._load_existing_faiss()
    
    stats = pop.stats()
    faiss_size = stats["faiss_size"]
    meta_count = stats["total"]
    
    if faiss_size != meta_count:
        errors.append(f"Count mismatch: FAISS={faiss_size}, Metadata={meta_count}")
    
    if faiss_size != manifest.get("vector_count"):
        logger.warning(f"Vector count changed since manifest: {manifest.get('vector_count')} -> {faiss_size}")

    # 3. Benchmark latency and stability
    latencies = []
    for query in GOLDEN_QUERIES:
        try:
            t0 = time.time()
            results = pop.search_faiss(query, top_k=5)
            t1 = time.time()
            latencies.append((t1 - t0) * 1000)
            
            if not results:
                errors.append(f"Empty results for golden query: {query}")
        except Exception as e:
            errors.append(f"Search failed for query '{query}': {e}")
            logger.error(f"Search error: {e}")
            break

    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    logger.info(f"Average latency: {avg_latency:.2f}ms")
    
    if avg_latency > LATENCY_THRESHOLD_MS:
        errors.append(f"Latency exceeded threshold: {avg_latency:.2f}ms > {LATENCY_THRESHOLD_MS}ms")

    # 4. Report
    report = {
        "timestamp": time.time(),
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "stats": stats,
        "avg_latency_ms": avg_latency
    }
    
    report_path = repo_root / "data" / "health_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    
    if errors:
        logger.error(f"Health check FAILED: {errors}")
        return False
    else:
        logger.info("Health check PASSED")
        return True

if __name__ == "__main__":
    success = run_health_check()
    sys.exit(0 if success else 1)
