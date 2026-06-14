#!/usr/bin/env python3
"""
Geometric Canvas (Grounded Version) — Synthesus 5
Prototype for 'Resonant Rendering' using empirical grounding shards.
"""

import os
import sys
import math
import json
import random
from PIL import Image
from pathlib import Path

# Add tools to path for the fallback engine
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'tools')))
from geometric_refinery import GeometricEngineFallback

class GroundedGeometricCanvas:
    def __init__(self, width=512, height=512):
        self.width = width
        self.height = height
        self.engine = GeometricEngineFallback()
        self.shard_dir = Path("./data/geometric_shards")
        self.grounding_data = self._load_grounding()
        print(f"🎨 Grounded Canvas initialized ({width}x{height})")

    def _load_grounding(self):
        grounding_file = self.shard_dir / "grounding.kn"
        if grounding_file.exists():
            with open(grounding_file, 'r') as f:
                data = json.load(f)
                print(f"📂 Loaded {len(data['vectors'])} grounding anchors.")
                return data['vectors']
        return {}

    def get_resonant_vector(self, prompt):
        """
        Prioritizes empirical grounding over arbitrary hashing.
        """
        prompt_lower = prompt.lower().strip()
        if prompt_lower in self.grounding_data:
            print(f"🔍 Found Empirical Anchor for '{prompt_lower}'")
            return self.grounding_data[prompt_lower]
        
        print(f"🎲 Falling back to hash for '{prompt_lower}'")
        return self.engine.word_to_vector(prompt)

    def generate_from_prompt(self, prompt, output_path="grounded_resonance.png"):
        print(f"🎬 Resonant Rendering: '{prompt}'")
        
        # 1. Get the Grounded Target Vector
        target_vec = self.get_resonant_vector(prompt)
        print(f"📐 Target Vector: {target_vec}")

        # 2. Initialize Image
        img = Image.new('RGB', (self.width, self.height), color='black')
        pixels = img.load()

        # 3. Resonant Rendering Loop
        for y in range(self.height):
            for x in range(self.width):
                nx = x / self.width
                ny = y / self.height
                
                # Calculate interference pattern centered on the spatial grounding (X, Y)
                dist = math.sqrt((nx - target_vec[0])**2 + (ny - target_vec[1])**2)
                
                # Use Phase (Axis 4) to drive harmonic frequency
                # Use Z (Axis 3) to drive spatial detail/noise
                # Use Scale (Axis 5) for luminance intensity
                
                interference = math.sin(dist * (20.0 * target_vec[2]) + target_vec[3] * math.pi * 2)
                
                # Apply physical grounding logic:
                # - Phase is the 'Identity' (Color)
                # - Scale is the 'Presence' (Brightness)
                # - Z is the 'Structural Complexity'
                
                intensity = (0.5 + 0.5 * interference) * target_vec[4]
                
                # Map Phase to realistic RGB
                r, g, b = self._phase_to_rgb(target_vec[3])
                
                # Add complexity-based noise (Z-axis)
                complexity_noise = random.uniform(-target_vec[2]*50, target_vec[2]*50)
                
                pixels[x, y] = (
                    int(max(0, min(255, r * intensity + complexity_noise))),
                    int(max(0, min(255, g * intensity + complexity_noise))),
                    int(max(0, min(255, b * intensity + complexity_noise)))
                )

            if y % 100 == 0:
                print(f"   Vibrating pixels at {target_vec[3]*360:.1f}° Phase... {int(y/self.height*100)}%")

        img.save(output_path)
        print(f"💾 Grounded Render complete: {output_path}")

    def _phase_to_rgb(self, phase):
        h = (phase % 1.0) * 360
        # Simple HSV to RGB logic
        s = 0.9
        v = 1.0
        
        c = v * s
        x = c * (1 - abs((h / 60) % 2 - 1))
        m = v - c
        
        if 0 <= h < 60: r, g, b = c, x, 0
        elif 60 <= h < 120: r, g, b = x, c, 0
        elif 120 <= h < 180: r, g, b = 0, c, x
        elif 180 <= h < 240: r, g, b = 0, x, c
        elif 240 <= h < 300: r, g, b = x, 0, c
        else: r, g, b = c, 0, x
        
        return (int((r+m)*255), int((g+m)*255), int((b+m)*255))

if __name__ == "__main__":
    canvas = GroundedGeometricCanvas(512, 512)
    prompt = sys.argv[1] if len(sys.argv) > 1 else "apple"
    canvas.generate_from_prompt(prompt, f"grounded_{prompt}.png")
