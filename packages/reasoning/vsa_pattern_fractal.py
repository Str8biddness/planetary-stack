#!/usr/bin/env python3
"""
Pattern compression demo: a recursive tree pattern — Synthesus 5
================================================================

Tests the claim "scale the pattern database and the crude shapes become rich."
The 'tree' was a green circle because its pattern was one primitive. Here the
'tree' pattern is a RECURSIVE rule (an L-system): branch, then two smaller
branches at +/- an angle, repeat. A handful of parameters expands into hundreds
of branches + leaves — rich detail from a tiny pattern.

This is the real form of the insight: a procedural/geometric pattern is an
extremely COMPRESSED, symbolic, vector-encodable unit of visual knowledge
(nature is fractal, so it compresses well). The honest caveat: the RULE still
encodes sourced knowledge (how trees branch was learned by studying trees);
synthetic variation multiplies what the rule covers, it doesn't invent new
real-object knowledge.

Run:  ./venv/bin/python packages/reasoning/vsa_pattern_fractal.py
"""
from __future__ import annotations
import math
import os

from PIL import Image, ImageDraw

PI = math.pi

# THE ENTIRE "TREE" PATTERN — a compact parameter vector (this is the compression)
TREE_PATTERN = {
    "depth": 9, "len0": 0.22, "ratio": 0.76, "spread": 26.0,
    "branches": 2, "wobble": 7.0, "trunk_w": 14.0,
}


def grow(draw, x, y, angle, length, depth, p, S, rng, n=[0]):
    if depth == 0 or length < 0.004:
        # leaf: a small green blob at the twig tip
        r = 0.012 * S
        draw.ellipse([x*S - r, y*S - r, x*S + r, y*S + r], fill=(45, 120, 40))
        return
    x2 = x + length * math.sin(angle)
    y2 = y - length * math.cos(angle)
    w = max(1, p["trunk_w"] * (depth / p["depth"]))           # taper with depth
    shade = int(60 + 90 * (1 - depth / p["depth"]))           # bark lighter outward
    draw.line([x*S, y*S, x2*S, y2*S], fill=(shade, int(shade*0.62), 30), width=int(w))
    n[0] += 1
    for k in range(p["branches"]):
        off = (k - (p["branches"] - 1) / 2) * p["spread"]
        wob = rng() * p["wobble"] - p["wobble"] / 2
        grow(draw, x2, y2, angle + math.radians(off + wob),
             length * p["ratio"], depth - 1, p, S, rng, n)


def render(p=TREE_PATTERN, res=1024, out="fractal_tree.png", seed=3):
    import random
    random.seed(seed)
    ss = 2                                                     # supersample for AA
    S = res * ss
    img = Image.new("RGB", (S, S), (210, 226, 244))
    d = ImageDraw.Draw(img)
    d.rectangle([0, int(0.80 * S), S, S], fill=(70, 120, 55))  # ground
    n = [0]
    grow(d, 0.5, 0.80, 0.0, p["len0"], p["depth"], p, S, random.random, n)
    img = img.resize((res, res), Image.LANCZOS)               # downsample = anti-alias
    img.save(out)
    return out, n[0]


def main():
    out = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "fractal_tree.png"))
    path, branches = render(out=out)
    params = len(TREE_PATTERN)
    print(f"pattern parameters stored : {params}")
    print(f"branches grown            : {branches}")
    print(f"+ a leaf at every twig tip")
    print(f"compression               : ~{params} numbers -> {branches}+ rendered elements")
    print(f"rendered                  : {os.path.basename(path)} (resolution-free rule, AA)\n")
    print("Scaling a PATTERN (a recursive rule) — not pixels — is what turns the\n"
          "green circle into a detailed tree. The pattern is a tiny vector; the image\n"
          "is rich. That IS a symbolic vector DB entry at high compression. Honest\n"
          "caveat: the rule encodes sourced knowledge of how trees branch; synthetic\n"
          "variation multiplies coverage, it doesn't invent unseen real form.")


if __name__ == "__main__":
    main()
