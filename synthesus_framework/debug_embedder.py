import sys
from pathlib import Path
import logging

repo_root = Path("/home/workspace/synthesus_repo")
sys.path.insert(0, str(repo_root))

from ml.swarm_embedder import SwarmEmbedder

logging.basicConfig(level=logging.DEBUG)
data_dir = repo_root / "data"
embedder_dir = data_dir / "embedder"
print(f"Checking embedder at: {embedder_dir}")
print(f"File exists: {(embedder_dir / 'swarm_embedder.pkl').exists()}")

embedder = SwarmEmbedder(model_dir=embedder_dir)
print(f"Is fitted: {embedder.is_fitted}")
if embedder.is_fitted:
    print(f"Dim: {embedder.dim}")
else:
    print("FAILED TO LOAD")
