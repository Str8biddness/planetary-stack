#!/usr/bin/env python3
"""
geometric_prediction_test.py
Validates the 5-axis geometric interference logic for token prediction.
"""

import numpy as np
import math

class GeometricPredictor:
    def __init__(self):
        # Sample vocabulary with 5-axis Symbolic Vectors
        # [X, Y, Z, Phase, Scale]
        self.vocabulary = {
            "the":        np.array([0.3, 0.3, 0.3, 0.1, 0.5]),
            "artificial":  np.array([0.8, 0.2, 0.7, 0.4, 0.9]),
            "intelligence": np.array([0.7, 0.25, 0.65, 0.5, 0.85]),
            "is":         np.array([0.1, 0.9, 0.2, 0.3, 0.4]),
            "revolutionary": np.array([0.9, 0.1, 0.8, 0.7, 1.0]),
            "technology":  np.array([0.85, 0.15, 0.75, 0.6, 0.7]),
        }

    def text_to_vector(self, word):
        return self.vocabulary.get(word.lower(), np.zeros(5))

    def predict_next(self, context_words):
        """
        Predicts next word using geometric interference.
        Each word creates a 'wave' in 5D space. 
        We calculate the constructive interference point.
        """
        if not context_words:
            return None

        # Convert context to vectors
        vectors = [self.text_to_vector(w) for w in context_words]
        
        # Calculate the 'Geometric Center' of the context
        # In a real SLLM, this would use the ProjectiveAcoustics wave equation.
        # Here we simulate with a weighted average based on 'Scale' (Axis 5)
        combined_vector = np.zeros(5)
        total_weight = 0
        
        for i, vec in enumerate(vectors):
            # Recency bias + Axis 5 (Scale)
            weight = (i + 1) * vec[4]
            combined_vector += vec * weight
            total_weight += weight
            
        target_vector = combined_vector / total_weight
        
        # Find the word in vocab that has the highest 'Resonance' (Cosine Similarity)
        # but is NOT already in the context (avoiding loops)
        best_word = None
        highest_resonance = -1
        
        for word, vec in self.vocabulary.items():
            if word in context_words:
                continue
                
            # Geometric Resonance (Cosine Sim)
            resonance = np.dot(target_vector, vec) / (np.linalg.norm(target_vector) * np.linalg.norm(vec))
            
            if resonance > highest_resonance:
                highest_resonance = resonance
                best_word = word
                
        return best_word, highest_resonance

def main():
    predictor = GeometricPredictor()
    
    # Test 1: Technical context
    context = ["artificial", "intelligence"]
    next_word, confidence = predictor.predict_next(context)
    print(f"Context: {context}")
    print(f"Geometric Prediction: '{next_word}' (Resonance: {confidence:.4f})")

    # Test 2: Descriptive context
    context = ["the", "technology"]
    next_word, confidence = predictor.predict_next(context)
    print(f"\nContext: {context}")
    print(f"Geometric Prediction: '{next_word}' (Resonance: {confidence:.4f})")

if __name__ == "__main__":
    main()
