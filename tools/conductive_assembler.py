#!/usr/bin/env python3
"""
Conductive Assembler — Synthesus 5 Phase 14.1
Optimizes language generation using Musical Theory (Chords/Rhythm/Intervals).
Treats a sentence as a musical score derived from 5-axis coordinates.
"""

import sys
import os
import json
import math
from pathlib import Path

# Add tools directory to path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from geometric_refinery import GeometricEngineFallback

class ConductiveAssembler:
    def __init__(self):
        self.engine = GeometricEngineFallback()
        self.shard_dir = Path("/home/dakin/dev/Synthesus_4.0/data/geometric_shards")
        self.knowledge_cloud = {}
        self._boot()

    def _boot(self):
        print("🎵 [CONDUCTOR] Tuning the Linguistic Orchestra...")
        for shard_file in self.shard_dir.glob("*.kn"):
            with open(shard_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.knowledge_cloud.update(data['vectors'])
        print(f"✅ [CONDUCTOR] Ready. {len(self.knowledge_cloud)} notes (concepts) in the score.")

    def compose_sentence(self, query):
        """
        Composes a sentence by following musical harmony rules.
        """
        # 1. Establish the 'Key' (Phase) from the Query
        tonic_vec = self.engine.word_to_vector(query)
        key_phase = tonic_vec[3]
        
        # 2. Find the 'Tonic' (First Word)
        # We find concepts with the highest resonance to the query
        potential_notes = []
        for word, vec in self.knowledge_cloud.items():
            res = self._calculate_resonance(tonic_vec, vec)
            if res > 0.95:
                potential_notes.append({'word': word, 'vec': vec, 'res': res})
        
        if not potential_notes:
            return "Dissonance detected. Seeking alignment."

        # Sort by Scale (Axis 5) to find the primary anchor
        potential_notes.sort(key=lambda x: x['vec'][4], reverse=True)
        
        # 3. Assemble the 'Melodic Line'
        # Rule: Next word must be a 'Harmonic Interval' away in Y-Axis (Pitch)
        sentence = [potential_notes[0]]
        
        # Composition Loop (Targeting 5-7 words for a 'Bar' of music)
        for _ in range(5):
            current_note = sentence[-1]
            next_note = self._find_consonant_neighbor(current_note, key_phase)
            if next_note:
                sentence.append(next_note)
            else:
                break

        # 4. Final 'Resolve' (The Cadence)
        # Convert to text and capitalize
        raw_words = [n['word'] for n in sentence]
        score = " ".join(raw_words).capitalize() + "."
        
        # Calculate overall 'Musical Coherence'
        coherence = sum(n['res'] for n in sentence) / len(sentence)
        
        print(f"🎼 [SCORE] Coherence: {coherence*100:.1f}% | Key: {key_phase*360:.1f}°")
        return score

    def _find_consonant_neighbor(self, current, key_phase):
        """
        Finds a word whose Pitch (Axis 2) is a 'Consonant Interval' 
        from the current word while staying in Key (Phase).
        """
        best_match = None
        min_dissonance = float('inf')
        
        # Sample a subset for speed in this prototype
        sample_size = 0
        for word, vec in self.knowledge_cloud.items():
            # Filter by Phase (Key alignment)
            phase_diff = abs(vec[3] - key_phase)
            if phase_diff > 0.1: continue # Out of Key
            
            # Check Pitch Interval (Y-Axis)
            # We look for 'Perfect Fifths' (0.33 offset) or 'Octaves' (0.5 offset)
            pitch_diff = abs(vec[1] - current['vec'][1])
            
            # Musical Consonance Check
            is_consonant = False
            for interval in [0.0, 0.33, 0.5, 0.66]: # Harmonic ratios
                if abs(pitch_diff - interval) < 0.05:
                    is_consonant = True
                    break
            
            if is_consonant and word not in [n['word'] for n in [current]]:
                # Track best by resonance and scale
                dissonance = phase_diff + (1.0 - vec[4])
                if dissonance < min_dissonance:
                    min_dissonance = dissonance
                    best_match = {'word': word, 'vec': vec, 'res': 1.0 - dissonance}
            
            sample_size += 1
            if sample_size > 2000: break # Optimization

        return best_match

    def _calculate_resonance(self, v1, v2):
        dot = sum(a*b for a, b in zip(v1, v2))
        mag1 = sum(a*a for a in v1)**0.5
        mag2 = sum(a*a for a in v2)**0.5
        return dot / (mag1 * mag2) if (mag1 * mag2) > 0 else 0

if __name__ == "__main__":
    assembler = ConductiveAssembler()
    # Test queries across different 'Keys'
    queries = ["Scientific truth", "The logic of existence", "Quantum computers"]
    
    for q in queries:
        print(f"\n👤 USER > {q}")
        print(f"🧠 SLLM > {assembler.compose_sentence(q)}")
