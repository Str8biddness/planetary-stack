#!/usr/bin/env python3
"""
GeometricInterferenceEngine — SLLM Core
Uses the 5-axis symbolic map to predict next tokens via geometric resonance.
"""

import json
import numpy as np
from pathlib import Path
from typing import List, Tuple, Optional

class GeometricInterferenceEngine:
    def __init__(self, map_path: str):
        self.root_dir = Path(__file__).resolve().parents[2]
        with open(map_path, "r") as f:
            data = json.load(f)
            self.symbolic_map = {k: np.array(v, dtype=np.float32) for k, v in data["map"].items()}
            self.dim = data["dim"]

    def predict_next_token(self, context: str, top_n: int = 5) -> List[Tuple[str, float]]:
        """
        Calculates the constructive interference point of the context words
        and returns the top-N words that resonate with that point.
        """
        words = context.lower().split()
        if not words:
            return []

        # 1. Convert context words to vectors
        context_vecs = []
        for w in words:
            if w in self.symbolic_map:
                context_vecs.append(self.symbolic_map[w])
        
        if not context_vecs:
            return []

        # 2. Calculate Interference Point (Weighted Center)
        # We use recency bias + Scale (Axis 5)
        combined_vec = np.zeros(self.dim, dtype=np.float32)
        total_weight = 0
        
        for i, vec in enumerate(context_vecs):
            # Recency bias (last word is most important)
            recency = (i + 1) / len(context_vecs)
            # Scale bias (inherent importance of the word)
            scale = vec[4]
            
            weight = recency * scale
            combined_vec += vec * weight
            total_weight += weight
            
        interference_point = combined_vec / total_weight

        # 3. Find Resonating Tokens
        # We use cosine similarity as the resonance metric
        results = []
        for word, vec in self.symbolic_map.items():
            if word in words: continue # Skip existing words to avoid loops
            
            # Resonance = Cosine Similarity
            dot = np.dot(interference_point, vec)
            norm = np.linalg.norm(interference_point) * np.linalg.norm(vec)
            resonance = dot / norm if norm > 0 else 0
            
            results.append((word, float(resonance)))

        # Sort by resonance and return top N
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_n]

if __name__ == "__main__":
    # Quick test
    map_file = Path(__file__).resolve().parents[2] / "data/knowledge/symbolic_map_5axis.json"
    engine = GeometricInterferenceEngine(str(map_file))
    
    test_context = "what is the"
    predictions = engine.predict_next_token(test_context)
    print(f"Context: '{test_context}'")
    for word, res in predictions:
        print(f"  -> '{word}' (Resonance: {res:.4f})")
