#!/usr/bin/env python3
"""
Persona Sculptor — Synthesus 5 Phase 16.2
Uses harvested conversational DNA (interviews, Q&A) to refine modular agents.
Generates 'Cadence Shards' to tune the harmonic intervals for each persona.
"""

import os
import sys
import json
import time
from pathlib import Path

# Add tools directory to path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from geometric_refinery import GeometricRefinery

class PersonaSculptor:
    def __init__(self):
        self.refinery = GeometricRefinery()
        self.shard_dir = Path("/home/dakin/dev/Synthesus_4.0/data/geometric_shards")
        self.dna_file = "conversational_dna.json"
        print("🎭 Persona Sculptor active: Sculpting authentic cadences...")

    def sculpt_agents(self):
        if not os.path.exists(self.dna_file):
            print("❌ No conversational DNA found. Run harvester first.")
            return

        with open(self.dna_file, 'r') as f:
            dna_data = json.load(f)

        for name, raw_text in dna_data.items():
            if not raw_text:
                print(f"⚠️ Skipping {name}: empty DNA.")
                continue

            print(f"  💎 Sculpting {name.capitalize()} Cadence Shard...")
            
            # Refine the conversational text into a priority shard
            shard_path = self.shard_dir / f"cadence_{name.lower()}.kn"
            
            # We use a lower character limit for the cadence to ensure high-density 'turn-taking' logic
            processed_text = f"CONVERSATIONAL_DNA_START\n{raw_text[:20000]}\nCONVERSATIONAL_DNA_END"
            
            self.refinery.refine_text_to_partition(processed_text, shard_path)
            print(f"✅ Cadence Shard [{name}] crystallized. Ready for bolting.")

if __name__ == "__main__":
    sculptor = PersonaSculptor()
    sculptor.sculpt_agents()
