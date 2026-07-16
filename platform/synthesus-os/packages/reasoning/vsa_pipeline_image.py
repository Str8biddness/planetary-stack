#!/usr/bin/env python3
"""
Coarse-to-fine image pipeline — Synthesus 5
===========================================

The CPU-only path you described:

  request --(reasoning kernel)--> PATTERN DOCUMENT (a resolution-free scene graph
            of primitives + normalized dimensions + colour + layout)
          --(Hopfield imagination)--> fills vague/unknown entities
          --(geometric engine: max-world-size + pi)--> crisp HD raster

No intermediate raster "rough draft" needed — the pattern graph IS the rough
draft, in symbolic form, so it renders to ANY resolution deterministically.

HONEST SCOPE (the part that does not move): the graph can only contain primitives
the system KNOWS (its shape vocabulary). Refinement perfects the *rendering* of
specified form; it cannot invent unseen form. So this makes crisp resolution-free
*scene / vector* imagery — not photoreal novel objects. Growing realism = growing
the vocabulary (by hand, or learned from images).

Run:  ./venv/bin/python packages/reasoning/vsa_pipeline_image.py
"""
from __future__ import annotations
import json
import os
import sys

import numpy as np
from PIL import Image

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "..", "..", "tools"))
from vsa_twolayer import cooccurrence, ppmi, svd_embed  # noqa: E402
from vsa_hopfield import ModernHopfield                 # noqa: E402
import scene_composer                                   # noqa: E402

PI = np.pi
PAL = {"sky": (.42, .62, .86), "grass": (.32, .55, .28), "sun": (1, .86, .30),
       "mountain": (.45, .42, .40), "apple": (.80, .18, .16), "cloud": (.96, .96, .98),
       "sea": (.18, .40, .70), "sand": (.86, .78, .55), "tree": (.20, .50, .22),
       "moon": (.90, .90, .82), "star": (.98, .92, .55), "house": (.70, .40, .32)}
ADJ = {"red": (.78, .18, .16), "green": (.20, .55, .25), "blue": (.24, .40, .82),
       "yellow": (.92, .82, .25), "orange": (.92, .55, .15), "white": (.95, .95, .97),
       "brown": (.47, .28, .13), "gold": (.86, .70, .18), "golden": (.86, .70, .18)}


# ── Stage 1: reasoning kernel -> pattern document (scene graph) ──
def pattern_document(request, imag=None, vidx=None, E=None):
    toks = [t.strip(".,") for t in request.lower().split()]
    doc, slot = [], {"disc_top": (.72, .20, .085), "cloud_top": (.30, .18, .07)}
    horizon = 0.66
    for i, t in enumerate(toks):
        role = scene_composer.SHAPES.get(t)
        if role is None and imag is not None:          # imagination fills unknowns
            base = E[vidx[t]] if t in vidx else None
            if base is not None:
                t = imag.recall(base)[0]; role = scene_composer.SHAPES.get(t)
        if role is None:
            continue
        color = ADJ[toks[i-1]] if i and toks[i-1] in ADJ else PAL.get(t, (.6, .6, .6))
        prim = {"entity": t, "role": role, "color": color}
        if role == "bg":
            prim.update(x=0, y=0, w=1, h=1)
        elif role == "ground":
            prim.update(y0=horizon)
        elif role in ("disc_top", "cloud_top"):
            prim.update(x=slot[role][0], y=slot[role][1], r=slot[role][2])
        elif role == "triangle":
            prim.update(cx=.5, base=horizon, h=.42, hw=.32)
        elif role == "disc":
            prim.update(x=.5, y=horizon - .07, r=.07)
        elif role == "tree":
            prim.update(x=.30, base=horizon, r=.10)
        doc.append(prim)
    return doc, horizon


# ── Stage 2: geometric engine (max world size + pi) -> HD raster ──
def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t)


