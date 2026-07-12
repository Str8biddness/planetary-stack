#!/usr/bin/env python3
"""
Extrude / print-lite math for SI form — stack or pull 2D contour into height.

Additive metaphor (3D printer layers) without full slicer:
  - rectangular prism from (cx, base, w, h_depth, height)
  - optional layered horizontal bands (print strata)

Honest ceiling: crates, walls, blocks, stepped hills — not freeform organics.
"""
from __future__ import annotations

import math
from typing import Any, List, Optional, Sequence, Tuple

import numpy as np

Point = Tuple[float, float]


def rect_footprint(cx: float, base: float, w: float, d: float) -> List[Point]:
    """Bottom face rectangle in ground plane (image x, y≈base). d unused for 2.5D."""
    hw = w * 0.5
    return [
        (cx - hw, base),
        (cx + hw, base),
        (cx + hw, base),
        (cx - hw, base),
    ]


def paint_extrude(
    img: np.ndarray,
    xx: np.ndarray,
    yy: np.ndarray,
    *,
    cx: float,
    base: float,
    width: float,
    height: float,
    color: Tuple[float, float, float],
    depth_frac: float = 0.35,
    layers: int = 1,
    aa: float = 0.004,
    sun_pos: Optional[Tuple[float, float]] = None,
    depth_map: Optional[np.ndarray] = None,
    depth_z: Optional[float] = None,
) -> np.ndarray:
    """Paint a simple extruded box (front face + top + side) for volume cue."""
    h, w = img.shape[:2]
    cov = np.zeros((h, w), dtype=np.float32)
    hw = width * 0.5
    ht = max(height, 1e-4)
    # isometric-ish skew for side/top
    skew = width * 0.22 * float(np.clip(depth_frac, 0.1, 1.0))
    y_top = base - ht

    col = np.asarray(color, dtype=np.float32)
    if col.max() > 1.5:
        col = col / 255.0
    # face colors
    front = col * 0.92
    side = col * 0.72
    top = col * 1.08
    if sun_pos is not None and sun_pos[0] > cx:
        side, front = front * 0.85, side * 1.05

    def _fill_poly(pts: Sequence[Point], rgb: np.ndarray, zwrite: Optional[float] = None):
        nonlocal cov
        arr = np.asarray(pts, dtype=np.float32)
        xs, ys = arr[:, 0], arr[:, 1]
        pad = max(aa * 4, 0.008)
        x0 = int(max(0, math.floor((xs.min() - pad) * (w - 1))))
        x1 = int(min(w, math.ceil((xs.max() + pad) * (w - 1)) + 1))
        y0 = int(max(0, math.floor((ys.min() - pad) * (h - 1))))
        y1 = int(min(h, math.ceil((ys.max() + pad) * (h - 1)) + 1))
        if x1 <= x0 or y1 <= y0:
            return
        # PIL polygon on crop
        from PIL import Image, ImageDraw

        ch, cw = y1 - y0, x1 - x0
        im = Image.new("L", (cw, ch), 0)
        dr = ImageDraw.Draw(im)
        local = [
            (
                (float(px) - x0 / max(w - 1, 1)) * (w - 1) - x0,
                (float(py) - y0 / max(h - 1, 1)) * (h - 1) - y0,
            )
            for px, py in pts
        ]
        # better: map world→pixel
        local = []
        for px, py in pts:
            local.append((
                px * (w - 1) - x0,
                py * (h - 1) - y0,
            ))
        dr.polygon(local, fill=255)
        m = np.asarray(im, dtype=np.float32) / 255.0
        if aa > 0:
            try:
                from PIL import ImageFilter
                im2 = im.filter(ImageFilter.GaussianBlur(radius=max(0.4, aa * min(h, w) * 0.5)))
                m = np.asarray(im2, dtype=np.float32) / 255.0
            except Exception:
                pass
        crop = img[y0:y1, x0:x1]
        m3 = m[..., None]
        crop[:] = crop * (1.0 - m3) + rgb.reshape(1, 1, 3) * m3
        cov[y0:y1, x0:x1] = np.maximum(cov[y0:y1, x0:x1], m)
        if depth_map is not None and zwrite is not None:
            try:
                import depth_buffer as _db
                _db.write_depth(depth_map[y0:y1, x0:x1], m, float(zwrite))
            except Exception:
                pass

    # Front face
    _fill_poly(
        [
            (cx - hw, base),
            (cx + hw, base),
            (cx + hw, y_top),
            (cx - hw, y_top),
        ],
        front,
        depth_z,
    )
    # Top face (parallelogram)
    _fill_poly(
        [
            (cx - hw, y_top),
            (cx + hw, y_top),
            (cx + hw + skew, y_top - skew * 0.35),
            (cx - hw + skew, y_top - skew * 0.35),
        ],
        np.clip(top, 0, 1),
        (depth_z - 0.02) if depth_z is not None else None,
    )
    # Right side
    _fill_poly(
        [
            (cx + hw, base),
            (cx + hw + skew, base - skew * 0.35),
            (cx + hw + skew, y_top - skew * 0.35),
            (cx + hw, y_top),
        ],
        side,
        (depth_z + 0.02) if depth_z is not None else None,
    )

    # Print strata lines
    nlay = max(1, min(12, int(layers)))
    if nlay > 1:
        for i in range(1, nlay):
            t = i / nlay
            y = base - ht * t
            x0w, x1w = cx - hw, cx + hw
            # thin darker band
            band = (np.abs(yy - y) < aa * 1.2) & (xx >= x0w) & (xx <= x1w)
            img[band] *= 0.88
            cov[band] = np.maximum(cov[band], 0.3)

    return cov


def extrude_primitive(
    entity: str,
    *,
    cx: float = 0.5,
    base: float = 0.66,
    width: float = 0.12,
    height: float = 0.16,
    color: Tuple[float, float, float] = (0.5, 0.48, 0.45),
    layers: int = 1,
) -> dict[str, Any]:
    return {
        "entity": entity,
        "role": "extrude",
        "color": color,
        "cx": float(cx),
        "base": float(base),
        "w": float(width),
        "h": float(height),
        "layers": int(layers),
        "construction": "extrude",
        "machine": "extrude",
    }


def demo():
    from PIL import Image

    h, w = 256, 320
    img = np.ones((h, w, 3), dtype=np.float32) * np.array([0.55, 0.7, 0.9])
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    yy /= h - 1
    xx /= w - 1
    img[yy > 0.66] = (0.35, 0.55, 0.3)
    paint_extrude(
        img, xx, yy, cx=0.4, base=0.66, width=0.14, height=0.2,
        color=(0.55, 0.5, 0.45), layers=5,
    )
    paint_extrude(
        img, xx, yy, cx=0.7, base=0.66, width=0.1, height=0.12,
        color=(0.4, 0.55, 0.7), layers=1,
    )
    path = "/tmp/extrude_demo.png"
    Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(path)
    print("wrote", path)


if __name__ == "__main__":
    demo()
