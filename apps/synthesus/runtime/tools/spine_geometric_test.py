#!/usr/bin/env python3
"""
spine_geometric_test.py
Tests the GenerationSpine's new 5-axis geometric generation path.
"""

import sys
from pathlib import Path

# Add packages to path
sys.path.append(str(Path(__file__).resolve().parents[1] / "packages"))

from reasoning.generation.spine import GenerationSpine, SpineInput

def main():
    print("🚀 Initializing Synthesus Generation Spine (SLLM Mode)...")
    spine = GenerationSpine()
    
    if not spine._geometric_engine:
        print("❌ Error: Geometric Engine not initialized. Check mapping file.")
        return

    # Test Query
    query = "what is the"
    print(f"\nTarget Query: '{query}'")
    
    inp = SpineInput(
        query=query,
        domain="chat",
        source_module="sllm_geometric"
    )
    
    print("Generating response via 5-axis resonance...")
    output = spine.generate(inp)
    
    print("\n=== Spine Output ===")
    print(f"Original Prediction: {output.text}")
    print(f"Final (Personality Applied): {output.final_text}")
    print(f"Resonance Confidence: {output.trace.mean_logprob:.4f}")
    print(f"Latency: {output.latency_ms:.2f}ms")
    print("====================")

if __name__ == "__main__":
    main()
