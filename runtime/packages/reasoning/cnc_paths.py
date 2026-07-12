#!/usr/bin/env python3
"""
CNC path math for SI image construction — Synthesus (not G-code UI, not diffusion).
==============================================================================

Uses the *math* of machine toolpaths to build resolution-free form:

  G1  — linear segments
  G2/G3 — circular arcs (CW / CCW)
  Tool-radius offset — parallel curves / outlines
  Contour / pocket — closed path fill
  Multi-pass — layered depth for richer structure

Product surface: path primitives on the scene graph. We do NOT require users
to type G-code. Internal path ops may be logged as g-like ops for provenance.

Honest ceiling: precision form language. Photoreal *look* still comes from
camera_isp. Content still limited by what paths we author for each entity.

Run:  python packages/reasoning/cnc_paths.py
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional, Sequence, Tuple

import numpy as np

PI = math.pi
Point = Tuple[float, float]


# ── Path representation ──────────────────────────────────────────────────

@dataclass
class LineSeg:
    x0: float
    y0: float
    x1: float
    y1: float
    kind: str = "G1"

    def length(self) -> float:
        return math.hypot(self.x1 - self.x0, self.y1 - self.y0)


@dataclass
class ArcSeg:
    """Circular arc through center + radius + start/end angles (radians).

    G2 = CW, G3 = CCW in screen coords where y grows downward — we use
    mathematical angles (CCW from +x) and a `cw` flag for direction of travel.
    """
    cx: float
    cy: float
    r: float
    a0: float
    a1: float
    cw: bool = False  # False = G3 CCW, True = G2 CW
    kind: str = "G3"

    def __post_init__(self):
        self.kind = "G2" if self.cw else "G3"
        self.r = abs(self.r)


Seg = LineSeg | ArcSeg


@dataclass
class Path:
    segs: List[Seg] = field(default_factory=list)
    closed: bool = False
    meta: dict = field(default_factory=dict)

    def append(self, seg: Seg) -> "Path":
        self.segs.append(seg)
        return self

    def extend(self, segs: Iterable[Seg]) -> "Path":
        self.segs.extend(segs)
        return self

    def empty(self) -> bool:
        return not self.segs


# ── Constructors (work coordinates, normalized [0,1] world) ──────────────

def line(x0: float, y0: float, x1: float, y1: float) -> LineSeg:
    return LineSeg(x0, y0, x1, y1)


def polyline(pts: Sequence[Point], closed: bool = False) -> Path:
    p = Path(closed=closed)
    if len(pts) < 2:
        return p
    for i in range(len(pts) - 1):
        (x0, y0), (x1, y1) = pts[i], pts[i + 1]
        p.append(line(x0, y0, x1, y1))
    if closed and len(pts) >= 3:
        (x0, y0), (x1, y1) = pts[-1], pts[0]
        p.append(line(x0, y0, x1, y1))
    return p


def rect(cx: float, cy: float, w: float, h: float) -> Path:
    """Axis-aligned rectangle centered at (cx, cy) — bottom at cy+h/2 if y-down.

    We treat cy as center; y increases downward (image space).
    """
    hw, hh = w * 0.5, h * 0.5
    pts = [
        (cx - hw, cy - hh),
        (cx + hw, cy - hh),
        (cx + hw, cy + hh),
        (cx - hw, cy + hh),
    ]
    return polyline(pts, closed=True)


def house_contour(cx: float, base: float, w: float, h: float) -> Path:
    """Classic house silhouette: walls + pitched roof (closed contour)."""
    hw = w * 0.5
    top = base - h
    roof_peak = top - h * 0.55
    pts = [
        (cx - hw, base),
        (cx - hw, top),
        (cx, roof_peak),
        (cx + hw, top),
        (cx + hw, base),
    ]
    return polyline(pts, closed=True)


def circle(cx: float, cy: float, r: float, segs: int = 48) -> Path:
    """Closed circle via G3-style polyline approximation (stable for fill)."""
    pts = []
    for i in range(segs):
        a = 2 * PI * i / segs
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return polyline(pts, closed=True)


def arc_g3(cx: float, cy: float, r: float, a0: float, a1: float) -> ArcSeg:
    """CCW arc (G3)."""
    return ArcSeg(cx, cy, r, a0, a1, cw=False)


def arc_g2(cx: float, cy: float, r: float, a0: float, a1: float) -> ArcSeg:
    """CW arc (G2)."""
    return ArcSeg(cx, cy, r, a0, a1, cw=True)


def mountain_contour(cx: float, base: float, h: float, hw: float) -> Path:
    return polyline(
        [(cx - hw, base), (cx, base - h), (cx + hw, base)],
        closed=True,
    )


def person_path(x: float, base: float, h: float) -> Path:
    """Stick figure as open path (stroke only)."""
    head_r = h * 0.12
    head_y = base - h + head_r
    neck = base - h + head_r * 2.1
    hip = base - h * 0.38
    # body
    p = Path(closed=False, meta={"stroke_only": True})
    p.append(line(x, neck, x, hip))
    # legs
    p.append(line(x, hip, x - h * 0.12, base))
    p.append(line(x, hip, x + h * 0.12, base))
    # arms
    arm_y = neck + (hip - neck) * 0.35
    p.append(line(x - h * 0.14, arm_y, x + h * 0.14, arm_y))
    # head as separate circle path stored in meta for dual paint
    p.meta["head"] = (x, head_y, head_r)
    return p


def fence_path(x0: float, x1: float, base: float, h: float, posts: int = 5) -> Path:
    p = Path(closed=False, meta={"stroke_only": True})
    rail_y = base - h * 0.65
    p.append(line(x0, rail_y, x1, rail_y))
    p.append(line(x0, base - h * 0.40, x1, base - h * 0.40))
    for i in range(posts):
        t = i / max(posts - 1, 1)
        x = x0 + (x1 - x0) * t
        p.append(line(x, base - h, x, base))
    return p


def boat_path(x: float, y: float, w: float, h: float) -> Path:
    """Hull as closed crescent-ish polygon + cabin rect."""
    hw, hh = w * 0.5, h
    hull = polyline(
        [
            (x - hw, y),
            (x - hw * 0.7, y + hh * 0.3),
            (x, y + hh),
            (x + hw * 0.7, y + hh * 0.3),
            (x + hw, y),
        ],
        closed=True,
    )
    hull.meta["cabin"] = rect(x, y - hh * 0.6, w * 0.35, h * 0.9)
    return hull


def tree_canopy_paths(x: float, base: float, r: float, seed: int = 0) -> List[Path]:
    """Trunk (stroke) + canopy circles (fill) — L-system-ish multi-pass structure."""
    rng = np.random.default_rng(seed + 3)
    trunk = Path(closed=False, meta={"stroke_only": True, "width": 0.012 + r * 0.04})
    trunk.append(line(x, base, x, base - r * 1.2))
    # multi-pass limbs (G1)
    for side in (-1.0, 1.0):
        trunk.append(
            line(x, base - r * 0.55, x + side * r * 0.5, base - r * 1.1)
        )
    canopies = [trunk]
    centers = [
        (x, base - r * 1.25, r * 1.0),
        (x - r * 0.5, base - r * 0.95, r * 0.65),
        (x + r * 0.5, base - r * 0.95, r * 0.65),
        (x, base - r * 1.65, r * 0.5),
    ]
    if r > 0.05:
        centers.extend([
            (x - r * 0.35, base - r * 1.4, r * 0.4),
            (x + r * 0.35, base - r * 1.4, r * 0.4),
            (x, base - r * 1.95, r * 0.35),
        ])
    for cx, cy, cr in centers:
        jx = float(rng.uniform(-0.01, 0.01))
        jy = float(rng.uniform(-0.01, 0.01))
        canopies.append(circle(cx + jx, cy + jy, cr * float(rng.uniform(0.92, 1.05))))
    return canopies


def building_contour(cx: float, base: float, w: float, h: float) -> Path:
    return rect(cx, base - h * 0.5, w, h)


def flower_paths(x: float, base: float, r: float) -> List[Path]:
    stem = Path(closed=False, meta={"stroke_only": True, "width": 0.008})
    stem.append(line(x, base, x, base - r * 3.5))
    bloom_y = base - r * 3.5
    paths = [stem, circle(x, bloom_y, r)]
    for k in range(5):
        a = 2 * PI * k / 5
        paths.append(circle(x + math.cos(a) * r * 0.9, bloom_y + math.sin(a) * r * 0.9, r * 0.55))
    return paths


def bridge_paths(cx: float, base: float, w: float, h: float) -> List[Path]:
    deck = rect(cx, base - h * 0.25, w, h * 0.18)
    # arch as polyline under deck
    hw = w * 0.45
    arch_pts = []
    for i in range(17):
        t = i / 16
        a = PI * t  # 0..pi
        arch_pts.append((cx - hw * math.cos(a), base - h * 0.15 + hw * 0.55 * math.sin(a)))
    arch = polyline(arch_pts, closed=False)
    arch.meta["stroke_only"] = True
    arch.meta["width"] = 0.012
    return [deck, arch]


# ── Discretize / offset / multi-pass ─────────────────────────────────────

def _arc_points(seg: ArcSeg, tol: float = 0.01) -> List[Point]:
    r = max(seg.r, 1e-6)
    # normalize span
    a0, a1 = seg.a0, seg.a1
    if seg.cw:
        # travel CW from a0 to a1
        while a1 > a0:
            a1 -= 2 * PI
        span = a0 - a1
    else:
        while a1 < a0:
            a1 += 2 * PI
        span = a1 - a0
    n = max(4, int(math.ceil(abs(span) * r / max(tol, 1e-4))))
    pts = []
    for i in range(n + 1):
        t = i / n
        if seg.cw:
            a = a0 - t * span
        else:
            a = a0 + t * span
        pts.append((seg.cx + r * math.cos(a), seg.cy + r * math.sin(a)))
    return pts


def discretize(path: Path, tol: float = 0.008) -> np.ndarray:
    """Path → Nx2 polyline in world units."""
    pts: List[Point] = []
    for seg in path.segs:
        if isinstance(seg, LineSeg):
            if not pts:
                pts.append((seg.x0, seg.y0))
            pts.append((seg.x1, seg.y1))
        else:
            ap = _arc_points(seg, tol=tol)
            if pts and ap:
                pts.extend(ap[1:])
            else:
                pts.extend(ap)
    if not pts:
        return np.zeros((0, 2), dtype=np.float64)
    return np.asarray(pts, dtype=np.float64)


def offset_polyline(poly: np.ndarray, radius: float, closed: bool = True) -> np.ndarray:
    """Simple vertex offset along averaged edge normals (tool-radius compensation).

    Not a full CAM kernel — good enough for illustration outlines.
    Positive radius = outward for CCW closed polys (image y-down: reverse).
    """
    if len(poly) < 2 or abs(radius) < 1e-9:
        return poly.copy()
    pts = poly
    if closed and len(pts) > 2:
        # drop duplicate last==first if present
        if np.allclose(pts[0], pts[-1]):
            pts = pts[:-1]
    n = len(pts)
    out = np.zeros_like(pts)
    for i in range(n):
        prev = pts[(i - 1) % n] if closed else pts[max(i - 1, 0)]
        nxt = pts[(i + 1) % n] if closed else pts[min(i + 1, n - 1)]
        cur = pts[i]
        e0 = cur - prev
        e1 = nxt - cur
        for e in (e0, e1):
            L = np.linalg.norm(e)
            if L > 1e-9:
                e /= L
        # normals (image y-down: left normal of dir (dx,dy) is (dy, -dx) for outward of CCW)
        n0 = np.array([e0[1], -e0[0]]) if np.linalg.norm(e0) > 1e-9 else np.array([0.0, -1.0])
        n1 = np.array([e1[1], -e1[0]]) if np.linalg.norm(e1) > 1e-9 else n0
        nrm = n0 + n1
        ln = np.linalg.norm(nrm)
        if ln < 1e-9:
            nrm = n0
            ln = np.linalg.norm(nrm) + 1e-9
        nrm /= ln
        out[i] = cur + nrm * radius
    if closed:
        out = np.vstack([out, out[0]])
    return out


def multi_pass_offsets(
    poly: np.ndarray, tool_r: float, passes: int = 3, closed: bool = True
) -> List[np.ndarray]:
    """Multiple offset passes (like roughing → finish)."""
    passes = max(1, int(passes))
    out = []
    for i in range(passes):
        # outer to inner or single outline
        r = tool_r * (1.0 - i / max(passes, 1) * 0.65)
        out.append(offset_polyline(poly, r, closed=closed))
    return out


# ── Rasterization into image mesh ────────────────────────────────────────

def smoothstep(a, b, x):
    denom = np.maximum(np.asarray(b) - np.asarray(a), 1e-9)
    t = np.clip((np.asarray(x) - np.asarray(a)) / denom, 0, 1)
    return t * t * (3.0 - 2.0 * t)


def _dist_to_segments(xx, yy, poly: np.ndarray) -> np.ndarray:
    """Min distance from each pixel to polyline segments."""
    h, w = xx.shape
    best = np.full((h, w), 1e9, dtype=np.float64)
    if len(poly) < 2:
        return best
    for i in range(len(poly) - 1):
        x0, y0 = poly[i]
        x1, y1 = poly[i + 1]
        dx, dy = x1 - x0, y1 - y0
        L2 = dx * dx + dy * dy
        if L2 < 1e-14:
            d = np.hypot(xx - x0, yy - y0)
        else:
            t = np.clip(((xx - x0) * dx + (yy - y0) * dy) / L2, 0, 1)
            px = x0 + t * dx
            py = y0 + t * dy
            d = np.hypot(xx - px, yy - py)
        best = np.minimum(best, d)
    return best


def raster_stroke(
    xx, yy, path: Path, width: float = 0.01, aa: float = 0.002
) -> np.ndarray:
    """Coverage mask [0,1] for stroked path."""
    poly = discretize(path, tol=max(aa * 2, 0.004))
    if len(poly) < 2:
        return np.zeros(xx.shape, dtype=np.float32)
    d = _dist_to_segments(xx, yy, poly)
    half = width * 0.5
    return (1.0 - smoothstep(half - aa, half + aa, d)).astype(np.float32)


def raster_fill(xx, yy, path: Path, aa: float = 0.002) -> np.ndarray:
    """Even-odd style fill via matplotlib-free winding using scan approx.

    Uses point-in-polygon on closed discretized contour + edge AA.
    """
    poly = discretize(path, tol=max(aa * 2, 0.005))
    if len(poly) < 3:
        return np.zeros(xx.shape, dtype=np.float32)
    if not np.allclose(poly[0], poly[-1]):
        poly = np.vstack([poly, poly[0]])
    # Ray cast PIP vectorized (horizontal ray)
    x = xx
    y = yy
    inside = np.zeros(xx.shape, dtype=bool)
    for i in range(len(poly) - 1):
        x0, y0 = poly[i]
        x1, y1 = poly[i + 1]
        # edge crosses horizontal ray
        cond = ((y0 > y) != (y1 > y)) & (
            x < (x1 - x0) * (y - y0) / (y1 - y0 + 1e-15) + x0
        )
        inside ^= cond
    cov = inside.astype(np.float32)
    # edge AA via distance
    d = _dist_to_segments(xx, yy, poly)
    edge = 1.0 - smoothstep(0, aa * 2, d)
    # soft boundary
    cov = np.maximum(cov * (1.0 - 0.0), np.minimum(1.0, cov + edge * 0.5))
    # cleaner: inside full, edge blend
    cov = np.where(inside, np.maximum(cov, 1.0 - smoothstep(0, aa * 2.5, d)), edge * 0.0)
    cov = inside.astype(np.float32)
    # soft exterior falloff into edge
    cov = np.clip(cov + (1.0 - smoothstep(0, aa * 2, d)) * (1 - cov) * 0.0, 0, 1)
    # distance field soft fill edge
    cov = np.clip(
        inside.astype(np.float32) * 1.0
        + (~inside).astype(np.float32) * (1.0 - smoothstep(0, aa * 2.5, d)) * 0,
        0,
        1,
    )
    # final: soft edge on boundary
    soft = 1.0 - smoothstep(-aa * 2, aa * 2, 
                            np.where(inside, -d, d))  # signed-ish
    # simpler reliable approach:
    d_signed = np.where(inside, -d, d)
    soft = 1.0 - smoothstep(0, aa * 2.5, d_signed)  # wrong for inside
    # USE: inside=1, boundary blend
    fill = inside.astype(np.float32)
    border = (1.0 - smoothstep(0, aa * 2.5, d)).astype(np.float32)
    return np.clip(np.maximum(fill, border * fill), 0, 1).astype(np.float32)


def raster_fill_fast(xx, yy, path: Path, aa: float = 0.0025) -> np.ndarray:
    """Reliable closed-path fill with edge anti-alias."""
    poly = discretize(path, tol=max(aa * 2, 0.005))
    if len(poly) < 3:
        return np.zeros(xx.shape, dtype=np.float32)
    if not np.allclose(poly[0], poly[-1]):
        poly = np.vstack([poly, poly[0]])
    x, y = xx, yy
    inside = np.zeros(xx.shape, dtype=bool)
    for i in range(len(poly) - 1):
        x0, y0 = float(poly[i, 0]), float(poly[i, 1])
        x1, y1 = float(poly[i + 1, 0]), float(poly[i + 1, 1])
        cond = ((y0 > y) != (y1 > y)) & (
            x < (x1 - x0) * (y - y0) / ((y1 - y0) + 1e-15) + x0
        )
        np.logical_xor(inside, cond, out=inside)
    d = _dist_to_segments(xx, yy, poly)
    # smooth: 1 inside, 0 outside, blend near edge
    # coverage ≈ 1 - smoothstep(0, aa, signed_distance) with sd = -d inside
    sd = np.where(inside, -d, d)
    return (1.0 - smoothstep(0.0, aa * 2.5, sd)).astype(np.float32)


def pocket_passes(
    path: Path, tool_r: float = 0.012, passes: int = 3
) -> List[Tuple[Path, float]]:
    """Roughing → finish offset contours for closed paths (CAM multi-pass).

    Returns list of (path, coverage_scale) from outer rough to inner finish.
    """
    if not path.closed or path.empty():
        return [(path, 1.0)]
    poly = discretize(path, tol=0.006)
    if len(poly) < 4:
        return [(path, 1.0)]
    passes = max(1, min(6, int(passes)))
    out: List[Tuple[Path, float]] = []
    for i in range(passes):
        # outer first (larger offset), then step inward
        t = i / max(passes - 1, 1)
        r = tool_r * (1.0 - t * 0.85)
        op = offset_polyline(poly, r if i == 0 else -abs(r) * 0.5 * t, closed=True)
        if len(op) < 3:
            continue
        pts = [tuple(p) for p in op]
        pth = polyline(pts, closed=True)
        pth.meta = dict(path.meta)
        pth.meta["pass"] = i
        pth.meta["pass_of"] = passes
        # inner passes slightly darker (depth of cut shading)
        scale = 1.0 - 0.08 * t
        out.append((pth, scale))
    if not out:
        out.append((path, 1.0))
    return out


def paint_path(
    img: np.ndarray,
    xx,
    yy,
    path: Path,
    color: Tuple[float, float, float],
    stroke_width: Optional[float] = None,
    aa: float = 0.002,
    sun_pos: Tuple[float, float] = (0.72, 0.20),
    use_materials: bool = True,
    pocket: bool = True,
    depth_map: Optional[np.ndarray] = None,
    depth_z: Optional[float] = None,
) -> np.ndarray:
    """Paint a path into img (float HxWx3) with fill and/or stroke.

    pocket=True applies multi-pass offset fills for closed contours.
    use_materials=True shades with materials.shade_albedo when available.
    If depth_map + depth_z provided, writes Z under coverage (true DOF later).
    Returns combined coverage mask for the paint.
    """
    c = np.asarray(color, dtype=np.float32)
    entity = str(path.meta.get("entity", ""))
    role = str(path.meta.get("role", ""))
    cov_acc = np.zeros(xx.shape, dtype=np.float32)

    def _write_z(m):
        if depth_map is not None and depth_z is not None:
            try:
                import depth_buffer as _db
                _db.write_depth(depth_map, m, float(depth_z))
            except Exception:
                pass

    def _blend_flat(m, col=None, scale=1.0):
        m = np.asarray(m, dtype=np.float32) * float(scale)
        nonlocal cov_acc
        cov_acc = np.maximum(cov_acc, m)
        col = np.asarray(col if col is not None else c, dtype=np.float32)
        for k in range(3):
            img[:, :, k] = img[:, :, k] * (1.0 - m) + col[k] * m
        _write_z(m)

    def _blend_mat(m, col=None, scale=1.0):
        m = np.asarray(m, dtype=np.float32) * float(scale)
        nonlocal cov_acc
        cov_acc = np.maximum(cov_acc, m)
        col = tuple(float(x) for x in (col if col is not None else c))
        if use_materials:
            try:
                import materials as _mat
                _mat.blend_shaded(
                    img, m, col, xx, yy, sun_pos=sun_pos, entity=entity, role=role
                )
                _write_z(m)
                return
            except Exception:
                pass
        _blend_flat(m, col)

    stroke_only = bool(path.meta.get("stroke_only"))
    width = stroke_width if stroke_width is not None else float(path.meta.get("width", 0.012))
    if stroke_only or not path.closed:
        _blend_flat(raster_stroke(xx, yy, path, width=width, aa=aa))
    else:
        if pocket and path.meta.get("layer") not in ("door", "window"):
            for pth, scale in pocket_passes(path, tool_r=max(width, 0.01), passes=3):
                fill = raster_fill_fast(xx, yy, pth, aa=aa)
                _blend_mat(fill, scale=scale)
        else:
            _blend_mat(raster_fill_fast(xx, yy, path, aa=aa))
        # finish pass outline (final contour cut)
        sw = max(width * 0.35, aa * 2)
        op = polyline([tuple(p) for p in discretize(path)], closed=True)
        _blend_flat(raster_stroke(xx, yy, op, width=sw, aa=aa) * 0.25)
    return cov_acc


def paths_for_primitive(prim: dict[str, Any], seed: int = 0) -> List[Path]:
    """Map a scene-graph primitive to CNC paths (entity construction language)."""
    role = prim.get("role")
    entity = prim.get("entity", "")
    paths: List[Path] = []

    if role == "house":
        cx, base, w, h = prim["cx"], prim["base"], prim["w"], prim["h"]
        paths.append(house_contour(cx, base, w, h))
        # door as inner pocket (multi-pass smaller rect)
        dw, dh = w * 0.18, h * 0.45
        door = rect(cx, base - dh * 0.5, dw, dh)
        door.meta["layer"] = "door"
        paths.append(door)
        # window
        wx = cx + w * 0.28
        wy = base - h * 0.55
        win = rect(wx, wy, w * 0.16, w * 0.14)
        win.meta["layer"] = "window"
        paths.append(win)
    elif role == "building":
        paths.append(building_contour(prim["cx"], prim["base"], prim["w"], prim["h"]))
    elif role == "triangle":
        paths.append(
            mountain_contour(prim["cx"], prim["base"], prim["h"], prim["hw"])
        )
    elif role == "tree":
        paths.extend(tree_canopy_paths(prim["x"], prim["base"], prim["r"], seed=seed))
    elif role == "bush":
        paths.extend(
            tree_canopy_paths(prim["x"], prim["base"], prim["r"] * 0.85, seed=seed + 9)
        )
    elif role == "person":
        paths.append(person_path(prim["x"], prim["base"], prim["h"]))
        hx, hy, hr = paths[0].meta["head"]
        paths.append(circle(hx, hy, hr))
    elif role == "fence":
        paths.append(fence_path(prim["x0"], prim["x1"], prim["base"], prim["h"]))
    elif role == "boat":
        bp = boat_path(prim["x"], prim["y"], prim["w"], prim["h"])
        paths.append(bp)
        if "cabin" in bp.meta:
            paths.append(bp.meta["cabin"])
    elif role == "flower":
        paths.extend(flower_paths(prim["x"], prim["base"], prim["r"]))
    elif role == "bridge":
        paths.extend(bridge_paths(prim["cx"], prim["base"], prim["w"], prim["h"]))
    elif role == "disc":
        paths.append(circle(prim["x"], prim["y"], prim["r"]))
    elif role == "disc_top":
        paths.append(circle(prim["x"], prim["y"], prim["r"]))
    elif role == "star_top":
        # star as multi-pass polyline
        cx, cy, r = prim["x"], prim["y"], prim.get("r", 0.03)
        pts = []
        for i in range(10):
            a = -PI / 2 + i * PI / 5
            rr = r if i % 2 == 0 else r * 0.4
            pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
        paths.append(polyline(pts, closed=True))
    elif role == "cloud_top":
        x, y, r = prim["x"], prim["y"], prim.get("r", 0.07)
        for dx, dy, rr in (
            (-1.1 * r, 0, 0.85 * r),
            (0, -0.15 * r, 1.05 * r),
            (1.1 * r, 0, 0.85 * r),
        ):
            paths.append(circle(x + dx, y + dy, rr))
    else:
        return []

    for p in paths:
        p.meta.setdefault("entity", entity)
        p.meta.setdefault("role", role)
    return paths


def path_provenance(paths: List[Path]) -> List[str]:
    """Human-readable g-like ops for API/debug (not executable G-code)."""
    ops = []
    for p in paths:
        for seg in p.segs:
            if isinstance(seg, LineSeg):
                ops.append(
                    f"G1 X{seg.x1:.3f} Y{seg.y1:.3f}"
                )
            else:
                code = "G2" if seg.cw else "G3"
                ops.append(
                    f"{code} I{seg.cx:.3f} J{seg.cy:.3f} R{seg.r:.3f}"
                )
        if p.closed:
            ops.append("CLOSE")
    return ops[:64]  # bound size


def demo():
    from PIL import Image

    h = w = 512
    yy, xx = np.meshgrid(
        np.linspace(0, 1, h), np.linspace(0, 1, w), indexing="ij"
    )
    img = np.ones((h, w, 3), dtype=np.float32) * np.array([0.55, 0.72, 0.90])
    # ground
    g = (yy > 0.66).astype(np.float32)
    for k, c in enumerate([0.32, 0.55, 0.28]):
        img[:, :, k] = img[:, :, k] * (1 - g) + c * g

    prims = [
        {"role": "house", "entity": "house", "cx": 0.55, "base": 0.66, "w": 0.16, "h": 0.14, "color": (0.7, 0.4, 0.32)},
        {"role": "tree", "entity": "tree", "x": 0.28, "base": 0.66, "r": 0.10, "color": (0.2, 0.5, 0.22)},
        {"role": "person", "entity": "person", "x": 0.72, "base": 0.66, "h": 0.11, "color": (0.2, 0.2, 0.28)},
        {"role": "fence", "entity": "fence", "x0": 0.35, "x1": 0.48, "base": 0.66, "h": 0.06, "color": (0.5, 0.38, 0.22)},
    ]
    all_ops = []
    for prim in prims:
        ps = paths_for_primitive(prim, seed=1)
        all_ops.extend(path_provenance(ps))
        col = prim["color"]
        for pth in ps:
            layer = pth.meta.get("layer")
            if layer == "door":
                paint_path(img, xx, yy, pth, (0.35, 0.22, 0.14), aa=1.5 / h)
            elif layer == "window":
                paint_path(img, xx, yy, pth, (0.55, 0.75, 0.9), aa=1.5 / h)
            else:
                paint_path(img, xx, yy, pth, col, aa=1.5 / h)

    out = "/tmp/cnc_paths_demo.png"
    Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(out)
    print("wrote", out)
    print("sample ops:", all_ops[:12])


if __name__ == "__main__":
    demo()
