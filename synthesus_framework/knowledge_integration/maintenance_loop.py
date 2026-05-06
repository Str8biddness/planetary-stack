import sys
import logging
from pathlib import Path
import subprocess

# Add repo root to path
repo_root = Path("/home/workspace/synthesus_repo")
sys.path.insert(0, str(repo_root))

from knowledge_integration.health_check import run_health_check
from knowledge_integration.manifest_manager import load_manifest, create_initial_manifest, save_manifest

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("maintenance_loop")

def check_source_drift(manifest):
    """Check if source data files have changed since last build."""
    data_dir = repo_root / "data"
    jeopardy_path = data_dir / "jeopardy" / "combined_season1-41.tsv"
    conceptnet_path = data_dir / "conceptnet" / "conceptnet-assertions-5.7.0.csv.gz"
    
    last_build = manifest.get("build_time", 0)
    
    for path in [jeopardy_path, conceptnet_path]:
        if path.exists() and path.stat().st_mtime > last_build:
            logger.info(f"Source file changed: {path}")
            return True
    return False

def rebuild_index():
    logger.info("Triggering full index rebuild...")
    
    # Clean up stale artifacts to ensure a fresh fit of the embedder and a clean index
    data_dir = repo_root / "data"
    stale_files = [
        data_dir / "faiss.index",
        data_dir / "knowledge.faiss",
        data_dir / "knowledge.kndb",
        data_dir / "knowledge.kndb.meta.db",
        data_dir / "embedder" / "swarm_embedder.pkl"
    ]
    for p in stale_files:
        if p.exists():
            logger.info(f"Removing stale artifact: {p}")
            p.unlink()

    # Run the population script with some defaults
    try:
        cmd = [sys.executable, "-m", "knowledge_integration.run_population", "--sample-jeopardy", "50000", "--max", "100000"]
        subprocess.run(cmd, check=True, cwd=str(repo_root))
        logger.info("Rebuild complete. Updating manifest.")
        m = create_initial_manifest()
        save_manifest(m)
        return True
    except Exception as e:
        logger.error(f"Rebuild FAILED: {e}")
        return False

def run_maintenance(force_rebuild=False):
    manifest = load_manifest()
    
    if force_rebuild:
        return rebuild_index()
    
    logger.info("Checking source drift...")
    if check_source_drift(manifest):
        logger.info("Source data changed. Rebuild required.")
        return rebuild_index()
    
    logger.info("Running health check...")
    healthy = run_health_check()
    
    if not healthy:
        logger.warning("Health check failed. Investigating...")
        # Load report to see errors
        report_path = repo_root / "data" / "health_report.json"
        if report_path.exists():
            import json
            with open(report_path, "r") as f:
                report = json.load(f)
            
            errors = report.get("errors", [])
            logger.info(f"Detected errors: {errors}")
            
            # Decide if we need a rebuild
            needs_rebuild = False
            for err in errors:
                if "mismatch" in err or "corrupt" in err.lower():
                    needs_rebuild = True
                    break
            
            if needs_rebuild:
                return rebuild_index()
            else:
                logger.info("Errors detected but not triggering auto-rebuild. Manual intervention required.")
                return False
    else:
        logger.info("System is healthy. No maintenance required.")
        return True

if __name__ == "__main__":
    force = "--force" in sys.argv
    success = run_maintenance(force_rebuild=force)
    sys.exit(0 if success else 1)
