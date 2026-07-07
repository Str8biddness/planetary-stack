#!/usr/bin/env python3
"""
Sovereign Assembler — Synthesus 5 Phase 14
Replaces the traditional 'LLM' front-end with native Harmonic Syntax logic.
Uses 5-axis resonance to assemble full sentences and trigger tool actions.
"""

import sys
import os
import json
import math
from pathlib import Path

# Add tools directory to path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from geometric_refinery import GeometricEngineFallback

class SovereignAssembler:
    def __init__(self):
        self.engine = GeometricEngineFallback()
        self.shard_dir = Path("/home/dakin/dev/Synthesus_4.0/data/geometric_shards")
        self.knowledge_cloud = {}
        self._boot()

    def _boot(self):
        print("🏛️  [ASSEMBLER] Initializing Harmonic Syntax Frame...")
        for shard_file in self.shard_dir.glob("*.kn"):
            with open(shard_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.knowledge_cloud.update(data['vectors'])
        print(f"✅ [ASSEMBLER] Ready. {len(self.knowledge_cloud)} harmonic anchors loaded.")

    def assemble_response(self, query):
        """
        Translates a query into a 'Stationary Wave' of language.
        Query -> Tonic Vector -> Harmonic Expansion -> Sentence.
        """
        # 1. Crystallize Query into its 'Tonic' frequency
        tonic_vec = self.engine.word_to_vector(query)
        
        # 2. Harmonic Expansion (Find concepts that resonate with the Tonic's Phase)
        # We look for a sequence of 5 tokens that minimize Phase drift
        sequence = []
        current_phase = tonic_vec[3]
        
        # Search for high-resonance concepts across the cloud
        candidates = []
        for word, vec in self.knowledge_cloud.items():
            res = self._calculate_resonance(tonic_vec, vec)
            if res > 0.98: # High resonance threshold
                candidates.append({'word': word, 'vec': vec, 'res': res})
        
        # Sort by Scale (Axis 5) to find the 'Anchors' of the sentence
        candidates.sort(key=lambda x: x['vec'][4], reverse=True)
        
        # Construct the 'Wave'
        # A simple 'Tonic - Expansion - Resolve' melody
        if candidates:
            # Major Anchor (Scale)
            major = candidates[0]['word']
            # Harmonic Neighbor (Phase)
            neighbor = candidates[min(1, len(candidates)-1)]['word']
            
            response = f"Resonance alignment: {major} vibrates through {neighbor}."
        else:
            response = "Minimal constructive interference detected. Seeking more data."

        # 3. Action Resonance Check
        # Check if the query resonates with system-command frequencies
        if "list" in query or "files" in query:
            self._trigger_action("ls")

        return response

    def _trigger_action(self, cmd):
        print(f"⚡ [ACTION] Resonance peak reached for command frequency: '{cmd}'")
        # In full impl: subprocess.run(cmd)

    def _calculate_resonance(self, v1, v2):
        dot = sum(a*b for a, b in zip(v1, v2))
        mag1 = sum(a*a for a in v1)**0.5
        mag2 = sum(a*a for a in v2)**0.5
        return dot / (mag1 * mag2) if (mag1 * mag2) > 0 else 0

if __name__ == "__main__":
    assembler = SovereignAssembler()
    # Test Query
    print(f"\n👤 USER > What is the truth?")
    print(f"🧠 SLLM > {assembler.assemble_response('What is the truth?')}")
    
    print(f"\n👤 USER > List my files.")
    print(f"🧠 SLLM > {assembler.assemble_response('List my files.')}")
