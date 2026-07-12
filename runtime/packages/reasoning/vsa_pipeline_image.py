#!/usr/bin/env python3
"""
Coarse-to-fine image pipeline — Synthesus 5 (image-roundout)
===========================================================

  request --(reasoning kernel)--> PATTERN DOCUMENT (resolution-free scene graph)
          --(Hopfield imagination)--> fills vague/unknown entities
          --(geometric engine: max-world-size + pi)--> crisp HD raster

Honest scope: procedural / vector illustrations from the known SHAPES vocabulary.
Not photoreal. Growing realism = growing the vocabulary + templates.

Roundout additions:
  - full SHAPES ↔ renderer parity (house, star_top, fire)
  - multi-object layout packing (no more everything at x=0.5)
  - style knobs: flat | soft | night
  - seed for deterministic jitter
  - aspect ratio (width/height)
  - float32 raster path

Run:  ./venv/bin/python packages/reasoning/vsa_pipeline_image.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Any, Iterable, Optional

import numpy as np
from PIL import Image

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "..", "..", "tools"))
from vsa_twolayer import cooccurrence, ppmi, svd_embed  # noqa: E402
from vsa_hopfield import ModernHopfield                 # noqa: E402
import scene_composer                                   # noqa: E402

PI = np.pi

PAL = {
    "sky": (.42, .62, .86), "space": (.08, .10, .22), "night": (.08, .10, .22),
    "grass": (.32, .55, .28), "sun": (1, .86, .30),
    "mountain": (.45, .42, .40), "apple": (.80, .18, .16), "cloud": (.96, .96, .98),
    "sea": (.18, .40, .70), "ocean": (.16, .38, .68), "water": (.20, .42, .72),
    "sand": (.86, .78, .55), "tree": (.20, .50, .22), "field": (.40, .58, .28),
    "snow": (.94, .96, .98), "ground": (.40, .38, .32),
    "moon": (.90, .90, .82), "star": (.98, .92, .55), "house": (.70, .40, .32),
    "fire": (.92, .40, .12), "ball": (.70, .20, .20), "orange": (.92, .55, .15),
    "rock": (.50, .48, .46), "stone": (.48, .46, .44), "hill": (.42, .50, .34),
    "pyramid": (.78, .68, .42),
}
ADJ = {
    "red": (.78, .18, .16), "green": (.20, .55, .25), "blue": (.24, .40, .82),
    "yellow": (.92, .82, .25), "orange": (.92, .55, .15), "white": (.95, .95, .97),
    "brown": (.47, .28, .13), "gold": (.86, .70, .18), "golden": (.86, .70, .18),
    "purple": (.55, .28, .70), "pink": (.90, .50, .65), "black": (.12, .12, .14),
    "gray": (.55, .55, .58), "grey": (.55, .55, .58),
}

# Paint order (background → foreground)
ROLE_ORDER = {
    "bg": 0, "ground": 1, "triangle": 2, "house": 3, "tree": 4,
    "disc": 5, "disc_top": 6, "cloud_top": 6, "star_top": 7,
}

# Roles that sit on/near the horizon and need horizontal packing
GROUND_ROLES = frozenset({"triangle", "tree", "disc", "house"})
SKY_ROLES = frozenset({"disc_top", "cloud_top", "star_top"})

STYLES = frozenset({"flat", "soft", "night"})


def _rng_from_seed(seed: Optional[int], prompt: str = "") -> np.random.Generator:
    if seed is None:
        # Stable default from prompt so identical prompts share layout unless seed set.
        h = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:8]
        seed = int(h, 16) % (2**31 - 1)
    return np.random.default_rng(int(seed))


def _pack_positions(count: int, lo: float, hi: float, rng: np.random.Generator) -> list[float]:
    """Evenly space `count` items in [lo, hi] with small deterministic jitter."""
    if count <= 0:
        return []
    if count == 1:
        mid = 0.5 * (lo + hi)
        return [float(np.clip(mid + float(rng.uniform(-0.04, 0.04)), lo, hi))]
    xs = np.linspace(lo, hi, count)
    jitter = rng.uniform(-0.03, 0.03, size=count)
    return [float(np.clip(x + j, lo, hi)) for x, j in zip(xs, jitter)]


def _style_modulate_color(color: tuple, style: str, entity: str, role: str) -> tuple:
    c = np.array(color, dtype=np.float64)
    if style == "night":
        if role == "bg" or entity in ("sky", "space", "night"):
            c = np.array([.07, .09, .20])
        elif role == "ground":
            c = c * 0.55 + np.array([.05, .06, .10]) * 0.45
        elif role == "disc_top" and entity == "sun":
            # Night scenes turn "sun" into dim moon-ish if style forces night
            c = np.array([.75, .78, .88]) * 0.85
        else:
            c = c * 0.78 + 0.05
    elif style == "soft":
        c = c * 0.92 + 0.08  # slightly lifted pastels
    return tuple(float(np.clip(v, 0, 1)) for v in c)


# ── Stage 1: reasoning kernel -> pattern document (scene graph) ──
def pattern_document(
    request: str,
    imag=None,
    vidx=None,
    E=None,
    seed: Optional[int] = None,
    style: str = "flat",
) -> tuple[list[dict[str, Any]], float]:
    """Parse prompt into a resolution-free scene graph with multi-object layout."""
    style = (style or "flat").lower().strip()
    if style not in STYLES:
        style = "flat"

    toks = [t.strip(".,!?;:\"'") for t in request.lower().split()]
    horizon = 0.66
    if style == "night":
        horizon = 0.68

    # First pass: resolve entities (with optional Hopfield imagination)
    raw: list[dict[str, Any]] = []
    for i, t in enumerate(toks):
        entity = t
        role = scene_composer.SHAPES.get(entity)
        if role is None and imag is not None and vidx is not None and E is not None:
            if entity in vidx:
                recalled = imag.recall(E[vidx[entity]])[0]
                entity = recalled
                role = scene_composer.SHAPES.get(entity)
        if role is None:
            continue
        color = ADJ[toks[i - 1]] if i and toks[i - 1] in ADJ else PAL.get(entity, (.6, .6, .6))
        color = _style_modulate_color(color, style, entity, role)
        raw.append({"entity": entity, "role": role, "color": color})

    # Night style injects a dark sky if no bg present
    if style == "night" and not any(p["role"] == "bg" for p in raw):
        raw.insert(0, {
            "entity": "night",
            "role": "bg",
            "color": _style_modulate_color(PAL["night"], style, "night", "bg"),
        })

    rng = _rng_from_seed(seed, request)

    # Collect indices for packing
    ground_idx = [i for i, p in enumerate(raw) if p["role"] in GROUND_ROLES]
    sky_idx = [i for i, p in enumerate(raw) if p["role"] in SKY_ROLES]
    ground_xs = _pack_positions(len(ground_idx), 0.18, 0.82, rng)
    sky_xs = _pack_positions(len(sky_idx), 0.15, 0.88, rng)
    g_map = {idx: x for idx, x in zip(ground_idx, ground_xs)}
    s_map = {idx: x for idx, x in zip(sky_idx, sky_xs)}

    doc: list[dict[str, Any]] = []
    for i, p in enumerate(raw):
        role = p["role"]
        prim = dict(p)
        if role == "bg":
            prim.update(x=0.0, y=0.0, w=1.0, h=1.0)
        elif role == "ground":
            prim.update(y0=horizon)
        elif role == "disc_top":
            y = 0.18 + float(rng.uniform(-0.02, 0.03))
            r = 0.075 + float(rng.uniform(-0.01, 0.015))
            prim.update(x=s_map.get(i, 0.72), y=y, r=r)
        elif role == "cloud_top":
            y = 0.16 + float(rng.uniform(-0.02, 0.04))
            r = 0.065 + float(rng.uniform(-0.01, 0.01))
            prim.update(x=s_map.get(i, 0.30), y=y, r=r)
        elif role == "star_top":
            y = 0.12 + float(rng.uniform(0.0, 0.18))
            r = 0.028 + float(rng.uniform(0.0, 0.012))
            prim.update(x=s_map.get(i, 0.50), y=y, r=r, points=5)
        elif role == "triangle":
            # mountain / hill / pyramid / fire (fire gets taller + warmer handled in color)
            h = 0.38 if p["entity"] != "fire" else 0.22
            hw = 0.28 if p["entity"] != "fire" else 0.10
            if p["entity"] == "hill":
                h, hw = 0.22, 0.34
            if p["entity"] == "pyramid":
                h, hw = 0.36, 0.24
            prim.update(cx=g_map.get(i, 0.5), base=horizon, h=h, hw=hw)
        elif role == "disc":
            r = 0.065 + float(rng.uniform(-0.01, 0.015))
            prim.update(x=g_map.get(i, 0.5), y=horizon - r * 0.95, r=r)
        elif role == "tree":
            r = 0.09 + float(rng.uniform(-0.015, 0.02))
            prim.update(x=g_map.get(i, 0.30), base=horizon, r=r, fractal=True)
        elif role == "house":
            w = 0.14 + float(rng.uniform(-0.02, 0.02))
            h = 0.12 + float(rng.uniform(-0.015, 0.02))
            prim.update(cx=g_map.get(i, 0.55), base=horizon, w=w, h=h)
        else:
            # Unknown role: still emit so callers see honesty; renderer no-ops safely
            prim.update(x=0.5, y=0.5, r=0.05)
        doc.append(prim)

    return doc, horizon


# ── Stage 2: geometric engine (max world size + pi) -> HD raster ──
def smoothstep(a, b, x):
    # a/b/x may be scalars or ndarrays — use np ops only
    denom = np.maximum(np.asarray(b) - np.asarray(a), 1e-9)
    t = np.clip((np.asarray(x) - np.asarray(a)) / denom, 0, 1)
    return t * t * (3.0 - 2.0 * t)


def _star_mask(x, y, cx, cy, r, points: int = 5, px: float = 0.002):
    """Soft 5-point star coverage mask in [0,1]."""
    # Polar coords relative to center
    dx = x - cx
    dy = y - cy
    ang = np.arctan2(dy, dx)
    dist = np.sqrt(dx * dx + dy * dy)
    # Star radius modulates with angle
    # 5-point: period 2π/5, outer/inner ratio
    k = points
    # Align a tip upward-ish
    a = ang + PI / 2
    # Triangle-wave like radius
    sector = (a % (2 * PI / k)) / (2 * PI / k)  # 0..1
    # outer at 0 and 1, inner at 0.5
    tip = np.abs(sector - 0.5) * 2.0  # 1 at tip, 0 at valley
    r_edge = r * (0.40 + 0.60 * tip)
    return 1.0 - smoothstep(r_edge - px, r_edge + px, dist)


def _house_mask(x, y, cx, base, w, h, px: float):
    """House body (rect) + pitched roof."""
    half = w * 0.5
    body_top = base - h
    # Body
    body = (
        (np.abs(x - cx) < half)
        & (y > body_top)
        & (y < base)
    ).astype(np.float64)
    # Roof triangle: apex above body
    roof_h = h * 0.55
    apex_y = body_top - roof_h
    # width expands from apex to body_top
    t = np.clip((y - apex_y) / max(body_top - apex_y, 1e-9), 0, 1)
    half_roof = half * 1.12 * t
    roof_inside = (
        (y >= apex_y) & (y <= body_top)
        & (np.abs(x - cx) <= half_roof)
    )
    # soft edges via distance-ish paint later — use binary then smooth with dilate-ish
    roof = roof_inside.astype(np.float64)
    # Soften body edges
    body_edge = smoothstep(half - 2 * px, half + 2 * px, half - np.abs(x - cx))
    body_v = (
        smoothstep(body_top - 2 * px, body_top + 2 * px, y)
        * (1.0 - smoothstep(base - 2 * px, base + 2 * px, y))
    )
    body_soft = body_edge * body_v
    # Roof soft
    roof_soft = roof * smoothstep(-2 * px, 2 * px, half_roof - np.abs(x - cx) + 1e-6)
    return np.maximum(body_soft, roof_soft), body_soft, roof_soft


def _tree_fractal_mask(x, y, tx, base, r, res_h: int, res_w: int, px: float, seed: int = 0):
    """Richer canopy: layered discs + trunk (cheap fractal-ish, no L-system per pixel)."""
    trunk_w = 0.014 + r * 0.05
    trunk = (
        (np.abs(x - tx) < trunk_w)
        & (y > base - r * 1.15)
        & (y < base)
    ).astype(np.float64)
    # Canopy clusters
    cov = np.zeros((res_h, res_w), dtype=np.float64)
    centers = [
        (tx, base - r * 1.25, r * 1.05),
        (tx - r * 0.55, base - r * 0.95, r * 0.70),
        (tx + r * 0.55, base - r * 0.95, r * 0.70),
        (tx, base - r * 1.70, r * 0.55),
        (tx - r * 0.30, base - r * 1.45, r * 0.45),
        (tx + r * 0.30, base - r * 1.45, r * 0.45),
    ]
    rng = np.random.default_rng(seed + 17)
    for cx, cy, cr in centers:
        jx = float(rng.uniform(-0.01, 0.01))
        jy = float(rng.uniform(-0.01, 0.01))
        rr = np.sqrt((x - (cx + jx)) ** 2 + (y - (cy + jy)) ** 2)
        cov = np.maximum(cov, 1.0 - smoothstep(cr - px, cr + px, rr))
    return trunk, cov


def _dims(res: int, aspect: float) -> tuple[int, int]:
    """Return (height, width) pixels from long-edge res and aspect = width/height."""
    res = max(32, int(res))
    aspect = float(aspect) if aspect and aspect > 0 else 1.0
    aspect = float(np.clip(aspect, 0.5, 2.0))
    if aspect >= 1.0:
        w = res
        h = max(32, int(round(res / aspect)))
    else:
        h = res
        w = max(32, int(round(res * aspect)))
    return h, w


def render_doc(
    doc: list[dict[str, Any]],
    horizon: float,
    res: int = 1024,
    out: str = "pipeline.png",
    style: str = "flat",
    aspect: float = 1.0,
    seed: Optional[int] = None,
) -> str:
    """Rasterize a pattern document to PNG at any resolution/aspect."""
    style = (style or "flat").lower().strip()
    if style not in STYLES:
        style = "flat"

    h, w = _dims(res, aspect)
    # World coords: x in [0,1], y in [0,1] (y grows downward in image space)
    yy, xx = np.meshgrid(
        np.linspace(0.0, 1.0, h, dtype=np.float32),
        np.linspace(0.0, 1.0, w, dtype=np.float32),
        indexing="ij",
    )
    px = 1.0 / max(h, w)
    aa = 2.5 * px if style == "soft" else 1.0 * px
    img = np.ones((h, w, 3), dtype=np.float32)

    has_glow = any(
        p.get("role") == "disc_top" and p.get("entity") in ("sun", "moon")
        for p in doc
    )
    sun_pos = next(
        ((p["x"], p["y"]) for p in doc if p.get("role") == "disc_top"),
        (0.72, 0.20),
    )

    def paint(m, c):
        m = np.asarray(m, dtype=np.float32)
        c = np.asarray(c, dtype=np.float32)
        for k in range(3):
            img[:, :, k] = img[:, :, k] * (1.0 - m) + c[k] * m

    for p in sorted(doc, key=lambda p: ROLE_ORDER.get(p["role"], 9)):
        c = p["color"]
        role = p["role"]
        if role == "bg":
            shade = 0.78 + 0.22 * (1.0 - yy)
            if style == "night":
                shade = 0.55 + 0.45 * (1.0 - yy)
            img[:] = np.stack([np.clip(c[k] * shade, 0, 1) for k in range(3)], -1)
            if has_glow and style != "flat":
                r = np.sqrt((xx - sun_pos[0]) ** 2 + (yy - sun_pos[1]) ** 2)
                glow_r = 0.50 if style == "soft" else 0.40
                strength = 0.42 if style == "soft" else 0.28
                if style == "night":
                    strength = 0.18
                glow = (1.0 + np.cos(PI * np.clip(r / glow_r, 0, 1))) / 2.0 * strength
                tint = np.array([1.0, 0.95, 0.72], dtype=np.float32)
                if style == "night":
                    tint = np.array([0.75, 0.80, 1.0], dtype=np.float32)
                img[:] = np.clip(img + glow[..., None] * tint, 0, 1)
            elif has_glow and style == "flat":
                r = np.sqrt((xx - sun_pos[0]) ** 2 + (yy - sun_pos[1]) ** 2)
                glow = (1.0 + np.cos(PI * np.clip(r / 0.45, 0, 1))) / 2.0 * 0.30
                img[:] = np.clip(img + glow[..., None] * np.array([1, .95, .7], dtype=np.float32), 0, 1)
        elif role == "ground":
            paint(smoothstep(p["y0"] - aa, p["y0"] + aa, yy), c)
        elif role == "disc_top":
            r = np.sqrt((xx - p["x"]) ** 2 + (yy - p["y"]) ** 2)
            paint(1.0 - smoothstep(p["r"] - aa, p["r"] + aa, r), c)
        elif role == "cloud_top":
            cov = np.zeros((h, w), dtype=np.float32)
            scale = float(p.get("r", 0.07))
            for dx, dy, rr in (
                (-1.2 * scale, 0.0, 0.85 * scale),
                (0.0, -0.15 * scale, 1.05 * scale),
                (1.2 * scale, 0.0, 0.85 * scale),
                (-0.55 * scale, -0.25 * scale, 0.70 * scale),
                (0.55 * scale, -0.20 * scale, 0.70 * scale),
            ):
                rad = np.sqrt((xx - p["x"] - dx) ** 2 + (yy - p["y"] - dy) ** 2)
                cov = np.maximum(cov, 1.0 - smoothstep(rr - aa, rr + aa, rad))
            paint(cov, c)
        elif role == "star_top":
            m = _star_mask(xx, yy, p["x"], p["y"], p.get("r", 0.03),
                           points=int(p.get("points", 5)), px=aa)
            paint(m, c)
            # small core glow
            r = np.sqrt((xx - p["x"]) ** 2 + (yy - p["y"]) ** 2)
            core = (1.0 - smoothstep(0.0, p.get("r", 0.03) * 0.45, r)) * 0.55
            paint(core, (1.0, 1.0, 0.92))
        elif role == "triangle":
            ay = p["base"] - p["h"]
            hw = p["hw"] * np.clip((yy - ay) / max(p["base"] - ay, 1e-9), 0, 1)
            inside = np.minimum(hw - np.abs(xx - p["cx"]),
                                np.minimum(yy - ay, p["base"] - yy))
            paint(smoothstep(-2 * aa, 2 * aa, inside), c)
            # Fire: extra inner hotter triangle
            if p.get("entity") == "fire":
                ay2 = p["base"] - p["h"] * 0.65
                hw2 = p["hw"] * 0.55 * np.clip((yy - ay2) / max(p["base"] - ay2, 1e-9), 0, 1)
                inside2 = np.minimum(hw2 - np.abs(xx - p["cx"]),
                                     np.minimum(yy - ay2, p["base"] - yy))
                paint(smoothstep(-2 * aa, 2 * aa, inside2) * 0.85, (.98, .85, .25))
        elif role == "disc":
            r = np.sqrt((xx - p["x"]) ** 2 + (yy - p["y"]) ** 2)
            paint(1.0 - smoothstep(p["r"] - aa, p["r"] + aa, r), c)
            # subtle stem for apple-like
            if p.get("entity") in ("apple", "orange"):
                stem = (
                    (np.abs(xx - p["x"]) < 0.006)
                    & (yy > p["y"] - p["r"] - 0.03)
                    & (yy < p["y"] - p["r"] * 0.75)
                ).astype(np.float32)
                paint(stem, (.42, .28, .13))
        elif role == "tree":
            s = int(seed if seed is not None else 0) + hash(p.get("entity", "tree")) % 1000
            trunk, canopy = _tree_fractal_mask(
                xx, yy, p["x"], p["base"], p["r"], h, w, aa, seed=s
            )
            paint(trunk, (.42, .28, .13))
            paint(canopy, c)
        elif role == "house":
            full, body, roof = _house_mask(
                xx, yy, p["cx"], p["base"], p["w"], p["h"], aa
            )
            roof_c = tuple(float(np.clip(v * 0.75, 0, 1)) for v in c)
            # roof darker than walls
            paint(body, c)
            paint(roof, roof_c)
            # door
            dw, dh = p["w"] * 0.18, p["h"] * 0.45
            door = (
                (np.abs(xx - p["cx"]) < dw * 0.5)
                & (yy > p["base"] - dh)
                & (yy < p["base"])
            ).astype(np.float32)
            paint(door, (.35, .22, .14))
            # window
            wx = p["cx"] + p["w"] * 0.28
            wy = p["base"] - p["h"] * 0.55
            wr = p["w"] * 0.10
            win = (
                (np.abs(xx - wx) < wr)
                & (np.abs(yy - wy) < wr * 0.85)
            ).astype(np.float32)
            win_c = (.55, .75, .90) if style != "night" else (.90, .80, .35)
            paint(win, win_c)

    Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(out)
    return out


def renderable_roles() -> dict[str, str]:
    """Entity → role map (honest capability surface)."""
    return dict(scene_composer.SHAPES)


def main():
    toks = scene_composer.SHAPES
    corpus = "the blue sky sun cloud moon star above green grass apple tree mountain sea sand house fire hill"
    tk = [w for w in corpus.split() if w in toks]
    vidx = {w: i for i, w in enumerate(sorted(set(tk)))}
    E = svd_embed(ppmi(cooccurrence(tk * 3, vidx, window=4)), min(16, len(vidx)))
    imag = ModernHopfield(np.vstack([E[vidx[w]] for w in vidx]), list(vidx), beta=12.0)

    request = (
        "a red apple and a house and two trees on green grass under a blue sky "
        "with a bright sun a cloud and a star"
    )
    doc, horizon = pattern_document(request, imag, vidx, E, seed=7, style="soft")
    print(f"REQUEST: {request}\n")
    print("PATTERN DOCUMENT (resolution-free scene graph):")
    print(json.dumps([
        {k: (round(v, 3) if isinstance(v, float) else v)
         for k, v in p.items() if k != "color"}
        for p in doc
    ], indent=1))
    out = os.path.abspath(os.path.join(_HERE, "..", "..", "pipeline_scene.png"))
    render_doc(doc, horizon, res=768, out=out, style="soft", aspect=1.0, seed=7)
    print(f"\n-> geometric engine rendered: {os.path.basename(out)}")
    print("Roles painted include house/star/tree multi-layout (image-roundout).")


if __name__ == "__main__":
    main()
