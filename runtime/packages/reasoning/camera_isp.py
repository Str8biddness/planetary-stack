#!/usr/bin/env python3
"""
Camera / Smart-TV ISP math for SI image finish — Synthesus (not diffusion).
=========================================================================

Photoreal *look* without neural generative models. Pipeline mirrors what
digital cameras and display engines already do in silicon:

  1. Linearize (scene-referred RGB)
  2. Auto-exposure (mid-gray / center-weighted metering)
  3. White-balance / colour temperature
  4. Soft bloom / optical glare (bright-pass + blur)
  5. Depth-of-field approximation (depth from y + multi-scale blur)
  6. Chromatic aberration (radial R/B shift)
  7. Filmic tone map (ACES-inspired)
  8. Local contrast / smart-TV clarity
  9. Sensor noise (ISO-linked)
 10. sRGB OETF + lens vignette

Honest ceiling: photographed *look* for procedural SI geometry — not diffusion
object invention. Growing realism of *content* still = vocabulary + materials.

Run: python packages/reasoning/camera_isp.py
"""
from __future__ import annotations

from typing import Any, Optional, Tuple

import numpy as np

LOOKS = frozenset({"raw", "photo", "cinema", "vivid", "tv"})


def _box_blur_1d(ch: np.ndarray, radius: int, axis: int) -> np.ndarray:
    """Constant-time box filter via cumsum along one axis."""
    r = int(max(0, radius))
    if r == 0:
        return ch.astype(np.float32)
    pad_width = [(0, 0), (0, 0)]
    pad_width[axis] = (r, r)
    pad = np.pad(ch.astype(np.float64), pad_width, mode="edge")
    csum = np.cumsum(pad, axis=axis)
    # sum of window size w=2r+1 ending at i+2r relative to unpadded...
    # For output index i, sum pad[i : i+2r+1] = csum[i+2r] - csum[i-1]
    w = 2 * r + 1
    if axis == 1:
        # csum shape (h, w+2r)
        left = np.zeros_like(csum)
        left[:, 1:] = csum[:, :-1]
        # window from j to j+w-1 in padded coords, j = 0..orig_w-1 maps to pad index j
        # sum = csum[:, j+w-1] - left[:, j]
        out = (csum[:, w - 1 : w - 1 + ch.shape[1]] - left[:, : ch.shape[1]]) / w
    else:
        left = np.zeros_like(csum)
        left[1:, :] = csum[:-1, :]
        out = (csum[w - 1 : w - 1 + ch.shape[0], :] - left[: ch.shape[0], :]) / w
    return out.astype(np.float32)


def box_blur(ch: np.ndarray, radius: int) -> np.ndarray:
    """Separable multi-pass box ≈ gaussian (TV/camera soft)."""
    r = int(max(0, radius))
    if r <= 0:
        return ch.astype(np.float32)
    out = ch.astype(np.float32)
    for _ in range(3):
        out = _box_blur_1d(out, r, axis=1)
        out = _box_blur_1d(out, r, axis=0)
    return out


def _luma(img: np.ndarray) -> np.ndarray:
    return (
        0.2126 * img[..., 0] + 0.7152 * img[..., 1] + 0.0722 * img[..., 2]
    ).astype(np.float32)


def auto_exposure(img: np.ndarray, target: float = 0.18) -> Tuple[np.ndarray, float]:
    y = _luma(img)
    h, w = y.shape
    y0, y1 = h // 4, 3 * h // 4
    x0, x1 = w // 4, 3 * w // 4
    meter = float(np.mean(y[y0:y1, x0:x1]) + 1e-4)
    gain = float(np.clip(target / meter, 0.35, 3.5))
    return np.clip(img * gain, 0, 8.0).astype(np.float32), gain


def white_balance(img: np.ndarray, temperature: float = 5600.0) -> np.ndarray:
    t = float(np.clip(temperature, 2500, 9000))
    d = (t - 5600.0) / 5600.0
    out = img.copy()
    out[..., 0] *= 1.0 - 0.18 * d
    out[..., 1] *= 1.0 - 0.04 * abs(d)
    out[..., 2] *= 1.0 + 0.22 * d
    return np.clip(out, 0, 8.0).astype(np.float32)


def bloom(img: np.ndarray, threshold: float = 0.75, amount: float = 0.35, radius: int = 6) -> np.ndarray:
    y = _luma(img)
    mask = np.clip((y - threshold) / max(1.0 - threshold, 1e-3), 0, 1)
    bright = img * mask[..., None]
    blur = np.stack([box_blur(bright[..., k], radius) for k in range(3)], -1)
    return np.clip(img + blur * amount, 0, 8.0).astype(np.float32)


