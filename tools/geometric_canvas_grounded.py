#!/usr/bin/env python3
"""
Geometric Canvas (Grounded) — Synthesus 5
Resonant rendering whose COLOUR is grounded in real co-occurrence statistics
(tools/color_grounding.py), not a hashed hue. The concept's colour now matches
the concept (sky→blue, grass→green, fire→red); texture is a derived-vector
interference field. Honest scope: this is a colour-grounded abstract field, not
a photographic object — recognisable objects need a learned visual model.
"""
import os, sys, math, json
from pathlib import Path
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from geometric_refinery import GeometricEngineFallback

SHARD_DIR = Path("/home/dakin/dev/Synthesus_4.0/data/geometric_shards")


class GroundedGeometricCanvas:
    def __init__(self, size=384):
        self.size = size
        self.engine = GeometricEngineFallback()
        self.colors = self._load(SHARD_DIR / "color_grounding.kn", "colors")
        self.derived = self._load(SHARD_DIR / "grounding_derived.kn", "vectors")
        print(f"🎨 Grounded Canvas {size}x{size} "
              f"({len(self.colors)} grounded colours, {len(self.derived)} derived vectors)")

    @staticmethod
    def _load(path, key):
        if path.exists():
            return json.load(open(path, encoding="utf-8")).get(key, {})
        return {}

    def concept_color(self, word):
        word = word.lower().strip()
        if word in self.colors:                       # grounded in statistics
            print(f"🔍 grounded colour for '{word}': {tuple(self.colors[word])}")
            return tuple(self.colors[word])
        # fallback: a stable but neutral hue from the hash (never black)
        v = self.engine.word_to_vector(word)
        print(f"🎲 no colour association for '{word}' — neutral hash hue")
        return self._hsv(v[3], 0.45, 0.8)

    def texture_params(self, word):
        """Derive interference frequency/orientation from the concept's vector."""
        v = self.derived.get(word.lower().strip()) or self.engine.word_to_vector(word)
        f1 = 6 + 18 * abs(v[0])
        f2 = 6 + 18 * abs(v[1] if len(v) > 1 else v[0])
        ang = (v[2] if len(v) > 2 else 0.3) * math.pi
        return f1, f2, ang

    def render(self, prompt, output_path=None):
        output_path = output_path or f"grounded_{prompt}.png"
        r0, g0, b0 = self.concept_color(prompt)
        f1, f2, ang = self.texture_params(prompt)
        ca, sa = math.cos(ang), math.sin(ang)

        img = Image.new("RGB", (self.size, self.size))
        px = img.load()
        for y in range(self.size):
            ny = y / self.size - 0.5
            for x in range(self.size):
                nx = x / self.size - 0.5
                u = nx * ca - ny * sa
                w = nx * sa + ny * ca
                # smooth multi-frequency interference field in [0,1]
                field = 0.5 + 0.5 * (0.6 * math.sin(u * f1 * math.pi) *
                                     math.cos(w * f2 * math.pi)
                                     + 0.4 * math.sin((u + w) * (f1 * 0.5) * math.pi))
                vign = 1.0 - 0.5 * (nx * nx + ny * ny)         # soft centre glow
                # brightness floored at 0.45 so a concept never goes black
                b = (0.45 + 0.55 * field) * vign
                px[x, y] = (min(255, int(r0 * b)),
                            min(255, int(g0 * b)),
                            min(255, int(b0 * b)))
        img.save(output_path)
        print(f"💾 saved {output_path}")

    @staticmethod
    def _hsv(h, s, v):
        h = (h % 1.0) * 6
        c = v * s; x = c * (1 - abs(h % 2 - 1)); m = v - c
        r, g, bb = [(c, x, 0), (x, c, 0), (0, c, x),
                    (0, x, c), (x, 0, c), (c, 0, x)][int(h) % 6]
        return (int((r + m) * 255), int((g + m) * 255), int((bb + m) * 255))


if __name__ == "__main__":
    canvas = GroundedGeometricCanvas(384)
    prompt = sys.argv[1] if len(sys.argv) > 1 else "apple"
    canvas.render(prompt)
