#!/usr/bin/env python3
"""
World camera — multi-view orbit + time axis on the same SI scene graph.
======================================================================

Real degrees of freedom (not fake high-D):
  - yaw   : horizontal camera orbit → parallax by depth Z (near moves more)
  - pitch : vertical camera tilt → vertical parallax + horizon shift
  - time  : sun/moon path + day/night style hints (0=dawn … 0.5=noon … 1=night)

Same scene graph → many projections. That's the bridge from single images to
virtual-world multi-view consistency (SI construction, not diffusion).

Run: python packages/reasoning/world_camera.py
"""
from __future__ import annotations

import copy
import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

try:
    import depth_buffer as _db
except Exception:  # pragma: no cover
    _db = None


def _shift_keys(p: dict, dx: float = 0.0, dy: float = 0.0) -> None:
    for k in ("x", "cx"):
        if k in p and isinstance(p[k], (int, float)):
            p[k] = float(np.clip(float(p[k]) + dx, 0.02, 0.98))
    if "x0" in p and "x1" in p:
        p["x0"] = float(np.clip(float(p["x0"]) + dx, 0.0, 0.95))
        p["x1"] = float(np.clip(float(p["x1"]) + dx, 0.05, 1.0))
    if abs(dy) > 1e-9:
        for k in ("y", "base", "y0"):
            if k in p and isinstance(p[k], (int, float)):
                lo, hi = (0.05, 0.55) if k == "y" else (0.35, 0.92)
                p[k] = float(np.clip(float(p[k]) + dy, lo, hi))


def sun_for_time(time_of_day: float) -> Tuple[float, float, str]:
    """Map t∈[0,1] → (sun_x, sun_y, paint_style_hint).

    0.0 dawn, 0.35 morning, 0.5 noon, 0.75 dusk, 0.9–1.0 night (moon).
    """
    t = float(np.clip(time_of_day, 0.0, 1.0))
    if t >= 0.88:
        # night moon
        return 0.78, 0.16, "night"
    # arc from left-low → top → right-low
    # use half-sine elevation
    phase = t / 0.88  # stretch day into [0,1)
    sx = 0.12 + 0.76 * phase
    # y small = high in sky; noon highest
    elev = math.sin(math.pi * phase)  # 0..1..0
    sy = 0.38 - 0.22 * elev  # ~0.38 dawn/dusk, ~0.16 noon
    if t < 0.12 or t > 0.78:
        style = "soft"  # golden hour still soft paint; ISP cinema often used
    else:
        style = "soft"
    return float(sx), float(sy), style


def look_for_time(time_of_day: float, default_look: str = "photo") -> str:
    t = float(np.clip(time_of_day, 0.0, 1.0))
    if t >= 0.88:
        return "cinema"
    if t < 0.15 or t > 0.75:
        return "cinema"
    if 0.4 <= t <= 0.6:
        return default_look if default_look != "raw" else "photo"
    return default_look if default_look != "raw" else "photo"


