#!/usr/bin/env python3
"""
Lathe math for SI form — solid of revolution (not diffusion, not full 3D CAD).

Profile polyline in (radius, height) → revolved silhouette + simple shade.
Axis is vertical in image space (screen y). Provenance is lathe-like, not G-code UI.

Honest ceiling: round/axial props (cup, vase, column, fruit, bottle).
"""
from __future__ import annotations

import math
from typing import Any, List, Optional, Sequence, Tuple

import numpy as np

Point = Tuple[float, float]


# Named profiles: list of (radius, height_frac 0=base 1=top) in local unit scale
PROFILES: dict[str, List[Point]] = {
    "cup": [
        (0.35, 0.0), (0.38, 0.15), (0.40, 0.55), (0.42, 0.85), (0.36, 1.0),
    ],
    "vase": [
        (0.22, 0.0), (0.28, 0.15), (0.40, 0.35), (0.32, 0.55), (0.22, 0.75), (0.30, 0.95), (0.34, 1.0),
    ],
    "column": [
        (0.32, 0.0), (0.30, 0.08), (0.28, 0.5), (0.30, 0.92), (0.36, 1.0),
    ],
    "bottle": [
        (0.28, 0.0), (0.30, 0.4), (0.28, 0.55), (0.14, 0.7), (0.12, 0.95), (0.14, 1.0),
    ],
    "pot": [
        (0.30, 0.0), (0.42, 0.2), (0.45, 0.55), (0.40, 0.85), (0.36, 1.0),
    ],
    "fruit": [
        (0.05, 0.0), (0.35, 0.2), (0.42, 0.5), (0.35, 0.8), (0.08, 1.0),
    ],
    "apple": [
        (0.08, 0.0), (0.38, 0.25), (0.42, 0.55), (0.32, 0.85), (0.10, 1.0),
    ],
    "bowl": [
        (0.15, 0.0), (0.40, 0.25), (0.48, 0.55), (0.45, 0.85), (0.42, 1.0),
    ],
    "lamp_body": [
        (0.25, 0.0), (0.35, 0.2), (0.28, 0.5), (0.22, 0.8), (0.18, 1.0),
    ],
    "urn": [
        (0.28, 0.0), (0.38, 0.2), (0.42, 0.45), (0.30, 0.7), (0.18, 0.9), (0.22, 1.0),
    ],
    "silo": [
        (0.40, 0.0), (0.42, 0.15), (0.42, 0.75), (0.38, 0.9), (0.28, 1.0),
    ],
    "goblet": [
        (0.18, 0.0), (0.12, 0.25), (0.10, 0.45), (0.28, 0.55), (0.36, 0.8), (0.34, 1.0),
    ],
    "barrel": [
        (0.32, 0.0), (0.40, 0.2), (0.42, 0.5), (0.40, 0.8), (0.32, 1.0),
    ],
    "amphora": [
        (0.20, 0.0), (0.34, 0.2), (0.38, 0.45), (0.28, 0.7), (0.14, 0.9), (0.16, 1.0),
    ],
    "default": [
        (0.30, 0.0), (0.35, 0.5), (0.28, 1.0),
    ],
}

# entity name → profile key
ENTITY_PROFILE: dict[str, str] = {
    "cup": "cup", "mug": "cup", "glass": "cup",
    "vase": "vase", "urn": "urn",
    "column": "column", "pillar": "column", "post": "column",
    "bottle": "bottle", "flask": "bottle",
    "pot": "pot", "jar": "pot",
    "fruit": "fruit", "apple": "apple", "orange": "fruit", "ball": "fruit",
    "bowl": "bowl",
    "lamp": "lamp_body", "lamp_body": "lamp_body",
    "silo": "silo", "goblet": "goblet", "barrel": "barrel", "keg": "barrel",
    "amphora": "amphora",
}


def profile_for_entity(entity: str) -> List[Point]:
    e = (entity or "default").lower().strip()
    key = ENTITY_PROFILE.get(e, e if e in PROFILES else "default")
    return list(PROFILES.get(key, PROFILES["default"]))


def scale_profile(
    profile: Sequence[Point],
    *,
    height: float,
    max_radius: float,
) -> List[Point]:
    """Map unit profile to world height and radius."""
    h = max(float(height), 1e-4)
    rmax = max(float(max_radius), 1e-4)
    # profile radius already 0..~0.5; scale so max radius = max_radius
    mr = max(abs(p[0]) for p in profile) or 1.0
    out = []
    for r, t in profile:
        out.append((float(r) / mr * rmax, float(t) * h))
    return out


def silhouette_polygon(
    profile: Sequence[Point],
    *,
    cx: float,
    base: float,
) -> np.ndarray:
    """Closed polygon (N,2) for revolved silhouette (left+right meridians)."""
    # profile: (radius, height_from_base)
    right = [(cx + r, base - h) for r, h in profile]  # y up decreases on screen
    left = [(cx - r, base - h) for r, h in reversed(profile)]
    pts = right + left
    return np.asarray(pts, dtype=np.float32)


