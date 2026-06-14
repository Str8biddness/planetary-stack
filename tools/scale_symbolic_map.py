#!/usr/bin/env python3
"""
scale_symbolic_map.py
Scales the 5-axis Symbolic Mapping to the full Knowledge Cloud datasets.
"""

import sys
import os
from pathlib import Path
import csv
import gzip
import logging
import json
from collections import Counter

# Add packages to path
sys.path.append(str(Path(__file__).resolve().parents[1] / "packages"))
from knowledge.geometric_embedder import GeometricEmbedder

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

def count_frequencies(jeopardy_path, conceptnet_path, limit=1000000):
    """Counts word frequencies from datasets for Axis 5 (Scale) calculation."""
    counts = Counter()
    
    # 1. Process Jeopardy
    logger.info(f"Processing Jeopardy frequencies from {jeopardy_path}...")
    try:
        with open(jeopardy_path, newline="", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            for i, row in enumerate(reader):
                text = (row.get("question", "") + " " + row.get("answer", "")).lower()
                counts.update(text.split())
                if i >= limit: break
    except Exception as e:
        logger.error(f"Error reading Jeopardy: {e}")

    # 2. Process ConceptNet (Healthy prefix)
    logger.info(f"Processing ConceptNet frequencies from {conceptnet_path}...")
    try:
        with gzip.open(conceptnet_path, 'rt', encoding='utf-8', errors='replace') as fh:
            for i, line in enumerate(fh):
                # ConceptNet format: /a/[/r/Antonym/,/c/ab/агыруа/n/,/c/ab/аҧсуа/] ...
                # We just want to extract words
                words = line.replace('/', ' ').replace('[', ' ').replace(']', ' ').replace(',', ' ').lower().split()
                counts.update(words)
                if i >= limit: break
    except EOFError:
        logger.warning("Reached end of healthy ConceptNet prefix.")
    except Exception as e:
        logger.error(f"Error reading ConceptNet: {e}")
        
    return dict(counts)

def main():
    root_dir = Path(__file__).resolve().parents[1]
    jeopardy_path = root_dir / "data/jeopardy/combined_season1-41.tsv"
    conceptnet_path = root_dir / "data/conceptnet/conceptnet-assertions-5.7.0.csv.gz"
    output_path = root_dir / "data/knowledge/symbolic_map_5axis.json"
    
    os.makedirs(output_path.parent, exist_ok=True)

    # 1. Gather Frequencies
    freq_map = count_frequencies(jeopardy_path, conceptnet_path, limit=250000)
    logger.info(f"Unique words found: {len(freq_map)}")

    # 2. Initialize Embedder
    embedder = GeometricEmbedder(frequency_map=freq_map)

    # 3. Generate Map for Top Words
    # We'll save the top 50k most frequent words to keep the file size small
    logger.info("Generating 5-axis map for top 50,000 words...")
    sorted_words = sorted(freq_map.items(), key=lambda x: x[1], reverse=True)[:50000]
    
    symbolic_map = {}
    for word, freq in sorted_words:
        vec = embedder.word_to_vector(word)
        symbolic_map[word] = vec.tolist()

    # 4. Save Map
    logger.info(f"Saving symbolic map to {output_path}...")
    with open(output_path, "w") as f:
        json.dump({
            "version": "5-axis-chal-v1",
            "dim": 5,
            "axes": ["X", "Y", "Z", "Phase", "Scale"],
            "map": symbolic_map
        }, f)
    
    logger.info("Scaling complete! 5-axis Symbolic Map is ready.")

if __name__ == "__main__":
    main()
