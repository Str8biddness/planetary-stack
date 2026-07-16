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
        self.grounding = {}
        for shard_file in self.shard_dir.glob("*.kn"):
            with open(shard_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.knowledge_cloud.update(data.get('vectors', {}))  # skip non-vector shards
        # Grounding map wins over hash vectors: it carries deliberate meaning.
        gfile = self.shard_dir / "grounding.kn"
        if gfile.exists():
            with open(gfile, 'r', encoding='utf-8') as f:
                self.grounding = json.load(f)['vectors']
            self.knowledge_cloud.update(self.grounding)  # override hash for grounded words

        # Derived grounding: coordinates learned from corpus statistics
        # (tools/cooccurrence_grounding.py). This is the PRIMARY meaning source —
        # real distributional semantics, not hash, not a hand table.
        self.derived = {}
        dfile = self.shard_dir / "grounding_derived.kn"
        if dfile.exists():
            with open(dfile, 'r', encoding='utf-8') as f:
                self.derived = json.load(f)['vectors']
        # Distributional POS tags: drop verb-like tokens from realized families.
        self.verbs = set()
        pfile = self.shard_dir / "pos_lexicon.kn"
        if pfile.exists():
            self.verbs = set(json.load(open(pfile)).get("verbs", []))
        # PPBRS reasoning layer: a Bayesian belief over the derived patterns,
        # giving calibrated uncertainty (it can answer "I'm not sure").
        self.activator = None
        self.realizer = None
        if self.derived:
            try:
                import importlib.util
                pa = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "packages", "reasoning", "ppbrs_activator.py")
                spec = importlib.util.spec_from_file_location("ppbrs_activator", pa)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                self.activator = mod.ProbabilisticPatternActivator(mod.PatternField(self.derived))
                rp = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "packages", "reasoning", "realizer.py")
                rspec = importlib.util.spec_from_file_location("realizer", rp)
                rmod = importlib.util.module_from_spec(rspec)
                rspec.loader.exec_module(rmod)
                self.realizer = rmod.Realizer()
            except Exception as e:
                print(f"⚠️ [PPBRS] reasoning layer unavailable: {e}")
        print(f"✅ [CONDUCTOR] Ready. {len(self.knowledge_cloud)} notes "
              f"({len(self.grounding)} hand-grounded, {len(self.derived)} derived"
              f"{', PPBRS active' if self.activator else ''}).")

    def _compose_ppbrs(self, query):
        """Primary path: Bayesian reasoning over derived patterns.

        Accumulates each grounded query word as evidence, then answers from the
        posterior — and crucially, HEDGES when the belief stays uncertain (high
        entropy) instead of returning a confident-looking list for nonsense.
        Returns None if the query names no grounded concept.
        """
        if not self.activator:
            return None
        self.activator.reset()
        observed = 0
        for w in self._query_words(query):
            if self.activator.observe(w) is not None:
                observed += 1
        if observed == 0:
            return None
        H = self.activator.entropy()
        fam = [w for w, _ in self.activator.top_k(8)]
        nouns = [w for w in fam if w not in self.verbs]   # POS filter: keep nouns
        if len(nouns) >= 2:
            fam = nouns
        resolved = self.activator.is_resolved()
        print(f"🧮 [PPBRS] {'resolved' if resolved else 'uncertain'} | entropy {H:.2f}")
        if self.realizer:                          # GRE-style surface realization
            return self.realizer.realize(fam[0], fam[1:5], resolved)
        # fallback if the realizer didn't load
        body = fam[0] + ": " + " ".join(fam[1:])
        return body.capitalize() + "." if resolved else \
            ("I'm not certain, but this seems related to " + body + ".").capitalize()

    def _resolve_tonic(self, query):
        """Tonic = the grounded concept in the query if present, else hash fallback.

        This is what makes selection topical: 'tell me about water' keys off the
        grounded coordinates of 'water', not the hash of the whole sentence.
        """
        for w in query.lower().split():
            w = w.strip(".,;:!?\"'()[]{}")
            if w in self.grounding:
                return self.grounding[w], True
        return self.engine.word_to_vector(query), False

    @staticmethod
    def _query_words(query):
        return [w.strip(".,;:!?\"'()[]{}") for w in query.lower().split()]

    def _compose_derived(self, query):
        """Primary path: select the topical family from corpus-derived coordinates.

        Returns the queried concept plus its most resonant neighbours in the
        learned distributional space (real semantics, no hash). None if the
        query names no derived concept.
        """
        keys = [w for w in self._query_words(query) if w in self.derived]
        if not keys:
            return None
        dim = len(next(iter(self.derived.values())))
        tonic = [sum(self.derived[k][d] for k in keys) / len(keys) for d in range(dim)]
        scored = []
        for w, v in self.derived.items():
            if w in keys:
                continue
            scored.append((self._calculate_resonance(tonic, v), w))
        scored.sort(reverse=True)
        family = [w for _, w in scored[:6]]
        coherence = sum(s for s, _ in scored[:6]) / 6 if scored else 0.0
        print(f"🎼 [DERIVED] {len(self.derived)} concepts | family resonance "
              f"{coherence*100:.0f}%")
        return (keys[0] + ": " + " ".join(family)).capitalize() + "."

    def compose_sentence(self, query):
        """
        Composes a sentence by following musical harmony rules.
        """
        # 0. Primary path: PPBRS Bayesian reasoning (with calibrated uncertainty),
        #    falling back to plain derived-coordinate selection.
        ppbrs = self._compose_ppbrs(query)
        if ppbrs is not None:
            return ppbrs
        derived = self._compose_derived(query)
        if derived is not None:
            return derived

        # 1. Establish the 'Key' (Phase) from the Query's grounded concept
        tonic_vec, grounded = self._resolve_tonic(query)
        key_phase = tonic_vec[3]

        # Grounding is authoritative: if the query names a grounded concept,
        # compose from that concept's cluster (same phase) instead of the hash
        # soup, where ~1% of 22k words cross the resonance gate by accident.
        if grounded:
            pool = {w: v for w, v in self.grounding.items()
                    if abs(v[3] - key_phase) < 1e-3}
        else:
            pool = self.knowledge_cloud

        # 2. Find the 'Tonic' (First Word)
        # We find concepts with the highest resonance to the query
        potential_notes = []
        for word, vec in pool.items():
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
            used = {n['word'] for n in sentence}
            next_note = self._find_consonant_neighbor(current_note, key_phase, used, pool)
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

    def _find_consonant_neighbor(self, current, key_phase, used=None, pool=None):
        """
        Finds a word whose Pitch (Axis 2) is a 'Consonant Interval'
        from the current word while staying in Key (Phase).
        """
        if pool is None:
            pool = self.knowledge_cloud
        best_match = None
        min_dissonance = float('inf')

        # Sample a subset for speed in this prototype
        sample_size = 0
        for word, vec in pool.items():
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
            
            if is_consonant and word != current['word'] and (used is None or word not in used):
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
