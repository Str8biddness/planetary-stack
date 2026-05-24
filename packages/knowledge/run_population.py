#!/usr/bin/env python3
"""
run_population.py — Main entry point for knowledge index population.

Usage:
    python -m knowledge_integration.run_population
    python -m knowledge_integration.run_population --max 10000
    python -m knowledge_integration.run_population --sample-jeopardy 1000 --sample-conceptnet 1000
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from knowledge_integration.kaggle_loader import load_all_datasets
from knowledge_integration.kn_populator import KNPopulator
from ml.swarm_embedder import SwarmEmbedder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def test_index(populator: KNPopulator, queries: list[str]) -> None:
    """Test semantic search on the populated index."""
    logger.info("=" * 60)
    logger.info("Testing semantic search on populated index...")
    for q in queries:
        results = populator.search_faiss(q, top_k=3)
        logger.info(f"\nQuery: {q}")
        if not results:
            logger.info("  → No results")
        for meta, score in results:
            logger.info(
                f"  → [{score:.3f}] {meta['category']} | Q: {meta['question'][:60]}... | A: {meta['answer'][:40]}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Populate Synthesus knowledge index")
    parser.add_argument("--cache-dir",  default="./data")
    parser.add_argument("--kn-db",      default="./data/knowledge.kndb")
    parser.add_argument("--faiss",      default="./data/knowledge.faiss")
    parser.add_argument("--model-dir",  default="./data/embedder")
    parser.add_argument("--max",        type=int, default=None, help="Max total entries")
    parser.add_argument("--sample-jeopardy",  type=int, default=None, help="Jeopardy sample size")
    parser.add_argument("--sample-conceptnet", type=int, default=None, help="ConceptNet sample size")
    parser.add_argument("--batch-size", type=int, default=2000)
    parser.add_argument("--skip-test",  action="store_true", help="Skip semantic search test")
    parser.add_argument("--dim",       type=int, default=128, help="Embedding dimension")
    args = parser.parse_args()

    # Ensure dirs
    Path(args.cache_dir).mkdir(parents=True, exist_ok=True)
    Path(args.kn_db).parent.mkdir(parents=True, exist_ok=True)
    Path(args.faiss).parent.mkdir(parents=True, exist_ok=True)
    Path(args.model_dir).parent.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("Synthesus Knowledge Index Population")
    logger.info("=" * 60)

    # Init embedder
    embedder = SwarmEmbedder(model_dir=args.model_dir, dim=args.dim)

    # Init populator
    pop = KNPopulator(
        kn_path=args.kn_db,
        faiss_path=args.faiss,
        embedder=embedder,
        batch_size=args.batch_size,
    )

    # Load entries
    entries = load_all_datasets(
        cache_dir=args.cache_dir,
        sample_jeopardy=args.sample_jeopardy,
        sample_conceptnet=args.sample_conceptnet,
        seed=42,
    )

    # Populate
    t0 = time.time()
    result = pop.populate(entries, max_entries=args.max)
    elapsed = time.time() - t0

    logger.info("=" * 60)
    logger.info("Population complete!")
    logger.info(f"  Total entries:   {result['total_inserted']:,}")
    logger.info(f"  KNDB nodes:      {result['kn_size']:,}")
    logger.info(f"  FAISS vectors:  {result['faiss_size']:,}")
    logger.info(f"  Duration:        {result['duration_s']:.1f}s")
    logger.info(f"  Rate:            {result['entries_per_s']:.0f} entries/sec")
    logger.info("=" * 60)

    # Test queries
    if not args.skip_test:
        test_queries = [
            "science and technology",
            "historical events",
            "geography and places",
            "arts and literature",
            "sports and games",
        ]
        test_index(pop, test_queries)

    # Save result
    result_path = Path(args.cache_dir) / "population_result.json"
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2)
    logger.info(f"Result saved to {result_path}")

    # Size comparison context
    logger.info("\n=== Size Comparison ===")
    logger.info(f"  Synthesus KN index: {result['faiss_size']:,} vectors")
    logger.info(f"  GPT-4 knowledge cutoff: ~Sept 2023 (no specific count)")
    logger.info(f"  Note: GPT-4 has ~1 trillion parameters vs our lightweight index")
    logger.info("  Quality over quantity — curated high-fidelity entries")


if __name__ == "__main__":
    main()