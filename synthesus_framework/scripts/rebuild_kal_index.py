import os
import json
import faiss
import numpy as np
from pathlib import Path
import sys

# Setup path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ml.swarm_embedder import SwarmEmbedder

def rebuild():
    meta_path = ROOT / "data" / "faiss_metadata.json"
    index_path = ROOT / "data" / "faiss.index"
    model_dir = ROOT / "data" / "models"
    
    print(f"Loading metadata from {meta_path}...")
    with open(meta_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)
    
    # Use 'response' for full content embedding
    texts = [m.get("response") or m.get("pattern", "") for m in metadata]
    print(f"Loaded {len(texts)} texts. Refitting SwarmEmbedder...")
    
    embedder = SwarmEmbedder(dim=128)
    embedder.fit(texts)
    
    print("Generating new embeddings...")
    embeddings = embedder.embed_texts(texts)
    
    print("Building FAISS index...")
    index = faiss.IndexFlatIP(128)
    index.add(embeddings.astype(np.float32))
    
    print(f"Saving index to {index_path}...")
    faiss.write_index(index, str(index_path))
    
    print(f"Saving model to {model_dir}...")
    embedder.model_dir = model_dir
    embedder._save()
    
    print("SUCCESS: Index and Embedder rebuilt with full vocabulary.")

if __name__ == "__main__":
    rebuild()
