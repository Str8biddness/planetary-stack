#!/usr/bin/env python3
"""
Synthesus 5 - User Mode Simulation
Tests the full pipeline: User Input -> Multi-Shard Resonance -> Larynx Output.
"""

import sys
import os
import json
from pathlib import Path

# Ensure the tools directory is in the path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'tools')))

from geometric_refinery import GeometricEngineFallback

class SynthesusUserInterface:
    def __init__(self):
        print("🖥️  [SYSTEM] Booting Synthesus 5 Sovereign Interface...")
        self.engine = GeometricEngineFallback()
        self.shard_dir = Path("./data/geometric_shards")
        self.loaded_shards = {}
        self._load_all_shards()

    def _load_all_shards(self):
        print("📂 [KERNEL] Mounting Knowledge Cloud shards...")
        if not self.shard_dir.exists():
            print("❌ Error: No shards found. Run refinery first.")
            return

        for shard_file in self.shard_dir.glob("*.kn"):
            category = shard_file.stem
            with open(shard_file, 'r', encoding='utf-8') as f:
                self.loaded_shards[category] = json.load(f)
            print(f"   - Mounted: {category}.kn ({len(self.loaded_shards[category]['vectors'])} concepts)")

    def process_query(self, user_text):
        print(f"\n👤 [USER]: {user_text}")
        print("🧠 [BRAIN]: Calculating 5-Axis Resonance...")
        
        # 1. Project Query to Geometric Space
        query_vec = self.engine.word_to_vector(user_text)
        
        # 2. Search Shards for resonance
        best_resonance = -1.0
        best_word = "..."
        source_shard = "unknown"

        for cat, data in self.loaded_shards.items():
            for word, vec in data['vectors'].items():
                res = self._calculate_cosine(query_vec, vec)
                if res > best_resonance:
                    best_resonance = res
                    best_word = word
                    source_shard = cat

        # 3. Simulate Larynx Vocal Profile
        vocal_pitch = 220.0 + (query_vec[1] * 660.0)
        
        print(f"📊 [TRACE]: Highest Resonance: {best_word} ({best_resonance:.4f}) from [{source_shard}]")
        print(f"🔊 [LARYNX]: (Harmonic Breath @ {vocal_pitch:.2f}Hz) -> 'Resonance detected in {source_shard} shard. Concept alignment: {best_word}.'")
        
        return best_word

    def _calculate_cosine(self, v1, v2):
        dot = sum(a*b for a, b in zip(v1, v2))
        mag1 = sum(a*a for a in v1)**0.5
        mag2 = sum(a*a for a in v2)**0.5
        return dot / (mag1 * mag2) if (mag1 * mag2) > 0 else 0

if __name__ == "__main__":
    ui = SynthesusUserInterface()
    
    # User Test Case 1: Cross-Lingual Concept
    ui.process_query("inteligencia")
    
    # User Test Case 2: Technical Inquiry
    ui.process_query("quantum computing")
    
    # User Test Case 3: News Context
    ui.process_query("headlines")

    print("\n--- Phase 13: Resonance Observer Audit (Syntech Steering Simulation) ---")
    # Simulate an LLM audit of a drifted concept
    print("🎯 [SYNTECH]: Auditing concept 'truth'...")
    health = 0.95 # Simulated logic health
    print(f"📊 [OBSERVER]: Logic Health Check: {health*100:.1f}%")
    
    # Apply a corrective nudge (simulating LLM feedback that 'truth' should be more prominent)
    print("⚖️  [SYNTECH]: Nudging 'truth' Scale axis (Axis 5) +0.1 to increase resonance prominence.")
    # In full C++ build, this calls resonance_observer->apply_bias_nudge("truth", 4, 0.1)
    print("✅ [KERNEL]: Bias nudge applied. Geometric drift corrected.")

