#!/usr/bin/env python3
"""
SI material pack — surface response without neural textures.
===========================================================

Lightweight BRDF-ish shading for CNC/path fills:
  - Lambertian diffuse
  - Schlick Fresnel (water / glaze)
  - Simple roughness → soft specular lobe
  - Metalness darkens diffuse, tints specular

Honest: procedural surface response on geometric form — not PBR maps from
photogrammetry, not diffusion textures.

Run: python packages/reasoning/materials.py
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np

# entity/role → material preset
MATERIAL_PRESETS: Dict[str, Dict[str, float]] = {
    # albedo is multiplied later by prim color; these are response params
    "default": {"roughness": 0.75, "metalness": 0.0, "specular": 0.12, "fresnel": 0.04},
    "grass": {"roughness": 0.92, "metalness": 0.0, "specular": 0.05, "fresnel": 0.02},
    "ground": {"roughness": 0.90, "metalness": 0.0, "specular": 0.06, "fresnel": 0.03},
    "sand": {"roughness": 0.88, "metalness": 0.0, "specular": 0.08, "fresnel": 0.03},
    "snow": {"roughness": 0.70, "metalness": 0.0, "specular": 0.25, "fresnel": 0.08},
    "sea": {"roughness": 0.18, "metalness": 0.0, "specular": 0.55, "fresnel": 0.22},
    "ocean": {"roughness": 0.18, "metalness": 0.0, "specular": 0.55, "fresnel": 0.22},
    "water": {"roughness": 0.20, "metalness": 0.0, "specular": 0.50, "fresnel": 0.20},
    "river": {"roughness": 0.22, "metalness": 0.0, "specular": 0.48, "fresnel": 0.18},
    "lake": {"roughness": 0.20, "metalness": 0.0, "specular": 0.52, "fresnel": 0.20},
    "pond": {"roughness": 0.25, "metalness": 0.0, "specular": 0.45, "fresnel": 0.16},
    "house": {"roughness": 0.70, "metalness": 0.0, "specular": 0.10, "fresnel": 0.04},
    "barn": {"roughness": 0.78, "metalness": 0.05, "specular": 0.12, "fresnel": 0.05},
    "cabin": {"roughness": 0.82, "metalness": 0.0, "specular": 0.08, "fresnel": 0.03},
    "building": {"roughness": 0.55, "metalness": 0.15, "specular": 0.28, "fresnel": 0.08},
    "tower": {"roughness": 0.50, "metalness": 0.20, "specular": 0.30, "fresnel": 0.09},
    "castle": {"roughness": 0.85, "metalness": 0.0, "specular": 0.08, "fresnel": 0.04},
    "tree": {"roughness": 0.88, "metalness": 0.0, "specular": 0.06, "fresnel": 0.03},
    "forest": {"roughness": 0.90, "metalness": 0.0, "specular": 0.05, "fresnel": 0.03},
    "bush": {"roughness": 0.90, "metalness": 0.0, "specular": 0.05, "fresnel": 0.03},
    "mountain": {"roughness": 0.80, "metalness": 0.0, "specular": 0.10, "fresnel": 0.04},
    "hill": {"roughness": 0.85, "metalness": 0.0, "specular": 0.08, "fresnel": 0.03},
    "rock": {"roughness": 0.82, "metalness": 0.0, "specular": 0.12, "fresnel": 0.05},
    "stone": {"roughness": 0.80, "metalness": 0.0, "specular": 0.12, "fresnel": 0.05},
    "boat": {"roughness": 0.55, "metalness": 0.25, "specular": 0.35, "fresnel": 0.10},
    "ship": {"roughness": 0.50, "metalness": 0.35, "specular": 0.40, "fresnel": 0.12},
    "car": {"roughness": 0.35, "metalness": 0.55, "specular": 0.55, "fresnel": 0.15},
    "bridge": {"roughness": 0.65, "metalness": 0.20, "specular": 0.25, "fresnel": 0.08},
    "fence": {"roughness": 0.75, "metalness": 0.0, "specular": 0.10, "fresnel": 0.04},
    "apple": {"roughness": 0.40, "metalness": 0.0, "specular": 0.35, "fresnel": 0.10},
    "flower": {"roughness": 0.55, "metalness": 0.0, "specular": 0.20, "fresnel": 0.06},
    "person": {"roughness": 0.70, "metalness": 0.0, "specular": 0.12, "fresnel": 0.05},
    "road": {"roughness": 0.85, "metalness": 0.0, "specular": 0.08, "fresnel": 0.03},
    "path": {"roughness": 0.88, "metalness": 0.0, "specular": 0.06, "fresnel": 0.03},
    "sun": {"roughness": 0.1, "metalness": 0.0, "specular": 0.0, "fresnel": 0.0, "emissive": 1.0},
    "moon": {"roughness": 0.85, "metalness": 0.0, "specular": 0.15, "fresnel": 0.05},
    "star": {"roughness": 0.2, "metalness": 0.0, "specular": 0.0, "fresnel": 0.0, "emissive": 0.8},
    "lamp": {"roughness": 0.3, "metalness": 0.4, "specular": 0.4, "fresnel": 0.1, "emissive": 0.6},
    "water_mat": {"roughness": 0.15, "metalness": 0.0, "specular": 0.6, "fresnel": 0.25},
    "metal": {"roughness": 0.35, "metalness": 0.85, "specular": 0.7, "fresnel": 0.2},
    "wood": {"roughness": 0.80, "metalness": 0.0, "specular": 0.08, "fresnel": 0.04},
    "glass": {"roughness": 0.08, "metalness": 0.0, "specular": 0.7, "fresnel": 0.28},
}


def resolve_material(entity: str, role: str = "") -> Dict[str, float]:
    e = (entity or "").lower()
    if e in MATERIAL_PRESETS:
        return dict(MATERIAL_PRESETS[e])
    r = (role or "").lower()
    role_map = {
        "ground": "ground",
        "river": "river",
        "strip": "road",
        "house": "house",
        "building": "building",
        "tree": "tree",
        "bush": "bush",
        "triangle": "mountain",
        "boat": "boat",
        "disc": "default",
        "person": "person",
        "fence": "fence",
        "bridge": "bridge",
        "flower": "flower",
        "disc_top": "sun",
    }
    key = role_map.get(r, "default")
    return dict(MATERIAL_PRESETS.get(key, MATERIAL_PRESETS["default"]))


def shade_albedo(
    albedo: Tuple[float, float, float],
    xx: np.ndarray,
    yy: np.ndarray,
    mask: np.ndarray,
    sun_pos: Tuple[float, float] = (0.72, 0.20),
    material: Optional[Dict[str, float]] = None,
    horizon: float = 0.66,
) -> np.ndarray:
    """Return shaded RGB under mask (float HxWx3), zeros outside mask.

    Light from sun_pos; normal approximated from height gradient of mask
    (blob/path soft edges act as curvature).
    """
    mat = material or MATERIAL_PRESETS["default"]
    roughness = float(mat.get("roughness", 0.75))
    metalness = float(mat.get("metalness", 0.0))
    specular = float(mat.get("specular", 0.12))
    f0 = float(mat.get("fresnel", 0.04))
    emissive = float(mat.get("emissive", 0.0))

    m = np.asarray(mask, dtype=np.float32)
    # Fake normal from mask gradient (soft edges = curvature)
    # sobel-ish
    gy = np.zeros_like(m)
    gx = np.zeros_like(m)
    gy[1:-1, :] = m[2:, :] - m[:-2, :]
    gx[:, 1:-1] = m[:, 2:] - m[:, :-2]
    # world light direction from sun
    sx, sy = sun_pos
    # per-pixel light dir toward sun in image plane + upward component
    lx = sx - xx
    ly = sy - yy
    # add "up" bias (negative y in image = sky)
    lz = 0.55
    ln = np.sqrt(lx * lx + ly * ly + lz * lz) + 1e-6
    lx, ly, lz = lx / ln, ly / ln, lz / ln
    # normal: mostly up, tilt by gradient
    nx = -gx * 2.5
    ny = -gy * 2.5
    nz = 1.0
    nn = np.sqrt(nx * nx + ny * ny + nz * nz) + 1e-6
    nx, ny, nz = nx / nn, ny / nn, nz / nn
    ndotl = np.clip(nx * lx + ny * ly + nz * lz, 0.0, 1.0)

    # ambient sky fill (stronger higher on screen)
    ambient = 0.22 + 0.12 * (1.0 - yy)
    # diffuse
    diff = ambient + 0.78 * ndotl
    # Schlick fresnel vs view (view ~ upward)
    view_up = np.clip(0.35 + 0.65 * (1.0 - yy), 0, 1)  # crude
    # fresnel higher at grazing (low ndotv ≈ edges of mask)
    edge = 1.0 - m  # wrong; use 1-ndotl-ish for rim
    fres = f0 + (1.0 - f0) * np.power(1.0 - np.clip(ndotl * 0.5 + 0.5, 0, 1), 5.0)
    # specular lobe sharpness from roughness
    sharp = max(1.0, (1.0 - roughness) * 48.0)
    # half-vector approx: highlight toward sun
    half = np.clip(ndotl, 0, 1) ** sharp
    spec_w = (specular * (1.0 - roughness * 0.7) + fres * 0.5) * half
    spec_w = spec_w * (0.35 + 0.65 * (1.0 - metalness * 0.5))

    alb = np.asarray(albedo, dtype=np.float32)
    # metals: diffuse pulled toward black, specular tinted by albedo
    diff_col = alb * (1.0 - metalness * 0.85)
    spec_col = alb * metalness + (1.0 - metalness) * np.array([1.0, 1.0, 1.0], dtype=np.float32)

    out = diff_col[None, None, :] * diff[..., None] + spec_col[None, None, :] * spec_w[..., None]
    if emissive > 0:
        out = out + alb[None, None, :] * emissive
    out = np.clip(out, 0, 4.0).astype(np.float32)
    return out * m[..., None]


def blend_shaded(
    img: np.ndarray,
    mask: np.ndarray,
    albedo: Tuple[float, float, float],
    xx: np.ndarray,
    yy: np.ndarray,
    sun_pos: Tuple[float, float],
    entity: str = "",
    role: str = "",
    horizon: float = 0.66,
) -> None:
    """In-place paint with material shading."""
    mat = resolve_material(entity, role)
    shaded = shade_albedo(albedo, xx, yy, mask, sun_pos=sun_pos, material=mat, horizon=horizon)
    m = np.asarray(mask, dtype=np.float32)[..., None]
    img[:] = img * (1.0 - m) + shaded * m


def demo():
    from PIL import Image

    h = w = 256
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    yy /= h - 1
    xx /= w - 1
    img = np.zeros((h, w, 3), dtype=np.float32)
    # water disc
    r = np.sqrt((xx - 0.5) ** 2 + (yy - 0.55) ** 2)
    mask = np.clip(1.0 - (r - 0.22) / 0.01, 0, 1)
    blend_shaded(img, mask, (0.15, 0.4, 0.7), xx, yy, (0.75, 0.2), entity="water", role="river")
    path = "/tmp/materials_demo.png"
    Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(path)
    print("wrote", path, "mat", resolve_material("water"))


if __name__ == "__main__":
    demo()
