#!/usr/bin/env python3
"""
GeometricEmbedder — 5-Axis Symbolic Vector Mapper
Implements the Synthesus 5 CHAL 5-Axis Logic:
[X, Y, Z, Phase, Scale]
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
from pathlib import Path
from typing import Optional, Union, List

import numpy as np

logger = logging.getLogger(__name__)

class GeometricEmbedder:
    """
    Deterministically maps text to 5-axis Symbolic Vectors.
    No neural network; uses geometric projection and deterministic hashing.
    """

    DIM = 5

    def __init__(self, frequency_map: Optional[dict[str, int]] = None):
        """
        Args:
            frequency_map: Optional dictionary of word frequencies to calculate Axis 5 (Scale).
        """
        self.frequency_map = frequency_map or {}
        self.max_freq = max(self.frequency_map.values()) if self.frequency_map else 1.0

    def word_to_vector(self, word: str) -> np.ndarray:
        """
        Maps a single word to a 5-axis symbolic vector.
        Deterministic and stateless.
        """
        word = word.lower().strip()
        if not word:
            return np.zeros(self.DIM, dtype=np.float32)

        # Use MD5 hashes for deterministic axis coordinates
        h = hashlib.md5(word.encode()).digest()
        
        # Axis 1-3: Spatial X, Y, Z
        # Map first 6 bytes to X, Y, Z (0.0 to 1.0)
        x = (h[0] + h[1] * 256) / 65535.0
        y = (h[2] + h[3] * 256) / 65535.0
        z = (h[4] + h[5] * 256) / 65535.0

        # Axis 4: Phase (Frequency/Temporal)
        # We can use the word length or a different hash slice
        phase = (h[6] + h[7] * 256) / 65535.0

        # Axis 5: Scale (Intensity/Importance)
        # Calculated from frequency map if available, else a hash slice
        if word in self.frequency_map:
            freq = self.frequency_map[word]
            # Logarithmic scaling to capture order of magnitude differences
            scale = math.log(freq + 1) / math.log(self.max_freq + 1)
        else:
            scale = (h[8] + h[9] * 256) / 65535.0

        return np.array([x, y, z, phase, scale], dtype=np.float32)

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """
        Converts a list of texts (sentences) into 5-axis vectors.
        Uses the 'Geometric Center' of the words.
        """
        vectors = []
        for text in texts:
            words = text.split()
            if not words:
                vectors.append(np.zeros(self.DIM, dtype=np.float32))
                continue
            
            # Sum up word vectors with 'Scale' as weight
            word_vecs = [self.word_to_vector(w) for w in words]
            combined = np.zeros(self.DIM, dtype=np.float32)
            total_weight = 0
            
            for vec in word_vecs:
                weight = vec[4] # Scale axis
                combined += vec * weight
                total_weight += weight
                
            if total_weight > 0:
                combined /= total_weight
            
            vectors.append(combined)
            
        return np.vstack(vectors).astype(np.float32)

if __name__ == "__main__":
    # Test script
    embedder = GeometricEmbedder(frequency_map={"technology": 1000, "is": 5000})
    test_word = "technology"
    vec = embedder.word_to_vector(test_word)
    print(f"Word: {test_word} -> Vector: {vec}")
    
    test_text = "technology is revolutionary"
    vec_text = embedder.embed_texts([test_text])
    print(f"Text: '{test_text}' -> Vector: {vec_text}")
