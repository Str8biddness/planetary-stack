#!/usr/bin/env python3
"""
Resolution-independent analytic rendering — Synthesus 5
=======================================================

The "maximum world size + pi" idea, done rigorously.

  * MAXIMUM WORLD SIZE: everything is defined in a normalized [0,1]x[0,1] world.
    Geometry is stored relative to that reference frame, NOT in pixels — so the
    same scene rasterizes to ANY resolution with no loss.
  * pi / continuous math: shapes are CONTINUOUS functions (signed-distance fields,
    radial cos-falloff glows, smooth gradients). Edges are anti-aliased to
    sub-pixel precision using the pixel size (1/res in world units). pi appears
    where curvature/periodicity does (radial glow (1+cos(pi*t))/2, etc.).

This DOES surpass the resolution/sharpness bottleneck: crisp HD at any res.
It does NOT surpass the semantic bottleneck: it makes mathematically-perfect
*procedural illustrations*, not photographs — recognisable real objects still
need learned visual content. pi buys infinite sharpness, not learned meaning.

Run:  ./venv/bin/python packages/reasoning/vsa_hd_render.py
"""
from __future__ import annotations
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools"))
import scene_composer  # noqa: E402  (reuse SHAPES vocabulary)

PI = np.pi
PALETTE = {  # grounded-ish colours, 0..1
    "sky": (0.42, 0.62, 0.86), "grass": (0.32, 0.55, 0.28), "sun": (1.0, 0.86, 0.30),
    "mountain": (0.45, 0.42, 0.40), "apple": (0.80, 0.18, 0.16), "cloud": (0.96, 0.96, 0.98),
    "sea": (0.18, 0.40, 0.70), "sand": (0.86, 0.78, 0.55), "tree": (0.20, 0.50, 0.22),
    "fire": (0.92, 0.45, 0.12), "moon": (0.90, 0.90, 0.82), "star": (0.98, 0.92, 0.55),
    "house": (0.70, 0.40, 0.32), "snow": (0.95, 0.96, 0.99), "orange": (0.92, 0.55, 0.15),
}


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def render(concepts, res=1024, out="hd.png", horizon=0.66):
    # normalized world grid in [0,1]; px = one pixel in WORLD units (AA width)
    y, x = np.meshgrid(np.linspace(0, 1, res), np.linspace(0, 1, res), indexing="ij")
    px = 1.0 / res
    img = np.ones((res, res, 3), dtype=np.float64)
    roles = {c: scene_composer.SHAPES.get(c, "disc") for c in concepts}

    def paint(mask, color):                      # mask in [0,1] coverage
        for k in range(3):
            img[:, :, k] = img[:, :, k] * (1 - mask) + color[k] * mask

    order = {"bg": 0, "ground": 1, "triangle": 2, "tree": 3, "house": 3,
             "disc": 4, "disc_top": 5, "cloud_top": 5, "star_top": 5}
    has_sun = any(roles[c] == "disc_top" for c in concepts)

    for c in sorted(concepts, key=lambda c: order.get(roles[c], 6)):
        col = PALETTE.get(c, (0.6, 0.6, 0.6)); role = roles[c]
        if role == "bg":
            shade = 0.80 + 0.20 * (1 - y)        # smooth vertical gradient
            grad = np.stack([np.clip(np.array(col)[k] * shade, 0, 1) for k in range(3)], -1)
            img[:] = grad
            if has_sun:                           # radial cos glow around the sun
                r = np.sqrt((x - 0.72) ** 2 + (y - 0.22) ** 2)
                glow = (1 + np.cos(PI * np.clip(r / 0.45, 0, 1))) / 2 * 0.35
                img[:] = np.clip(img + glow[..., None] * np.array([1, 0.95, 0.7]), 0, 1)
        elif role == "ground":
            cov = smoothstep(horizon - px, horizon + px, y)
            shade = 0.85 + 0.25 * (y - horizon)
            paint(cov * 1.0, np.clip(np.array(col) * 1.0, 0, 1))
            img[:] = np.clip(img * (1 + 0.0), 0, 1)
            paint(cov, tuple(np.clip(np.array(col) * (0.9), 0, 1)))
        elif role in ("disc_top", "star_top"):    # sun/moon/star: smooth disc
            r = np.sqrt((x - 0.72) ** 2 + (y - 0.20) ** 2)
            paint(1 - smoothstep(0.085 - px, 0.085 + px, r), col)
        elif role == "cloud_top":                  # cloud: union of soft discs
            cov = np.zeros((res, res))
            for cx, cy, rr in [(0.24, 0.18, 0.07), (0.33, 0.17, 0.085), (0.42, 0.19, 0.06)]:
                r = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
                cov = np.maximum(cov, 1 - smoothstep(rr - px, rr + px, r))
            paint(cov, col)
        elif role == "triangle":                   # mountain: apex up, base on horizon
            ay = horizon - 0.42                      # apex height (smaller y = higher)
            hw = 0.32 * np.clip((y - ay) / (horizon - ay), 0, 1)   # half-width grows downward
            inside = np.minimum(hw - np.abs(x - 0.5),               # within sloped edges
                                np.minimum(y - ay, horizon - y))    # within vertical bounds
            paint(smoothstep(-px * 2, px * 2, inside), col)
        elif role in ("disc",):                    # object resting on the ground
            r = np.sqrt((x - 0.5) ** 2 + (y - (horizon - 0.07)) ** 2)
            paint(1 - smoothstep(0.07 - px, 0.07 + px, r), col)

    Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(out)
    return out


def main():
    scene = ["mountain", "grass", "sky", "sun"]
    for res in (256, 1024):
        out = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..",
                                           f"hd_{'_'.join(scene)}_{res}.png"))
        render(scene, res=res, out=out)
        print(f"  rendered {scene} at {res}x{res} -> {os.path.basename(out)}")
    print("\nSame normalized-world scene, rasterized crisp at any resolution "
          "(anti-aliased\nvia pixel-size in world units; pi in the radial glow). "
          "Resolution bottleneck\nsurpassed; photorealism still needs learned content.")


if __name__ == "__main__":
    main()
