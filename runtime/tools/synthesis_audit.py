#!/usr/bin/env python3
"""
Synthesis Audit Benchmark
Evaluates the quality of multi-entity knowledge synthesis in Synthesus 2.0.
"""

import asyncio
import json
import logging
import sys
import os
import time
from pathlib import Path
from typing import Dict, List, Any

# Add project root to path and set CWD
PROJ_ROOT = Path(__file__).parent.parent.resolve()
os.chdir(PROJ_ROOT)
sys.path.insert(0, str(PROJ_ROOT))

from cognitive.cognitive_engine import CognitiveEngine
from core.knowledge_cloud import KnowledgeCloud

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Test Queries (Multi-Entity & General)
CHALLENGES = [
    {
        "id": "dragon_mountain",
        "query": "Where do dragons live and are they dangerous?",
        "expected_entities": ["dragon", "mountain"],
    },
    {
        "id": "ironhaven_commerce",
        "query": "Tell me about the trade in Ironhaven and the Merchant's Alliance.",
        "expected_entities": ["ironhaven", "merchant"],
    },
    {
        "id": "blackhollow_wraith",
        "query": "What is the danger in Blackhollow?",
        "expected_entities": ["blackhollow", "wraith"],
    },
    {
        "id": "silvermoor_textiles",
        "query": "Who makes the enchanted silk in Silvermoor?",
        "expected_entities": ["silvermoor", "weaver"],
    },
    {
        "id": "healing_reagents",
        "query": "How do you make a healing potion?",
        "expected_entities": ["healing potion", "moonpetal"],
    }
]

class SynthesisAudit:
    def __init__(self):
        self.data_dir = PROJ_ROOT / "data"
        self.cloud = KnowledgeCloud(data_dir=str(self.data_dir / "knowledge_cloud"))
        
        # Mock Character: Garen
        self.bio = {
            "name": "Garen",
            "archetype": "knight",
            "role": "Defender of Ironhaven",
            "knowledge_domains": ["military", "lore"]
        }
        self.patterns = {
            "synthetic_patterns": [
                {"trigger": "danger", "response": "My blade is ready. No evil shall pass while I breathe."},
                {"trigger": "honor", "response": "Honor is the shield that protects our hearts."}
            ]
        }
        
        self.engine = CognitiveEngine(
            character_id="garen",
            bio=self.bio,
            patterns=self.patterns,
            knowledge_cloud=self.cloud
        )

    async def run_audit(self):
        logger.info("=" * 60)
        logger.info("Synthesus Synthesis Audit Benchmark")
        logger.info(f"Knowledge Cloud: {len(self.cloud._entries)} entries")
        logger.info("=" * 60)
        
        results = []
        total_score = 0
        
        for challenge in CHALLENGES:
            logger.info(f"\nChallenge: {challenge['id']}")
            logger.info(f"Query: {challenge['query']}")
            
            t0 = time.time()
            # CognitiveEngine.process_query returns an awaitable or dict
            res = self.engine.process_query(
                player_id="benchmark_player",
                query=challenge["query"],
                ml_context={"trust": 70.0, "intent": "lore_query"}
            )
            
            # Handle potential awaitable
            if hasattr(res, "__await__"):
                res = await res
                
            elapsed = (time.time() - t0) * 1000
            
            response = res.get("response", "")
            source = res.get("source", "unknown")
            
            # Scoring
            entities_found = []
            for ent in challenge["expected_entities"]:
                if ent.lower() in response.lower():
                    entities_found.append(ent)
            
            accuracy = len(entities_found) / len(challenge["expected_entities"])
            
            # Bonus for using Knowledge Cloud (SequenceLinker)
            source_bonus = 20 if source == "knowledge_cloud" else 0
            
            # Baseline accuracy score (80%) + Source bonus (20%)
            score = (accuracy * 80) + source_bonus
            
            total_score += score
            
            logger.info(f"Source: {source}")
            logger.info(f"Latency: {elapsed:.1f}ms")
            logger.info(f"Accuracy: {accuracy:.0%}")
            logger.info(f"Response: {response[:150]}...")
            
            results.append({
                "id": challenge["id"],
                "score": score,
                "latency_ms": elapsed,
                "source": source,
                "entities_found": entities_found
            })
            
        avg_score = total_score / len(CHALLENGES)
        logger.info("\n" + "=" * 60)
        logger.info(f"Audit Complete! Overall Score: {avg_score:.1f}")
        logger.info("=" * 60)
        
        return {
            "overall_score": avg_score,
            "challenges": results
        }

async def main():
    audit = SynthesisAudit()
    results = await audit.run_audit()
    
    # Save results
    timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    results_dir = PROJ_ROOT / "benchmarks" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    out_path = results_dir / f"synthesis_audit_{timestamp}.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"\nResults saved to {out_path}")

if __name__ == "__main__":
    asyncio.run(main())