def project_view(
    doc: List[Dict[str, Any]],
    horizon: float = 0.66,
    yaw_deg: float = 0.0,
    pitch_deg: float = 0.0,
    time_of_day: Optional[float] = None,
    parallax: float = 0.14,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Project scene graph under camera yaw/pitch + optional time-of-day sun.

    Returns (new_doc, camera_meta). Horizon may shift with pitch.
    """
    yaw_deg = float(np.clip(yaw_deg, -60.0, 60.0))
    pitch_deg = float(np.clip(pitch_deg, -35.0, 35.0))
    yaw = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)
    # horizontal / vertical pan factors
    pan_base = parallax * math.sin(yaw)
    # pitch>0 looks up → horizon drops (higher y), near objects rise less than far
    pitch_base = parallax * 0.85 * math.sin(pitch)
    horizon_out = float(np.clip(horizon + 0.10 * math.sin(pitch), 0.50, 0.80))

    out: List[Dict[str, Any]] = []
    for prim in doc:
        p = copy.deepcopy(prim)
        if _db is not None:
            z = _db.depth_for_primitive(p, horizon=horizon)
        else:
            z = 0.5
        p["depth_z"] = z
        # nearer (small z) shifts more; camera yaw>0 → world appears to slide left for near objs
        dx = -pan_base * (1.0 - z)
        # pitch: near objects move opposite to far; look up → near drops slightly, far rises
        dy = pitch_base * (0.35 - z)  # near z~0.3 → negative dy when pitch>0
        role = p.get("role")
        if role not in ("bg",):  # sky full-frame
            if role == "ground":
                if "y0" in p:
                    p["y0"] = horizon_out
            else:
                _shift_keys(p, dx, dy)
                # keep ground-anchored bases near new horizon
                if role in (
                    "house", "tree", "person", "building", "boat", "fence",
                    "bush", "flower", "bridge", "disc", "triangle",
                ) and "base" in p:
                    # soft pull base toward horizon_out for ground objects
                    if role != "triangle":
                        p["base"] = float(
                            np.clip(0.65 * float(p["base"]) + 0.35 * horizon_out, 0.4, 0.92)
                        )
        # paths are geometric in absolute coords — invalidate cached paths so render rebuilds
        if "paths" in p:
            p.pop("paths", None)
            p.pop("path_ops", None)
        out.append(p)

    cam: Dict[str, Any] = {
        "yaw_deg": yaw_deg,
        "pitch_deg": pitch_deg,
        "parallax": parallax,
        "horizon": horizon_out,
        "axis": ["x", "y", "z", "yaw", "pitch"],
    }

    if time_of_day is not None:
        t = float(np.clip(time_of_day, 0.0, 1.0))
        sx, sy, style_hint = sun_for_time(t)
        cam["time_of_day"] = t
        cam["sun_pos"] = (sx, sy)
        cam["style_hint"] = style_hint
        cam["look_hint"] = look_for_time(t)
        cam["axis"] = ["x", "y", "z", "yaw", "pitch", "time"]
        # inject / move disc_top sun or moon
        has_sun = False
        for p in out:
            if p.get("role") == "disc_top":
                p["x"], p["y"] = sx, sy
                if t >= 0.88:
                    p["entity"] = "moon"
                    p["color"] = (0.90, 0.90, 0.82)
                else:
                    p["entity"] = "sun"
                    p["color"] = (1.0, 0.86, 0.30)
                has_sun = True
                p.pop("paths", None)
        if not has_sun:
            ent = "moon" if t >= 0.88 else "sun"
            col = (0.90, 0.90, 0.82) if ent == "moon" else (1.0, 0.86, 0.30)
            out.append({
                "entity": ent,
                "role": "disc_top",
                "color": col,
                "x": sx,
                "y": sy,
                "r": 0.07 if ent == "sun" else 0.055,
            })
        # night: ensure dark bg entity present
        if t >= 0.88 and not any(p.get("role") == "bg" for p in out):
            out.insert(0, {
                "entity": "night",
                "role": "bg",
                "color": (0.07, 0.09, 0.20),
                "x": 0, "y": 0, "w": 1, "h": 1,
            })
        elif t >= 0.88:
            for p in out:
                if p.get("role") == "bg":
                    p["entity"] = "night"
                    p["color"] = (0.07, 0.09, 0.20)

    cam["horizon"] = horizon_out
    return out, cam


def pitch_schedule(n: int = 3, span_deg: float = 20.0) -> List[float]:
    """Even pitch samples centered at 0."""
    n = max(1, min(12, int(n)))
    span = float(np.clip(span_deg, 0.0, 50.0))
    if n == 1:
        return [0.0]
    return [float(-span / 2 + span * i / (n - 1)) for i in range(n)]


def yaw_schedule(n: int = 3, span_deg: float = 30.0) -> List[float]:
    """Even yaw samples centered at 0, e.g. n=3 span=30 → [-15, 0, 15]."""
    n = max(1, min(12, int(n)))
    span = float(np.clip(span_deg, 0.0, 90.0))
    if n == 1:
        return [0.0]
    return [float(-span / 2 + span * i / (n - 1)) for i in range(n)]


def time_schedule(n: int = 4, t0: float = 0.1, t1: float = 0.92) -> List[float]:
    """Even time-of-day samples from t0..t1."""
    n = max(1, min(12, int(n)))
    t0, t1 = float(t0), float(t1)
    if n == 1:
        return [0.5 * (t0 + t1)]
    return [float(t0 + (t1 - t0) * i / (n - 1)) for i in range(n)]


def demo():
    doc = [
        {"entity": "sky", "role": "bg", "color": (0.4, 0.6, 0.85)},
        {"entity": "grass", "role": "ground", "color": (0.3, 0.5, 0.3), "y0": 0.66},
        {"entity": "house", "role": "house", "color": (0.7, 0.4, 0.3), "cx": 0.55, "base": 0.66, "w": 0.14, "h": 0.12},
        {"entity": "tree", "role": "tree", "color": (0.2, 0.5, 0.2), "x": 0.28, "base": 0.66, "r": 0.09},
        {"entity": "sun", "role": "disc_top", "color": (1, 0.86, 0.3), "x": 0.72, "y": 0.2, "r": 0.07},
    ]
    d1, m1 = project_view(doc, yaw_deg=20)
    d2, m2 = project_view(doc, yaw_deg=0, time_of_day=0.95)
    print("yaw meta", m1)
    print("house cx shift", doc[2]["cx"], "->", d1[2].get("cx"))
    print("night sun", m2.get("sun_pos"), [p["entity"] for p in d2 if p.get("role") == "disc_top"])


if __name__ == "__main__":
    demo()