def depth_of_field(
    img: np.ndarray,
    yy: np.ndarray,
    horizon: float,
    focus: float = 0.62,
    amount: float = 0.55,
    max_radius: int = 5,
    depth_map: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Bokeh-style DOF.

    If depth_map (HxW, 0=near 1=far) is provided, CoC = |z - focus|.
    Otherwise falls back to y-horizon proxy (legacy).
    """
    if depth_map is not None and depth_map.shape[:2] == img.shape[:2]:
        depth = np.clip(depth_map.astype(np.float32), 0, 1)
        focus = float(np.clip(focus, 0.0, 1.0))
        coc = np.clip(np.abs(depth - focus) * 1.85, 0, 1)
    else:
        depth = np.clip(yy, 0, 1)
        focus = float(np.clip(focus, 0.15, 0.95))
        coc = np.clip(np.abs(depth - focus) * 1.4 + np.clip(horizon - yy, 0, 1) * 0.15, 0, 1)
    soft = np.stack([box_blur(img[..., k], max(1, max_radius)) for k in range(3)], -1)
    softer = np.stack([box_blur(img[..., k], max(2, max_radius + 2)) for k in range(3)], -1)
    a = (coc * amount).astype(np.float32)[..., None]
    mid = img * (1 - np.clip(a * 1.2, 0, 1)) + soft * np.clip(a * 1.2, 0, 1)
    a2 = np.clip((coc - 0.4) * 2.0 * amount, 0, 1)[..., None]
    return (mid * (1 - a2) + softer * a2).astype(np.float32)


def chromatic_aberration(img: np.ndarray, strength: float = 0.0018) -> np.ndarray:
    h, w, _ = img.shape
    yy, xx = np.mgrid[0:h, 0:w]
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    dx = (xx - cx) / max(w, 1)
    dy = (yy - cy) / max(h, 1)
    sx = np.rint(dx * strength * w).astype(np.int32)
    sy = np.rint(dy * strength * h).astype(np.int32)
    out = img.copy()
    ys = np.clip(yy + sy, 0, h - 1)
    xs = np.clip(xx + sx, 0, w - 1)
    yi = np.clip(yy - sy, 0, h - 1)
    xi = np.clip(xx - sx, 0, w - 1)
    out[..., 0] = img[ys, xs, 0]
    out[..., 2] = img[yi, xi, 2]
    return out.astype(np.float32)


def filmic_tonemap(img: np.ndarray) -> np.ndarray:
    x = np.clip(img, 0, 16.0)
    a, b, c, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
    y = (x * (a * x + b)) / (x * (c * x + d) + e + 1e-8)
    return np.clip(y, 0, 1).astype(np.float32)


def local_contrast(img: np.ndarray, amount: float = 0.22, radius: int = 4) -> np.ndarray:
    y = _luma(img)
    blur = box_blur(y, radius)
    detail = y - blur
    y2 = np.clip(y + detail * amount, 0, 1)
    scale = (y2 / (y + 1e-5))[..., None]
    return np.clip(img * scale, 0, 1).astype(np.float32)


def sensor_noise(img: np.ndarray, iso: float = 200.0, seed: int = 0) -> np.ndarray:
    iso = float(np.clip(iso, 50, 3200))
    rng = np.random.default_rng(int(seed) + 7)
    shot = 0.004 * np.sqrt(iso / 100.0)
    read = 0.002 * (iso / 100.0) * 0.35
    noise = rng.normal(0.0, 1.0, size=img.shape).astype(np.float32)
    y = _luma(img)[..., None]
    out = img + noise * (shot * np.sqrt(np.clip(y, 0, 1) + 1e-4) + read)
    return np.clip(out, 0, 1).astype(np.float32)


def srgb_oetf(img: np.ndarray) -> np.ndarray:
    x = np.clip(img, 0, 1)
    return np.where(
        x <= 0.0031308,
        12.92 * x,
        1.055 * np.power(np.maximum(x, 1e-8), 1.0 / 2.4) - 0.055,
    ).astype(np.float32)


def apply_camera_look(
    img: np.ndarray,
    yy: np.ndarray,
    horizon: float = 0.66,
    look: str = "photo",
    seed: Optional[int] = None,
    sun_pos: Optional[Tuple[float, float]] = None,
    depth_map: Optional[np.ndarray] = None,
    focus_depth: Optional[float] = None,
) -> dict[str, Any]:
    look = (look or "photo").lower().strip()
    if look not in LOOKS:
        look = "photo"
    if look == "raw":
        return {
            "image": np.clip(img, 0, 1).astype(np.float32),
            "meta": {"look": "raw", "pipeline": [], "engine": "none"},
        }

    seed = 0 if seed is None else int(seed)
    pipeline: list[str] = []
    x = np.clip(img.astype(np.float32), 0, 4.0)

    if look == "cinema":
        temp, iso, bloom_amt, dof_amt, contrast = 4800.0, 400.0, 0.28, 0.65, 0.18
        target = 0.16
    elif look == "vivid":
        temp, iso, bloom_amt, dof_amt, contrast = 6000.0, 100.0, 0.40, 0.35, 0.32
        target = 0.20
    elif look == "tv":
        temp, iso, bloom_amt, dof_amt, contrast = 6500.0, 100.0, 0.22, 0.20, 0.38
        target = 0.22
    else:
        temp, iso, bloom_amt, dof_amt, contrast = 5600.0, 200.0, 0.32, 0.50, 0.24
        target = 0.18

    x, gain = auto_exposure(x, target=target)
    pipeline.append(f"ae_gain={gain:.3f}")
    x = white_balance(x, temperature=temp)
    pipeline.append(f"wb_K={temp:.0f}")

    if sun_pos is not None:
        h, w = x.shape[:2]
        sx, sy = sun_pos
        yyg, xxg = np.mgrid[0:h, 0:w].astype(np.float32)
        yyg /= max(h - 1, 1)
        xxg /= max(w - 1, 1)
        dist = np.sqrt((xxg - sx) ** 2 + (yyg - sy) ** 2)
        flare = np.clip(1.0 - dist / 0.55, 0, 1) ** 2 * 0.12
        x = np.clip(
            x + flare[..., None] * np.array([1.0, 0.95, 0.8], dtype=np.float32), 0, 8
        )
        pipeline.append("sun_flare")

    x = bloom(x, threshold=0.72, amount=bloom_amt, radius=6 if look != "tv" else 3)
    pipeline.append("bloom")
    # True DOF when per-object depth map present; else y-proxy
    fd = 0.35 if focus_depth is None else float(focus_depth)
    if depth_map is None:
        fd = 0.62  # legacy y-focus
    x = depth_of_field(
        x, yy, horizon, focus=fd, amount=dof_amt, max_radius=4, depth_map=depth_map
    )
    pipeline.append("dof_z" if depth_map is not None else "dof_y")
    if look in ("photo", "cinema"):
        x = chromatic_aberration(x, strength=0.0015 if look == "photo" else 0.0022)
        pipeline.append("ca")

    x = filmic_tonemap(x)
    pipeline.append("filmic")
    x = local_contrast(x, amount=contrast, radius=3 if look == "tv" else 4)
    pipeline.append("clarity")
    x = sensor_noise(x, iso=iso, seed=seed)
    pipeline.append(f"iso={iso:.0f}")

    h, w = x.shape[:2]
    yyg, xxg = np.mgrid[0:h, 0:w].astype(np.float32)
    yyg = yyg / max(h - 1, 1)
    xxg = xxg / max(w - 1, 1)
    rad = np.sqrt((xxg - 0.5) ** 2 + (yyg - 0.5) ** 2)
    vig = 1.0 - 0.18 * np.clip((rad - 0.45) / 0.55, 0, 1) ** 1.5
    x = x * vig[..., None]
    pipeline.append("vignette")

    x = srgb_oetf(np.clip(x, 0, 1))
    pipeline.append("srgb")

    return {
        "image": np.clip(x, 0, 1).astype(np.float32),
        "meta": {
            "look": look,
            "pipeline": pipeline,
            "ae_gain": gain,
            "engine": "synthesus_camera_isp",
            "focus_depth": fd if depth_map is not None else None,
            "depth_guided": depth_map is not None,
            "note": "camera/TV ISP math on SI scene — not diffusion",
        },
    }


def demo():
    h, w = 256, 384
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    yy /= h - 1
    xx /= w - 1
    img = np.stack(
        [0.3 + 0.5 * (1 - yy), 0.4 + 0.2 * xx, 0.6 - 0.3 * yy], -1
    ).astype(np.float32)
    r = np.sqrt((xx - 0.7) ** 2 + (yy - 0.2) ** 2)
    img += (np.clip(1 - r / 0.08, 0, 1) * 2.0)[..., None]
    out = apply_camera_look(img, yy, horizon=0.65, look="photo", seed=1, sun_pos=(0.7, 0.2))
    from PIL import Image

    path = "/tmp/camera_isp_demo.png"
    Image.fromarray((out["image"] * 255).astype(np.uint8)).save(path)
    print("wrote", path, out["meta"])


if __name__ == "__main__":
    demo()
