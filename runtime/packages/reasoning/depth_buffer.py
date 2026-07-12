#!/usr/bin/env python3
"""
Per-object depth buffer for SI scenes — world Z for true DOF / future worlds.
=============================================================================

Each primitive gets a depth in [0,1] (0 = camera-near, 1 = far).
When painted, the depth map is updated under the coverage mask.
Camera ISP DOF uses this map instead of y-only hacks.

This is the bridge from 2D illustration → dimensional construction:
same depth field can later drive virtual worlds / view projection.

Axes note (SI opinion encoded as code):
  X,Y  — image plane
  Z    — depth (this buffer)
  optional later: yaw/pitch (camera), time (animation)
More axes help only when they are real degrees of freedom that project
consistently — not arbitrary high-D for its own sake.

Run: python packages/reasoning/depth_buffer.py
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np

# Base depth by role (far → near-ish defaults); refined by layout position
ROLE_DEPTH = {
    "bg": 0.98,
    "cloud_top": 0.90,
    "star_top": 0.95,
    "disc_top": 0.88,  # sun/moon still far
    "bird": 0.82,
    "triangle": 0.72,  # mountains
    "bridge": 0.48,
    "building": 0.45,
    "house": 0.42,
    "tree": 0.40,
    "bush": 0.38,
    "fence": 0.36,
    "boat": 0.34,
    "strip": 0.50,  # road recedes
    "river": 0.52,
    "ground": 0.55,
    "disc": 0.32,
    "flower": 0.30,
    "person": 0.28,
}


def depth_for_primitive(prim: Dict[str, Any], horizon: float = 0.66) -> float:
    """Estimate world depth z∈[0,1] for a scene primitive."""
    role = prim.get("role") or ""
    z = float(ROLE_DEPTH.get(role, 0.5))
    # Closer to bottom of frame (higher y) → nearer camera for ground objects
    y_anchor = prim.get("base", prim.get("y", prim.get("y0", horizon)))
    try:
        y_anchor = float(y_anchor)
    except (TypeError, ValueError):
        y_anchor = horizon
    if role in ("ground", "strip", "river"):
        # ground plane: interpolate near at y=1, horizon depth at y0
        z = float(np.clip(0.15 + 0.55 * (1.0 - (y_anchor - 0.2)), 0.2, 0.75))
    elif role in ("house", "tree", "person", "building", "boat", "fence", "bush", "flower", "disc", "bridge"):
        # objects on ground: nearer if lower on screen
        z = z * 0.55 + 0.45 * float(np.clip(1.15 - y_anchor, 0.15, 0.9))
    elif role == "triangle":
        # mountains sit on horizon — stay back
        z = float(np.clip(0.65 + 0.15 * (horizon - 0.1), 0.55, 0.85))
    # behind relation: slightly farther
    for rel in prim.get("relations") or []:
        if rel == "behind":
            z = float(np.clip(z + 0.08, 0, 1))
        elif rel == "front":
            z = float(np.clip(z - 0.08, 0, 1))
    return float(np.clip(z, 0.0, 1.0))


def make_depth_buffer(h: int, w: int, far: float = 1.0) -> np.ndarray:
    return np.full((h, w), float(far), dtype=np.float32)


def write_depth(
    depth: np.ndarray,
    mask: np.ndarray,
    z: float,
    *,
    soft: bool = True,
) -> None:
    """Update depth where mask covers; nearer (smaller z) wins like a z-buffer.

    Supports full-frame or matching-shape crop (bbox-restricted paint passes a crop).
    """
    m = np.asarray(mask, dtype=np.float32)
    if depth.shape[:2] != m.shape[:2]:
        return  # shape mismatch — skip rather than corrupt
    if soft:
        write = m > 0.08
    else:
        write = m > 0.5
    if not np.any(write):
        return
    z = float(np.clip(z, 0.0, 1.0))
    cur = depth[write]
    new = np.minimum(cur, z)
    if soft:
        a = m[write]
        depth[write] = cur * (1.0 - a) + new * a
        depth[write] = np.minimum(depth[write], new)
    else:
        depth[write] = new


def depth_for_role_mask(
    depth: np.ndarray,
    mask: np.ndarray,
    role: str,
    prim: Optional[Dict[str, Any]] = None,
    horizon: float = 0.66,
) -> None:
    z = depth_for_primitive(prim or {"role": role}, horizon=horizon)
    write_depth(depth, mask, z)


def focus_from_doc(doc, default: float = 0.35) -> float:
    """Pick focus depth: prefer person/house, else median object depth."""
    zs = []
    priority = []
    for p in doc:
        role = p.get("role")
        if role in ("bg", "ground"):
            continue
        z = depth_for_primitive(p)
        zs.append(z)
        if role in ("person", "house", "boat", "building"):
            priority.append(z)
    if priority:
        return float(np.median(priority))
    if zs:
        return float(np.median(zs))
    return default


def demo():
    h, w = 64, 96
    d = make_depth_buffer(h, w)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    yy /= h - 1
    xx /= w - 1
    # far mountain
    m = (yy < 0.5).astype(np.float32) * 0.5
    write_depth(d, m, 0.8)
    # near person blob
    r = np.sqrt((xx - 0.5) ** 2 + (yy - 0.7) ** 2)
    m2 = (r < 0.1).astype(np.float32)
    write_depth(d, m2, 0.25)
    print("depth range", d.min(), d.max(), "focus", focus_from_doc([
        {"role": "person", "base": 0.7},
        {"role": "triangle", "base": 0.66},
    ]))


if __name__ == "__main__":
    demo()