def paint_lathe(
    img: np.ndarray,
    xx: np.ndarray,
    yy: np.ndarray,
    *,
    cx: float,
    base: float,
    height: float,
    max_radius: float,
    color: Tuple[float, float, float],
    profile: Optional[Sequence[Point]] = None,
    entity: str = "lathe",
    aa: float = 0.004,
    sun_pos: Optional[Tuple[float, float]] = None,
    depth_map: Optional[np.ndarray] = None,
    depth_z: Optional[float] = None,
    yaw_deg: float = 0.0,
) -> np.ndarray:
    """Raster solid-of-revolution into img; return coverage mask.

    yaw_deg: slight horizontal foreshortening of apparent radius (ellipse cue)
    so orbit multi-pass still reads as a turned solid, not a flat card.
    """
    prof = list(profile) if profile is not None else profile_for_entity(entity)
    # Yaw: cos foreshorten apparent radius (solid of revolution side view)
    yaw = math.radians(float(np.clip(yaw_deg, -60, 60)))
    r_scale = float(max(0.55, abs(math.cos(yaw)) * 0.35 + 0.65))
    prof = scale_profile(prof, height=height, max_radius=max_radius * r_scale)
    # slight vertical squash when looking off-axis
    h_scale = float(0.92 + 0.08 * abs(math.cos(yaw)))
    height_eff = height * h_scale

    h, w = img.shape[:2]
    cov = np.zeros((h, w), dtype=np.float32)

    hs = np.array([p[1] for p in prof], dtype=np.float32)
    rs = np.array([p[0] for p in prof], dtype=np.float32)
    order = np.argsort(hs)
    hs, rs = hs[order], rs[order]

    y_top = base - height_eff
    y_bot = base
    pad = max(aa * 3, 0.01)
    max_r = float(rs.max()) if len(rs) else max_radius
    x0 = int(max(0, math.floor((cx - max_r - pad) * (w - 1))))
    x1 = int(min(w, math.ceil((cx + max_r + pad) * (w - 1)) + 1))
    y0 = int(max(0, math.floor((y_top - pad) * (h - 1))))
    y1 = int(min(h, math.ceil((y_bot + pad) * (h - 1)) + 1))
    if x1 <= x0 or y1 <= y0:
        return cov

    ys = np.linspace(0, 1, h, dtype=np.float32)[y0:y1]
    xs = np.linspace(0, 1, w, dtype=np.float32)[x0:x1]
    h_from_base = base - ys
    # remap profile heights to height_eff
    hs_n = hs * (height_eff / max(height, 1e-4))
    r_at = np.interp(h_from_base, hs_n, rs, left=0.0, right=0.0).astype(np.float32)
    valid_h = (h_from_base >= -aa) & (h_from_base <= height_eff + aa)
    dx = xs[None, :] - cx
    # ellipse: compress x by foreshortening already in r; add mild y-coupled oval
    oval = 1.0 + 0.12 * abs(math.sin(yaw))
    dist = np.abs(dx) * oval
    r2d = r_at[:, None]
    inside = (dist <= r2d + aa) & valid_h[:, None]
    edge = np.clip((r2d + aa - dist) / max(aa * 2, 1e-5), 0, 1)
    m = (edge * inside.astype(np.float32)).astype(np.float32)

    # simple revolve shade: lambert from lateral normal ~ x offset
    nx = np.clip(dx / np.maximum(r2d, 1e-4), -1, 1)
    # light from upper-left unless sun
    if sun_pos is not None:
        lx = float(sun_pos[0]) - cx
        ly = float(sun_pos[1]) - (base - height_eff * 0.5)
        ln = math.hypot(lx, ly) + 1e-5
        lx, ly = lx / ln, ly / ln
    else:
        lx, ly = -0.45, -0.55
    # normal on surface: (nx, 0) in 2d approx + slight vertical
    ndot = np.clip(-nx * lx + 0.25 * (-ly), 0.15, 1.0)
    shade = (0.35 + 0.65 * ndot).astype(np.float32)
    # rim light
    rim = np.clip(1.0 - np.abs(nx), 0, 1) ** 2 * 0.12
    shade = np.clip(shade + rim, 0.2, 1.15)

    col = np.asarray(color, dtype=np.float32).reshape(1, 1, 3)
    if col.max() > 1.5:
        col = col / 255.0
    crop = img[y0:y1, x0:x1]
    m3 = m[..., None]
    lit = col * shade[..., None]
    crop[:] = crop * (1.0 - m3) + lit * m3
    cov[y0:y1, x0:x1] = np.maximum(cov[y0:y1, x0:x1], m)

    if depth_map is not None and depth_z is not None:
        try:
            import depth_buffer as _db
            _db.write_depth(depth_map[y0:y1, x0:x1], m, float(depth_z))
        except Exception:
            pass
    return cov


def lathe_primitive(
    entity: str,
    *,
    cx: float = 0.5,
    base: float = 0.66,
    height: float = 0.14,
    max_radius: float = 0.06,
    color: Tuple[float, float, float] = (0.55, 0.45, 0.35),
) -> dict[str, Any]:
    """Scene-graph primitive for lathe objects."""
    return {
        "entity": entity,
        "role": "lathe",
        "color": color,
        "cx": float(cx),
        "base": float(base),
        "h": float(height),
        "r": float(max_radius),
        "profile": profile_for_entity(entity),
        "construction": "lathe",
        "machine": "lathe",
    }


def demo():
    from PIL import Image

    h, w = 256, 320
    img = np.ones((h, w, 3), dtype=np.float32) * np.array([0.55, 0.7, 0.9])
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    yy /= h - 1
    xx /= w - 1
    img[yy > 0.66] = (0.35, 0.55, 0.3)
    paint_lathe(
        img, xx, yy, cx=0.35, base=0.66, height=0.18, max_radius=0.07,
        color=(0.7, 0.35, 0.25), entity="vase",
    )
    paint_lathe(
        img, xx, yy, cx=0.65, base=0.66, height=0.10, max_radius=0.05,
        color=(0.85, 0.85, 0.9), entity="cup",
    )
    path = "/tmp/lathe_demo.png"
    Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(path)
    print("wrote", path)


if __name__ == "__main__":
    demo()
