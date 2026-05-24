#!/usr/bin/env python3
"""
Parameter Cloud v2 — Out-of-Core SQLite Batch Ingestion
AIVM Synthesus 2.0

Reads massive knowledge bases/corpora line-by-line and ingests their N-Gram 
transitions into the out-of-core SQLite PatternLM db.
"""

import os
import sys
import argparse
import time
from pathlib import Path

# Setup path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ml.pattern_lm import PatternLM


def process_file_in_chunks(filepath: Path, lm: PatternLM, chunk_size: int = 1000):
    """Read a large file line by line and batch fit the PatternLM."""
    print(f"Reading {filepath}...", flush=True)
    batch = []
    lines_processed = 0
    t0 = time.time()
    
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            # Basic cleanup: remove markdown hashes if present, ignore pure code blocks
            if line.startswith("```"):
                continue
            line = line.lstrip("#*-> \t")
            
            if len(line.split()) < 2:
                continue
                
            batch.append(line)
            lines_processed += 1
            
            if len(batch) >= chunk_size:
                lm.fit(batch)
                batch = []
                if lines_processed % 10000 == 0:
                    print(f"  Processed {lines_processed} lines... ({time.time() - t0:.1f}s)", flush=True)

    # flush remainder
    if batch:
        lm.fit(batch)
        
    print(f"Finished {filepath}. Total lines: {lines_processed} in {time.time() - t0:.1f}s", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Ingest massive datasets into the out-of-core SQLite PatternLM.")
    parser.add_argument("path", type=str, nargs="?", default="data", help="Directory or file to ingest")
    parser.add_argument("--db-path", type=str, default="D:/synthesus_data/data/pattern_lm.db", help="Path to SQLite DB")
    parser.add_argument("--order", type=int, default=3, help="Max N-Gram order")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    args = parser.parse_args()

    input_path = Path(args.path)
    if not input_path.exists():
        print(f"Error: Path not found {input_path}")
        return

    # Use a chunk size that balances memory with SQLite transaction speed
    chunk_size = 5000

    lm = PatternLM(order=args.order, db_path=args.db_path)
    print(f"Initialized PatternLM(order={args.order}) connected to {args.db_path}")

    files = []
    if input_path.is_file():
        files.append(input_path)
    else:
        # We target the massive _v1 grounding txts specifically, or fallback to all txts
        massive_files = list(input_path.glob("*_v1.txt"))
        if massive_files:
            files.extend(massive_files)
        else:
            files.extend(list(input_path.glob("**/*.txt")))
            files.extend(list(input_path.glob("**/*.csv")))
            files.extend(list(input_path.glob("**/*.json")))

    if not files:
        print("No .txt files found to ingest.")
        return

    print(f"Found {len(files)} files to ingest into the Parameter Cloud.")
    
    if args.dry_run:
        print("DRY RUN: would process:")
        for f in files:
            print(f"  - {f}")
        return

    t_start = time.time()
    for fpath in files:
        process_file_in_chunks(fpath, lm, chunk_size=chunk_size)
        
    print(f"SUCCESS: Parameter Cloud ingestion complete. Total time: {time.time() - t_start:.2f}s")
    
if __name__ == "__main__":
    main()