def render_doc(doc, horizon, res=1024, out="pipeline.png"):
    y, x = np.meshgrid(np.linspace(0, 1, res), np.linspace(0, 1, res), indexing="ij")
    px = 1.0 / res
    img = np.ones((res, res, 3))
    has_sun = any(p["role"] == "disc_top" for p in doc)

    def paint(m, c):
        for k in range(3):
            img[:, :, k] = img[:, :, k] * (1 - m) + c[k] * m

    order = {"bg": 0, "ground": 1, "triangle": 2, "tree": 3, "disc": 4,
             "disc_top": 5, "cloud_top": 5}
    for p in sorted(doc, key=lambda p: order.get(p["role"], 6)):
        c, role = p["color"], p["role"]
        if role == "bg":
            img[:] = np.stack([np.clip(c[k] * (.80 + .20 * (1 - y)), 0, 1) for k in range(3)], -1)
            if has_sun:
                r = np.sqrt((x - .72) ** 2 + (y - .20) ** 2)
                glow = (1 + np.cos(PI * np.clip(r / .45, 0, 1))) / 2 * .35
                img[:] = np.clip(img + glow[..., None] * np.array([1, .95, .7]), 0, 1)
        elif role == "ground":
            paint(smoothstep(p["y0"] - px, p["y0"] + px, y), c)
        elif role in ("disc_top",):
            r = np.sqrt((x - p["x"]) ** 2 + (y - p["y"]) ** 2)
            paint(1 - smoothstep(p["r"] - px, p["r"] + px, r), c)
        elif role == "cloud_top":
            cov = np.zeros((res, res))
            for dx in (-.09, 0, .09):
                r = np.sqrt((x - p["x"] - dx) ** 2 + (y - p["y"]) ** 2)
                cov = np.maximum(cov, 1 - smoothstep(.06 - px, .06 + px, r))
            paint(cov, c)
        elif role == "triangle":
            ay = p["base"] - p["h"]
            hw = p["hw"] * np.clip((y - ay) / (p["base"] - ay), 0, 1)
            inside = np.minimum(hw - np.abs(x - p["cx"]), np.minimum(y - ay, p["base"] - y))
            paint(smoothstep(-2 * px, 2 * px, inside), c)
        elif role == "disc":
            r = np.sqrt((x - p["x"]) ** 2 + (y - p["y"]) ** 2)
            paint(1 - smoothstep(p["r"] - px, p["r"] + px, r), c)
        elif role == "tree":
            trunk = (np.abs(x - p["x"]) < .015) & (y > p["base"] - .09) & (y < p["base"])
            paint(trunk.astype(float), (.42, .28, .13))
            r = np.sqrt((x - p["x"]) ** 2 + (y - (p["base"] - .11)) ** 2)
            paint(1 - smoothstep(p["r"] - px, p["r"] + px, r), c)
    Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(out)
    return out


def main():
    # tiny grounding so imagination can map unknown words -> renderable concepts
    toks = scene_composer.SHAPES
    corpus = "the blue sky sun cloud above green grass apple tree mountain sea sand house"
    tk = [w for w in corpus.split() if w in toks]
    vidx = {w: i for i, w in enumerate(sorted(set(tk)))}
    E = svd_embed(ppmi(cooccurrence(tk * 3, vidx, window=4)), min(16, len(vidx)))
    imag = ModernHopfield(np.vstack([E[vidx[w]] for w in vidx]), list(vidx), beta=12.0)

    request = "a red apple on green grass under a blue sky with a bright sun a cloud and a tree"
    doc, horizon = pattern_document(request, imag, vidx, E)
    print(f"REQUEST: {request}\n")
    print("PATTERN DOCUMENT (resolution-free scene graph):")
    print(json.dumps([{k: (round(v, 3) if isinstance(v, float) else v)
                       for k, v in p.items() if k != 'color'} for p in doc], indent=1))
    out = os.path.abspath(os.path.join(_HERE, "..", "..", "pipeline_scene.png"))
    render_doc(doc, horizon, res=1024, out=out)
    print(f"\n-> geometric engine rendered HD: {os.path.basename(out)}")
    print("Stage1 reasoning->graph (CPU, resolution-free); Stage2 pi/max-size->HD raster.\n"
          "Content = the vocabulary in the graph; refinement perfects rendering, not content.")


if __name__ == "__main__":
    main()
