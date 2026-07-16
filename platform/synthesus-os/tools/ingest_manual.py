#!/usr/bin/env python3
"""
Synthesus KAL — Manual Knowledge Ingestor
Allows ingesting local text/markdown files into the FAISS index.
"""
import os
import json
import argparse
import logging
from pathlib import Path
import faiss
import numpy as np
import sys

# Setup path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ml.swarm_embedder import SwarmEmbedder

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("ingest_manual")

def chunk_text(text, max_len=400):
    words = text.split()
    chunks = []
    current_chunk = []
    current_len = 0
    for w in words:
        if current_len + len(w) > max_len and current_chunk:
            chunks.append(" ".join(current_chunk))
            current_chunk = [w]
            current_len = len(w)
        else:
            current_chunk.append(w)
            current_len += len(w) + 1
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    return chunks

def main():
    parser = argparse.ArgumentParser(description="Ingest local files into KAL FAISS index")
    parser.add_argument("path", type=str, help="Directory or file to ingest")
    parser.add_argument("--namespace", type=str, default="manual_ingest", help="Target namespace")
    parser.add_argument("--domain", type=str, default="technical", help="Target domain")
    parser.add_argument("--char-id", type=str, default="global", help="Character ID or 'global'")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    args = parser.parse_args()

    input_path = Path(args.path)
    if not input_path.exists():
        log.error(f"Path not found: {input_path}")
        return

    files = []
    if input_path.is_file():
        files.append(input_path)
    else:
        for ext in ["*.txt", "*.md", "*.json"]:
            files.extend(list(input_path.glob(f"**/{ext}")))

    log.info(f"Found {len(files)} files for ingestion")

    entries = []
    for fpath in files:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Simple metadata from filename
            source_name = fpath.name
            
            # Chunk the content
            chunks = chunk_text(content)
            for i, chunk in enumerate(chunks):
                entries.append({
                    "pattern": f"{source_name} (segment {i+1}): {chunk[:100]}...",
                    "response": chunk,
                    "source": f"manual/{source_name}",
                    "namespace": args.namespace,
                    "domain": args.domain,
                    "character_id": args.char_id,
                    "file_path": str(fpath.relative_to(ROOT)) if ROOT in fpath.parents else str(fpath)
                })
        except Exception as e:
            log.error(f"Failed to read {fpath}: {e}")

    if not entries:
        log.warning("No entries extracted")
        return

    log.info(f"Extracted {len(entries)} chunks")

    if args.dry_run:
        log.info("DRY RUN -- sample entry:")
        log.info(json.dumps(entries[0], indent=2))
        return

    # Loading index and embedder
    index_path = ROOT / "data" / "faiss.index"
    meta_path = ROOT / "data" / "faiss_metadata.json"
    
    log.info("Loading SwarmEmbedder...")
    embedder = SwarmEmbedder(dim=128)
    
    # Load the existing model to ensure dimension consistency
    model_dir = ROOT / "data" / "models"
    if (model_dir / "swarm_embedder.pkl").exists():
        log.info(f"Loading fitted model from {model_dir}")
        embedder.model_dir = model_dir
        embedder._load()
    else:
        log.warning("No fitted model found! Fitting on new entries (this may cause dimension mismatch).")
        texts = [e["pattern"] for e in entries]
        embedder.fit(texts)
    
    texts = [e["pattern"] for e in entries]
    embeddings = embedder.embed_texts(texts)
    
    log.info(f"Loading existing index from {index_path}...")
    index = faiss.read_index(str(index_path))
    
    if index.d != embeddings.shape[1]:
        log.error(f"Dimension mismatch: Index={index.d}, New={embeddings.shape[1]}")
        return

    index.add(embeddings.astype(np.float32))
    
    with open(meta_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)
    
    metadata.extend(entries)
    
    # Save
    faiss.write_index(index, str(index_path))
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f)
    
    log.info(f"SUCCESS: Ingested {len(entries)} chunks. New index size: {index.ntotal}")

if __name__ == "__main__":
    main()
