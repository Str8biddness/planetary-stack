#!/usr/bin/env python3
"""
Geometric Canvas — Synthesus 5
Prototype for 'Resonant Rendering'.
Generates an image by vibrating pixels to match a 5-axis text resonance field.
"""

import os
import sys
import math
import random
from PIL import Image
from pathlib import Path

# Add tools to path for the fallback engine
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'tools')))
from geometric_refinery import GeometricEngineFallback

class GeometricCanvas:
    def __init__(self, width=256, height=256):
        self.width = width
        self.height = height
        self.engine = GeometricEngineFallback()
        print(f"🎨 Geometric Canvas initialized ({width}x{height})")

    def generate_from_prompt(self, prompt, output_path="resonance_output.png"):
        print(f"🎬 Generating: '{prompt}'")
        
        # 1. Project Prompt to 5-Axis Vector (The 'Target Resonance')
        target_vec = self.engine.word_to_vector(prompt)
        print(f"📐 Target Resonance Vector: {target_vec}")

        # 2. Initialize Image
        img = Image.new('RGB', (self.width, self.height), color='black')
        pixels = img.load()

        # 3. Resonant Rendering Loop
        # For each pixel, we calculate its 'local resonance' with the prompt
        for y in range(self.height):
            for x in range(self.width):
                # Map pixel to normalized space [0-1]
                nx = x / self.width
                ny = y / self.height
                
                # Calculate resonance based on spatial interference
                # We use the prompt's Phase (Axis 4) and Scale (Axis 5) to drive color/intensity
                # and Spatial-Z (Axis 3) to drive local complexity
                
                # Harmonic interference pattern
                dist = math.sqrt((nx - target_vec[0])**2 + (ny - target_vec[1])**2)
                phase_interference = math.sin(dist * 10.0 + target_vec[3] * math.pi * 2)
                
                # Scale intensity by Axis 5 and depth by Axis 3
                intensity = (0.5 + 0.5 * phase_interference) * target_vec[4]
                
                # Resonate color (Phase -> RGB mapping)
                r, g, b = self._phase_to_rgb(target_vec[3] + (dist * 0.1))
                
                # Apply Z-axis 'blur' or complexity (simple simulation)
                z_mod = (1.0 - target_vec[2]) * 20.0
                noise = random.uniform(-z_mod, z_mod)
                
                pixels[x, y] = (
                    int(max(0, min(255, r * intensity + noise))),
                    int(max(0, min(255, g * intensity + noise))),
                    int(max(0, min(255, b * intensity + noise)))
                )

            if y % 50 == 0:
                print(f"   Vibrating pixels... {int(y/self.height*100)}%")

        img.save(output_path)
        print(f"💾 Render complete: {output_path}")

    def _phase_to_rgb(self, phase):
        # Maps a 0-1 phase to a colorful triplet
        h = (phase % 1.0) * 6.0
        c = 255
        x = int(c * (1 - abs(h % 2 - 1)))
        
        if h < 1: return (c, x, 0)
        if h < 2: return (x, c, 0)
        if h < 3: return (0, c, x)
        if h < 4: return (0, x, c)
        if h < 5: return (x, 0, c)
        return (c, 0, x)

if __name__ == "__main__":
    canvas = GeometricCanvas(512, 512)
    
    # Prompt examples:
    # "quantum nebula" -> high frequency phase
    # "forest" -> earthy scale
    # "blood moon" -> intense scale, specific phase
    
    prompt = "quantum resonance of a digital sun"
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
        
    canvas.generate_from_prompt(prompt, "geometric_resonance.png")
