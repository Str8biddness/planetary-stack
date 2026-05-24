#!/usr/bin/env python3
"""
Synthesus 2.0 — Hemisphere Performance & Integration Benchmark
AIVM LLC

Verifies:
1. Left Hemisphere token trigger lookup (< 1ms target).
2. Right Hemisphere cognitive state retrieval (Smart FS fallback).
3. Universal Substrate aggregation.
"""

import json
import logging
import time
import sys
from pathlib import Path

# Setup path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.universal_substrate import UniversalSubstrate
from cognitive.cognitive_engine import CognitiveEngine

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("benchmark")

async def main():
    substrate = UniversalSubstrate()
    log.info("=" * 60)
    log.info("Synthesus Universal Substrate Benchmark")
    log.info("=" * 60)

    # 1. Test Right Hemisphere (Character Data)
    start = time.time()
    bio = substrate.get_parameter("char_synthesus.bio", domain="right_hemisphere")
    latency = (time.time() - start) * 1000
    if bio:
        log.info(f"Right Hemisphere: Successfully fetched 'synthesus' bio in {latency:.2f}ms")
    else:
        log.error("Right Hemisphere: Failed to fetch character bio.")

    # 2. Test Left Hemisphere (Fast Pattern Lookup)
    # We'll mock a pattern key that was migrated
    start = time.time()
    pats = substrate.get_parameter("patterns.global", domain="left_hemisphere")
    latency = (time.time() - start) * 1000
    if pats:
        log.info(f"Left Hemisphere: Successfully fetched global patterns in {latency:.2f}ms")
    else:
        log.warning("Left Hemisphere: No global patterns found in substrate.")

    # 3. Test Full Brain Integration
    log.info("Initializing CognitiveEngine with Universal Substrate...")
    engine = CognitiveEngine(character_id="synthesus", substrate=substrate)
    
    log.info(f"Engine character: {engine.bio.get('name', 'Unknown')}")
    log.info(f"Engine archeype: {engine.bio.get('archetype', 'Unknown')}")
    
    # 4. Process Query
    query = "Who are you?"
    log.info(f"Processing query: '{query}'")
    start = time.time()
    result = await engine.process_query("player_1", query)
    latency = (time.time() - start) * 1000
    
    log.info("-" * 40)
    log.info(f"Response: {result.get('response')}")
    log.info(f"Source: {result.get('source')}")
    log.info(f"Latency: {latency:.2f}ms")
    log.info("-" * 40)

    log.info("Benchmark Complete!")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
