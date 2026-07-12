#!/usr/bin/env python3
"""
Coarse-to-fine image pipeline — Synthesus 5 (image-studio)
==========================================================

  request --(reasoning kernel)--> PATTERN DOCUMENT (resolution-free scene graph)
          --(Hopfield imagination)--> fills vague/unknown entities
          --(geometric engine: max-world-size + pi)--> crisp HD raster

Honest scope: procedural / vector illustrations from the known SHAPES vocabulary.
Not photoreal. Growing realism = growing the vocabulary + templates.

Studio additions on top of image-roundout:
  - relation-aware layout (left of / right of / behind / in front of / above / under)
  - expanded vocab templates: road, river, fence, boat, person, building, flower,
    bird, bridge, bush
  - all new roles have paint paths (parity with SHAPES)

Run:  ./venv/bin/python packages/reasoning/vsa_pipeline_image.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Any, Optional

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
    # image-studio expansions
    "road": (.35, .35, .38), "path": (.48, .42, .32), "highway": (.30, .30, .33),
    "river": (.18, .42, .70), "stream": (.20, .48, .72), "creek": (.22, .50, .68),
    "fence": (.50, .38, .22),
    "boat": (.55, .35, .20), "ship": (.40, .42, .48),
    "person": (.22, .22, .30), "human": (.22, .22, .30), "figure": (.22, .22, .30),
    "building": (.42, .44, .50), "tower": (.38, .40, .48), "castle": (.45, .42, .40),
    "flower": (.85, .25, .40), "rose": (.80, .15, .28),
    "bird": (.18, .18, .22),
    "bridge": (.48, .40, .30),
    "bush": (.22, .48, .24), "shrub": (.24, .46, .22),
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
    "bg": 0, "ground": 1, "strip": 2, "river": 2, "bridge": 3,
    "triangle": 4, "building": 5, "house": 6, "fence": 7, "tree": 8, "bush": 8,
    "boat": 9, "disc": 10, "flower": 10, "person": 11,
    "disc_top": 12, "cloud_top": 12, "star_top": 13, "bird": 14,
}

# Roles that sit on/near the horizon and need horizontal packing
GROUND_ROLES = frozenset({
    "triangle", "tree", "disc", "house", "building", "fence", "boat",
    "person", "flower", "bush", "bridge",
})
SKY_ROLES = frozenset({"disc_top", "cloud_top", "star_top", "bird"})
# Full-width layers (not packed as point objects)
SPAN_ROLES = frozenset({"strip", "river"})

STYLES = frozenset({"flat", "soft", "night"})

# Relation phrases: (span_tokens, kind) — multi-word first
_REL_PHRASES: list[tuple[tuple[str, ...], str]] = [
    (("in", "front", "of"), "front"),
    (("left", "of"), "left"),
    (("right", "of"), "right"),
    (("next", "to"), "beside"),
    (("behind",), "behind"),
    (("beside",), "beside"),
    (("above",), "above"),
    (("over",), "above"),
    (("below",), "below"),
    (("under",), "below"),
    (("on",), "on"),
]


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


def _parse_relations(toks: list[str], entity_token_idxs: list[int]) -> list[dict[str, Any]]:
    """Find binary spatial relations between consecutive entities in the prompt.

    Returns list of {subject_tok, object_tok, kind} using token indices into `toks`.
    """
    if len(entity_token_idxs) < 2:
        return []
    ent_set = set(entity_token_idxs)
    rels: list[dict[str, Any]] = []
    i = 0
    while i < len(toks):
        matched = None
        for phrase, kind in _REL_PHRASES:
            n = len(phrase)
            if i + n <= len(toks) and tuple(toks[i:i + n]) == phrase:
                matched = (n, kind)
                break
        if not matched:
            i += 1
            continue
        n, kind = matched
        # subject = nearest entity token before phrase; object = nearest after
        subj = max((e for e in ent_set if e < i), default=None)
        obj = min((e for e in ent_set if e >= i + n), default=None)
        if subj is not None and obj is not None and subj != obj:
            rels.append({"subject_tok": subj, "object_tok": obj, "kind": kind})
        i += n
    return rels


def _apply_relations(
    x_by_raw: dict[int, float],
    y_off_by_raw: dict[int, float],
    scale_by_raw: dict[int, float],
    raw: list[dict[str, Any]],
    tok_to_raw: dict[int, int],
    relations: list[dict[str, Any]],
) -> None:
    """Mutate layout maps from parsed relations (subject relative to object)."""
    for rel in relations:
        si = tok_to_raw.get(rel["subject_tok"])
        oi = tok_to_raw.get(rel["object_tok"])
        if si is None or oi is None:
            continue
        # Skip pure bg/ground as subjects for left/right
        if raw[si]["role"] in ("bg", "ground") or raw[oi]["role"] in ("bg", "ground"):
            if rel["kind"] not in ("on", "above", "below"):
                continue
        ox = x_by_raw.get(oi, 0.5)
        kind = rel["kind"]
        if kind == "left":
            x_by_raw[si] = float(np.clip(ox - 0.18, 0.08, 0.92))
        elif kind == "right":
            x_by_raw[si] = float(np.clip(ox + 0.18, 0.08, 0.92))
        elif kind == "beside":
            # place to the side with less crowding
            side = -0.14 if ox > 0.5 else 0.14
            x_by_raw[si] = float(np.clip(ox + side, 0.08, 0.92))
        elif kind == "behind":
            x_by_raw[si] = float(np.clip(ox + 0.02, 0.08, 0.92))
            y_off_by_raw[si] = y_off_by_raw.get(si, 0.0) - 0.06  # higher on canvas
            scale_by_raw[si] = scale_by_raw.get(si, 1.0) * 0.85
        elif kind == "front":
            x_by_raw[si] = float(np.clip(ox - 0.02, 0.08, 0.92))
            y_off_by_raw[si] = y_off_by_raw.get(si, 0.0) + 0.04
            scale_by_raw[si] = scale_by_raw.get(si, 1.0) * 1.12
        elif kind == "above":
            y_off_by_raw[si] = y_off_by_raw.get(si, 0.0) - 0.12
            x_by_raw[si] = float(np.clip(ox + 0.0, 0.08, 0.92))
        elif kind == "below":
            y_off_by_raw[si] = y_off_by_raw.get(si, 0.0) + 0.08
            x_by_raw[si] = float(np.clip(ox, 0.08, 0.92))
        elif kind == "on":
            # subject rests at object's x (or horizon if object is ground)
            x_by_raw[si] = float(np.clip(ox if raw[oi]["role"] != "ground" else x_by_raw.get(si, ox), 0.08, 0.92))
            y_off_by_raw[si] = 0.0


# ── Stage 1: reasoning kernel -> pattern document (scene graph) ──
def pattern_document(
    request: str,
    imag=None,
    vidx=None,
    E=None,
    seed: Optional[int] = None,
    style: str = "flat",
) -> tuple[list[dict[str, Any]], float]:
    """Parse prompt into a resolution-free scene graph with multi-object + relation layout."""
    style = (style or "flat").lower().strip()
    if style not in STYLES:
        style = "flat"

    toks = [t.strip(".,!?;:\"'") for t in request.lower().split()]
    horizon = 0.66
    if style == "night":
        horizon = 0.68

    # First pass: resolve entities (with optional Hopfield imagination)
    raw: list[dict[str, Any]] = []
    tok_to_raw: dict[int, int] = {}
    entity_token_idxs: list[int] = []
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
        tok_to_raw[i] = len(raw)
        entity_token_idxs.append(i)
        raw.append({"entity": entity, "role": role, "color": color, "_tok": i})

    # Night style injects a dark sky if no bg present
    if style == "night" and not any(p["role"] == "bg" for p in raw):
        raw.insert(0, {
            "entity": "night",
            "role": "bg",
            "color": _style_modulate_color(PAL["night"], style, "night", "bg"),
            "_tok": -1,
        })
        # shift maps
        tok_to_raw = {k: v + 1 for k, v in tok_to_raw.items()}

    rng = _rng_from_seed(seed, request)
    relations = _parse_relations(toks, entity_token_idxs)

    # Default packing
    ground_idx = [i for i, p in enumerate(raw) if p["role"] in GROUND_ROLES]
    sky_idx = [i for i, p in enumerate(raw) if p["role"] in SKY_ROLES]
    ground_xs = _pack_positions(len(ground_idx), 0.18, 0.82, rng)
    sky_xs = _pack_positions(len(sky_idx), 0.15, 0.88, rng)
    x_by_raw: dict[int, float] = {}
    for idx, x in zip(ground_idx, ground_xs):
        x_by_raw[idx] = x
    for idx, x in zip(sky_idx, sky_xs):
        x_by_raw[idx] = x
    y_off_by_raw: dict[int, float] = {}
    scale_by_raw: dict[int, float] = {}

    _apply_relations(x_by_raw, y_off_by_raw, scale_by_raw, raw, tok_to_raw, relations)

    doc: list[dict[str, Any]] = []
    for i, p in enumerate(raw):
        role = p["role"]
        prim = {k: v for k, v in p.items() if k != "_tok"}
        sc = scale_by_raw.get(i, 1.0)
        yoff = y_off_by_raw.get(i, 0.0)
        if role == "bg":
            prim.update(x=0.0, y=0.0, w=1.0, h=1.0)
        elif role == "ground":
            prim.update(y0=horizon)
        elif role == "strip":  # road / path
            prim.update(y0=horizon + 0.02 + yoff, h=0.06 * sc, taper=0.35)
        elif role == "river":
            prim.update(y0=horizon + 0.04 + yoff, h=0.05 * sc, meander=0.03)
        elif role == "disc_top":
            y = 0.18 + float(rng.uniform(-0.02, 0.03)) + yoff
            r = (0.075 + float(rng.uniform(-0.01, 0.015))) * sc
            prim.update(x=x_by_raw.get(i, 0.72), y=float(np.clip(y, 0.05, 0.45)), r=r)
        elif role == "cloud_top":
            y = 0.16 + float(rng.uniform(-0.02, 0.04)) + yoff
            r = (0.065 + float(rng.uniform(-0.01, 0.01))) * sc
            prim.update(x=x_by_raw.get(i, 0.30), y=float(np.clip(y, 0.05, 0.40)), r=r)
        elif role == "star_top":
            y = 0.12 + float(rng.uniform(0.0, 0.18)) + yoff
            r = (0.028 + float(rng.uniform(0.0, 0.012))) * sc
            prim.update(x=x_by_raw.get(i, 0.50), y=float(np.clip(y, 0.04, 0.40)), r=r, points=5)
        elif role == "bird":
            y = 0.22 + float(rng.uniform(-0.05, 0.08)) + yoff
            prim.update(x=x_by_raw.get(i, 0.55), y=float(np.clip(y, 0.08, 0.50)), s=0.035 * sc)
        elif role == "triangle":
            h = 0.38 if p["entity"] != "fire" else 0.22
            hw = 0.28 if p["entity"] != "fire" else 0.10
            if p["entity"] == "hill":
                h, hw = 0.22, 0.34
            if p["entity"] == "pyramid":
                h, hw = 0.36, 0.24
            prim.update(
                cx=x_by_raw.get(i, 0.5),
                base=float(np.clip(horizon + yoff, 0.4, 0.9)),
                h=h * sc, hw=hw * sc,
            )
        elif role == "disc":
            r = (0.065 + float(rng.uniform(-0.01, 0.015))) * sc
            base = float(np.clip(horizon + yoff, 0.4, 0.9))
            prim.update(x=x_by_raw.get(i, 0.5), y=base - r * 0.95, r=r)
        elif role == "tree":
            r = (0.09 + float(rng.uniform(-0.015, 0.02))) * sc
            prim.update(
                x=x_by_raw.get(i, 0.30),
                base=float(np.clip(horizon + yoff, 0.4, 0.9)),
                r=r, fractal=True,
            )
        elif role == "bush":
            r = (0.055 + float(rng.uniform(-0.01, 0.01))) * sc
            prim.update(
                x=x_by_raw.get(i, 0.40),
                base=float(np.clip(horizon + yoff, 0.4, 0.9)),
                r=r,
            )
        elif role == "house":
            w = (0.14 + float(rng.uniform(-0.02, 0.02))) * sc
            hh = (0.12 + float(rng.uniform(-0.015, 0.02))) * sc
            prim.update(
                cx=x_by_raw.get(i, 0.55),
                base=float(np.clip(horizon + yoff, 0.4, 0.9)),
                w=w, h=hh,
            )
        elif role == "building":
            w = (0.10 + float(rng.uniform(-0.02, 0.03))) * sc
            hh = (0.22 + float(rng.uniform(0.0, 0.12))) * sc
            if p["entity"] == "tower":
                w, hh = 0.07 * sc, 0.32 * sc
            if p["entity"] == "castle":
                w, hh = 0.18 * sc, 0.20 * sc
            prim.update(
                cx=x_by_raw.get(i, 0.5),
                base=float(np.clip(horizon + yoff, 0.4, 0.9)),
                w=w, h=hh,
            )
        elif role == "fence":
            prim.update(
                x0=float(np.clip(x_by_raw.get(i, 0.35) - 0.12, 0.05, 0.7)),
                x1=float(np.clip(x_by_raw.get(i, 0.35) + 0.12, 0.2, 0.95)),
                base=float(np.clip(horizon + yoff, 0.4, 0.9)),
                h=0.06 * sc,
            )
        elif role == "boat":
            prim.update(
                x=x_by_raw.get(i, 0.45),
                y=float(np.clip(horizon + 0.02 + yoff, 0.45, 0.92)),
                w=0.10 * sc, h=0.035 * sc,
            )
        elif role == "person":
            prim.update(
                x=x_by_raw.get(i, 0.5),
                base=float(np.clip(horizon + yoff, 0.4, 0.9)),
                h=0.10 * sc,
            )
        elif role == "flower":
            prim.update(
                x=x_by_raw.get(i, 0.5),
                base=float(np.clip(horizon + yoff, 0.4, 0.9)),
                r=0.025 * sc,
            )
        elif role == "bridge":
            prim.update(
                cx=x_by_raw.get(i, 0.5),
                base=float(np.clip(horizon + yoff, 0.4, 0.9)),
                w=0.22 * sc, h=0.08 * sc,
            )
        else:
            prim.update(x=x_by_raw.get(i, 0.5), y=0.5, r=0.05)
        if relations:
            prim["relations"] = [
                r["kind"] for r in relations
                if tok_to_raw.get(r["subject_tok"]) == i
            ]
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


def _tree_fractal_mask(
    x, y, tx, base, r, res_h: int, res_w: int, px: float, seed: int = 0, high: bool = False
):
    """Richer canopy: layered discs + trunk; high detail adds more clusters + limbs."""
    trunk_w = 0.014 + r * 0.05
    trunk = (
        (np.abs(x - tx) < trunk_w)
        & (y > base - r * 1.15)
        & (y < base)
    ).astype(np.float64)
    cov = np.zeros((res_h, res_w), dtype=np.float64)
    centers = [
        (tx, base - r * 1.25, r * 1.05),
        (tx - r * 0.55, base - r * 0.95, r * 0.70),
        (tx + r * 0.55, base - r * 0.95, r * 0.70),
        (tx, base - r * 1.70, r * 0.55),
        (tx - r * 0.30, base - r * 1.45, r * 0.45),
        (tx + r * 0.30, base - r * 1.45, r * 0.45),
    ]
    if high:
        centers.extend([
            (tx - r * 0.75, base - r * 1.20, r * 0.40),
            (tx + r * 0.75, base - r * 1.20, r * 0.40),
            (tx - r * 0.15, base - r * 1.95, r * 0.38),
            (tx + r * 0.15, base - r * 1.95, r * 0.38),
            (tx, base - r * 2.15, r * 0.32),
            (tx - r * 0.45, base - r * 1.65, r * 0.35),
            (tx + r * 0.45, base - r * 1.65, r * 0.35),
        ])
    rng = np.random.default_rng(seed + 17)
    for cx, cy, cr in centers:
        jx = float(rng.uniform(-0.012, 0.012))
        jy = float(rng.uniform(-0.012, 0.012))
        rr = np.sqrt((x - (cx + jx)) ** 2 + (y - (cy + jy)) ** 2)
        cov = np.maximum(cov, 1.0 - smoothstep(cr - px, cr + px, rr))
    if high:
        # Diagonal limbs (cheap branch suggestion)
        for side in (-1.0, 1.0):
            bx0, by0 = tx, base - r * 0.55
            bx1, by1 = tx + side * r * 0.55, base - r * 1.15
            # distance to segment
            t = np.clip(
                ((x - bx0) * (bx1 - bx0) + (y - by0) * (by1 - by0))
                / max((bx1 - bx0) ** 2 + (by1 - by0) ** 2, 1e-9),
                0, 1,
            )
            px_ = bx0 + t * (bx1 - bx0)
            py_ = by0 + t * (by1 - by0)
            d = np.sqrt((x - px_) ** 2 + (y - py_) ** 2)
            limb = 1.0 - smoothstep(0.008 - px, 0.008 + px, d)
            trunk = np.maximum(trunk, limb * 0.85)
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
    detail: str = "standard",
) -> str:
    """Rasterize a pattern document to PNG at any resolution/aspect.

    detail='high' enables richer tree canopies + atmospheric post (vignette/haze).
    """
    style = (style or "flat").lower().strip()
    if style not in STYLES:
        style = "flat"
    detail = (detail or "standard").lower().strip()
    high = detail == "high"

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
                xx, yy, p["x"], p["base"], p["r"], h, w, aa, seed=s, high=high
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
        elif role == "strip":  # road / path
            y0 = float(p.get("y0", horizon + 0.02))
            hh = float(p.get("h", 0.06))
            # perspective taper toward horizon
            taper = float(p.get("taper", 0.35))
            t = np.clip((yy - y0) / max(hh, 1e-6), 0, 1)
            half = 0.08 + (0.42 - 0.08) * t  # wider near camera
            band = (
                (yy >= y0) & (yy <= y0 + hh)
                & (np.abs(xx - 0.5) < half * (1.0 - taper * (1.0 - t) * 0.3))
            )
            m = band.astype(np.float32) * smoothstep(y0 - aa, y0 + aa, yy)
            paint(m, c)
            # center dashed line for road-like
            if p.get("entity") in ("road", "highway"):
                dash = (
                    (np.abs(xx - 0.5) < 0.008)
                    & (yy >= y0 + 0.01)
                    & (yy <= y0 + hh - 0.01)
                    & (((yy * 40).astype(int) % 2) == 0)
                ).astype(np.float32)
                paint(dash, (.85, .80, .40))
        elif role == "river":
            y0 = float(p.get("y0", horizon + 0.04))
            hh = float(p.get("h", 0.05))
            meander = float(p.get("meander", 0.03))
            center = 0.5 + meander * np.sin(yy * PI * 3.0)
            half = 0.06 + 0.02 * np.sin(yy * PI * 5.0)
            band = (yy >= y0) & (yy <= y0 + hh * 3.5) & (np.abs(xx - center) < half)
            # also a softer band crossing the ground near horizon
            band2 = (np.abs(yy - horizon) < hh * 1.2) & (np.abs(xx - center) < half * 1.4)
            paint(np.maximum(band, band2).astype(np.float32), c)
        elif role == "building":
            half = p["w"] * 0.5
            top = p["base"] - p["h"]
            body = (
                smoothstep(half - 2 * aa, half + 2 * aa, half - np.abs(xx - p["cx"]))
                * smoothstep(top - 2 * aa, top + 2 * aa, yy)
                * (1.0 - smoothstep(p["base"] - 2 * aa, p["base"] + 2 * aa, yy))
            )
            paint(body, c)
            # window grid
            for row in range(3):
                for col in range(2):
                    wx = p["cx"] - p["w"] * 0.22 + col * p["w"] * 0.28
                    wy = top + p["h"] * (0.2 + row * 0.25)
                    wr = p["w"] * 0.08
                    win = (
                        (np.abs(xx - wx) < wr)
                        & (np.abs(yy - wy) < wr * 0.7)
                    ).astype(np.float32)
                    win_c = (.55, .72, .90) if style != "night" else (.95, .85, .40)
                    paint(win * 0.9, win_c)
        elif role == "fence":
            x0, x1 = float(p["x0"]), float(p["x1"])
            base, fh = float(p["base"]), float(p["h"])
            # rail
            rail = (
                (xx >= x0) & (xx <= x1)
                & (yy > base - fh * 0.7) & (yy < base - fh * 0.55)
            ).astype(np.float32)
            paint(rail, c)
            # posts
            n_posts = 5
            for k in range(n_posts):
                px_ = x0 + (x1 - x0) * k / max(n_posts - 1, 1)
                post = (
                    (np.abs(xx - px_) < 0.008)
                    & (yy > base - fh) & (yy < base)
                ).astype(np.float32)
                paint(post, c)
        elif role == "boat":
            # hull (half-ellipse) + cabin
            hx, hy, bw, bh = p["x"], p["y"], p["w"], p["h"]
            hull = (
                ((xx - hx) / max(bw, 1e-6)) ** 2 + ((yy - hy) / max(bh, 1e-6)) ** 2 < 1.0
            ) & (yy >= hy)
            paint(hull.astype(np.float32), c)
            cabin = (
                (np.abs(xx - hx) < bw * 0.25)
                & (yy > hy - bh * 1.6) & (yy < hy)
            ).astype(np.float32)
            paint(cabin, tuple(float(np.clip(v * 1.15, 0, 1)) for v in c))
        elif role == "person":
            # simple stick silhouette: head + body + legs
            px_, base, ph = p["x"], p["base"], p["h"]
            head_y = base - ph
            head = 1.0 - smoothstep(
                0.012 * (ph / 0.10) - aa, 0.012 * (ph / 0.10) + aa,
                np.sqrt((xx - px_) ** 2 + (yy - head_y) ** 2),
            )
            body = (
                (np.abs(xx - px_) < 0.012)
                & (yy > head_y) & (yy < base - ph * 0.35)
            ).astype(np.float32)
            legs = (
                ((np.abs(xx - (px_ - 0.012)) < 0.008) | (np.abs(xx - (px_ + 0.012)) < 0.008))
                & (yy > base - ph * 0.4) & (yy < base)
            ).astype(np.float32)
            paint(np.maximum(np.maximum(head, body), legs), c)
        elif role == "flower":
            px_, base, fr = p["x"], p["base"], p["r"]
            stem = (
                (np.abs(xx - px_) < 0.006)
                & (yy > base - fr * 3.5) & (yy < base)
            ).astype(np.float32)
            paint(stem, (.20, .50, .22))
            bloom = 1.0 - smoothstep(fr - aa, fr + aa,
                                     np.sqrt((xx - px_) ** 2 + (yy - (base - fr * 3.5)) ** 2))
            paint(bloom, c)
            # petals
            for ang in (0, 72, 144, 216, 288):
                rad = np.radians(ang)
                cx = px_ + np.cos(rad) * fr * 0.9
                cy = (base - fr * 3.5) + np.sin(rad) * fr * 0.9
                petal = 1.0 - smoothstep(
                    fr * 0.55 - aa, fr * 0.55 + aa,
                    np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2),
                )
                paint(petal * 0.85, c)
        elif role == "bird":
            # V wings
            bx, by, s = p["x"], p["y"], p["s"]
            left = (
                (np.abs((yy - by) - (bx - xx) * 0.6) < s * 0.35)
                & (xx > bx - s * 2) & (xx < bx)
                & (yy > by - s) & (yy < by + s)
            )
            right = (
                (np.abs((yy - by) - (xx - bx) * 0.6) < s * 0.35)
                & (xx < bx + s * 2) & (xx > bx)
                & (yy > by - s) & (yy < by + s)
            )
            paint((left | right).astype(np.float32), c)
        elif role == "bridge":
            cx, base, bw, bh = p["cx"], p["base"], p["w"], p["h"]
            # deck
            deck = (
                (np.abs(xx - cx) < bw * 0.5)
                & (yy > base - bh * 0.35) & (yy < base - bh * 0.15)
            ).astype(np.float32)
            paint(deck, c)
            # arch
            arch_r = bw * 0.45
            arch_cy = base - bh * 0.15
            dist = np.sqrt((xx - cx) ** 2 + (yy - arch_cy) ** 2)
            arch = (
                (dist < arch_r) & (dist > arch_r - 0.02)
                & (yy < arch_cy)
            ).astype(np.float32)
            paint(arch, c)
        elif role == "bush":
            trunk, canopy = _tree_fractal_mask(
                xx, yy, p["x"], p["base"], p["r"] * 0.9, h, w, aa,
                seed=(int(seed or 0) + 99), high=high,
            )
            # no tall trunk for bush — just canopy near ground
            low = canopy * (yy > p["base"] - p["r"] * 2.2).astype(np.float32)
            paint(low, c)

    # ── atmospheric post (wow polish) ────────────────────────────────
    if high or style in ("soft", "night"):
        # Distance haze: lift toward horizon band
        haze_strength = 0.14 if high else 0.08
        if style == "night":
            haze_col = np.array([0.08, 0.10, 0.18], dtype=np.float32)
        else:
            haze_col = np.array([0.72, 0.80, 0.92], dtype=np.float32)
        # stronger near mid-distance (around horizon)
        dist_w = np.exp(-((yy - horizon) ** 2) / 0.08) * haze_strength
        for k in range(3):
            img[:, :, k] = img[:, :, k] * (1.0 - dist_w) + haze_col[k] * dist_w

    if high or style == "soft":
        # Soft vignette
        cx, cy = 0.5, 0.5
        rad = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2 * 1.05)
        vig = 1.0 - 0.22 * smoothstep(0.55, 0.98, rad)
        img *= vig[..., None].astype(np.float32)

    if high and style != "flat":
        # Subtle film grain (deterministic from seed)
        rng = np.random.default_rng(int(seed if seed is not None else 0) + 101)
        grain = rng.normal(0.0, 0.012, size=img.shape).astype(np.float32)
        img = np.clip(img + grain, 0, 1)

    # Contact shadow under ground objects (subtle lift of presence)
    if high:
        for p in doc:
            if p.get("role") in ("house", "tree", "person", "building", "boat", "disc"):
                ox = p.get("x", p.get("cx", 0.5))
                by = p.get("base", p.get("y", horizon))
                if by is None:
                    continue
                sh = np.exp(-(((xx - ox) / 0.08) ** 2 + ((yy - (by + 0.01)) / 0.025) ** 2))
                img *= (1.0 - 0.18 * sh)[..., None].astype(np.float32)

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
