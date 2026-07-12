#!/usr/bin/env python3
"""
Atmospheric sky model (Preetham-lite) — SI outdoor lighting without diffusion.
=============================================================================

Simplified analytical sky for daytime / dusk / night based on sun direction.
Inspired by Preetham & Hoffman sky models: zenith luminance, horizon glow,
sun aureole — pure math, no neural weights.

Honest: stylized physical sky, not a weather satellite product.

Run: python packages/reasoning/sky_model.py
"""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np

PI = np.pi


def render_sky(
    xx: np.ndarray,
    yy: np.ndarray,
    sun_pos: Tuple[float, float] = (0.72, 0.20),
    style: str = "soft",
    turbidity: float = 2.5,
) -> np.ndarray:
    """Return RGB sky (float HxWx3) for full frame.

    yy=0 top, yy=1 bottom (image space). Sun at sun_pos in same coords.
    """
    style = (style or "soft").lower()
    sx, sy = sun_pos
    # elevation proxy: sy small = high sun; night if style night or sun is moon-ish
    elev = float(np.clip(1.0 - sy / 0.55, 0.0, 1.0))  # 1 = high sun
    if style == "night":
        elev = 0.05

    # Zenith → horizon gradient angle
    # "view zenith angle" from top: 0 at zenith, larger toward horizon
    # horizon line around 0.66 later for ground; sky uses full y
    vza = np.clip(yy * 1.15, 0, 1)  # 0 top → 1 bottom

    # Base zenith / horizon colors by time of day
    if style == "night":
        zenith = np.array([0.04, 0.05, 0.12], dtype=np.float32)
        horizon = np.array([0.08, 0.10, 0.18], dtype=np.float32)
        sun_col = np.array([0.75, 0.80, 0.95], dtype=np.float32)
        aureole_str = 0.25
    elif elev > 0.65:
        # midday
        zenith = np.array([0.28, 0.48, 0.88], dtype=np.float32)
        horizon = np.array([0.62, 0.78, 0.95], dtype=np.float32)
        sun_col = np.array([1.0, 0.95, 0.75], dtype=np.float32)
        aureole_str = 0.55
    elif elev > 0.35:
        # afternoon
        zenith = np.array([0.25, 0.40, 0.78], dtype=np.float32)
        horizon = np.array([0.75, 0.65, 0.55], dtype=np.float32)
        sun_col = np.array([1.0, 0.82, 0.45], dtype=np.float32)
        aureole_str = 0.70
    else:
        # dusk / low sun
        zenith = np.array([0.12, 0.16, 0.35], dtype=np.float32)
        horizon = np.array([0.95, 0.45, 0.25], dtype=np.float32)
        sun_col = np.array([1.0, 0.55, 0.25], dtype=np.float32)
        aureole_str = 0.85

    # Turbidity: hazier horizon
    t = float(np.clip(turbidity, 1.0, 8.0))
    haze = 0.15 * (t - 1.0) / 7.0
    horizon = np.clip(horizon * (1.0 - haze) + np.array([0.7, 0.7, 0.72]) * haze, 0, 1)

    # Vertical blend with limb darkening toward zenith
    f = np.power(vza, 0.85 + 0.1 * (1 - elev))
    sky = zenith[None, None, :] * (1.0 - f[..., None]) + horizon[None, None, :] * f[..., None]

    # Sun aureole (scattering around sun)
    dist = np.sqrt((xx - sx) ** 2 + (yy - sy) ** 2)
    # Preetham-ish glow falloff
    glow = np.exp(-dist * dist / (0.04 + 0.02 * t)) * aureole_str
    glow2 = np.exp(-dist / (0.18 + 0.04 * t)) * aureole_str * 0.35
    glow = (glow + glow2).astype(np.float32)
    sky = sky + sun_col[None, None, :] * glow[..., None]

    # Subtle horizontal banding (atmospheric layers)
    bands = 0.02 * np.sin(yy * PI * 6.0) * (0.4 + 0.6 * vza)
    sky = sky + bands[..., None]

    return np.clip(sky, 0, 4.0).astype(np.float32)


def demo():
    from PIL import Image

    h, w = 320, 480
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    yy /= h - 1
    xx /= w - 1
    sky = render_sky(xx, yy, sun_pos=(0.75, 0.22), style="soft", turbidity=3.0)
    path = "/tmp/sky_model_demo.png"
    Image.fromarray((np.clip(sky, 0, 1) * 255).astype(np.uint8)).save(path)
    print("wrote", path)


if __name__ == "__main__":
    demo()
