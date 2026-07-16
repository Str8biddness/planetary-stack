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


def box_blur(ch: np.ndarray, radius: int) -> np.ndarray:
    """Fast blur via PIL Gaussian (C) — replaces multi-pass numpy box.

    Accepts HxW or HxWxC float arrays. Radius is approximate pixel sigma.
    """
    r = int(max(0, radius))
    if r <= 0:
        return np.asarray(ch, dtype=np.float32)
    from PIL import Image, ImageFilter

    arr = np.asarray(ch, dtype=np.float32)
    # PIL works in 0–255; preserve scale by normalizing with a safe max
    scale = float(max(float(arr.max()), 1e-6))
    sigma = max(0.5, r * 0.65)
    if arr.ndim == 2:
        u8 = np.clip(arr / scale * 255.0, 0, 255).astype(np.uint8)
        im = Image.fromarray(u8, mode="L")
        im = im.filter(ImageFilter.GaussianBlur(radius=sigma))
        return (np.asarray(im, dtype=np.float32) / 255.0) * scale
    if arr.ndim == 3 and arr.shape[2] >= 3:
        u8 = np.clip(arr[..., :3] / scale * 255.0, 0, 255).astype(np.uint8)
        im = Image.fromarray(u8, mode="RGB")
        im = im.filter(ImageFilter.GaussianBlur(radius=sigma))
        return (np.asarray(im, dtype=np.float32) / 255.0) * scale
    return arr


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
    # Single RGB blur (faster than 3× mono)
    blur = box_blur(bright, radius)
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
    # Two RGB blurs (not 6 mono channel blurs)
    soft = box_blur(img, max(1, max_radius))
    softer = box_blur(img, max(2, max_radius + 2))
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
    blur = box_blur(y, max(1, radius))
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
    quality: str = "full",
) -> dict[str, Any]:
    """Apply camera/TV ISP finish.

    quality:
      full  — full bloom / DOF / CA / noise / clarity
      draft — AE + WB + filmic + light bloom only (preview speed)
    """
    look = (look or "photo").lower().strip()
    if look not in LOOKS:
        look = "photo"
    if look == "raw":
        return {
            "image": np.clip(img, 0, 1).astype(np.float32),
            "meta": {"look": "raw", "pipeline": [], "engine": "none", "quality": "raw"},
        }

    seed = 0 if seed is None else int(seed)
    quality = (quality or "full").lower().strip()
    if quality not in ("full", "draft"):
        quality = "full"
    draft = quality == "draft"
    pipeline: list[str] = []
    x = np.clip(img.astype(np.float32), 0, 4.0)

    # Smaller blur radii — PIL gaussian is strong; less radius, same look, less cost
    if look == "cinema":
        temp, iso, bloom_amt, dof_amt, contrast = 4800.0, 400.0, 0.28, 0.65, 0.18
        target = 0.16
        bloom_r, dof_r = 4, 3
    elif look == "vivid":
        temp, iso, bloom_amt, dof_amt, contrast = 6000.0, 100.0, 0.40, 0.35, 0.32
        target = 0.20
        bloom_r, dof_r = 4, 2
    elif look == "tv":
        temp, iso, bloom_amt, dof_amt, contrast = 6500.0, 100.0, 0.22, 0.20, 0.38
        target = 0.22
        bloom_r, dof_r = 3, 2
    else:
        temp, iso, bloom_amt, dof_amt, contrast = 5600.0, 200.0, 0.32, 0.50, 0.24
        target = 0.18
        bloom_r, dof_r = 4, 3

    if draft:
        bloom_amt *= 0.55
        bloom_r = max(1, bloom_r - 2)
        dof_amt = 0.0
        contrast = 0.0
        iso = min(iso, 100.0)

    x, gain = auto_exposure(x, target=target)
    pipeline.append(f"ae_gain={gain:.3f}")
    x = white_balance(x, temperature=temp)
    pipeline.append(f"wb_K={temp:.0f}")

    if sun_pos is not None and not draft:
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

    if bloom_amt > 0.01:
        x = bloom(x, threshold=0.72, amount=bloom_amt, radius=bloom_r)
        pipeline.append("bloom" + ("_draft" if draft else ""))
    # True DOF when per-object depth map present; else y-proxy
    fd = 0.35 if focus_depth is None else float(focus_depth)
    if depth_map is None:
        fd = 0.62  # legacy y-focus
    if not draft and dof_amt > 0.01:
        x = depth_of_field(
            x, yy, horizon, focus=fd, amount=dof_amt, max_radius=dof_r, depth_map=depth_map
        )
        pipeline.append("dof_z" if depth_map is not None else "dof_y")
    if not draft and look in ("photo", "cinema"):
        x = chromatic_aberration(x, strength=0.0015 if look == "photo" else 0.0022)
        pipeline.append("ca")

    x = filmic_tonemap(x)
    pipeline.append("filmic")
    if not draft and contrast > 0.01:
        x = local_contrast(x, amount=contrast, radius=2 if look == "tv" else 3)
        pipeline.append("clarity")
    if not draft:
        x = sensor_noise(x, iso=iso, seed=seed)
        pipeline.append(f"iso={iso:.0f}")

    h, w = x.shape[:2]
    yyg, xxg = np.mgrid[0:h, 0:w].astype(np.float32)
    yyg = yyg / max(h - 1, 1)
    xxg = xxg / max(w - 1, 1)
    rad = np.sqrt((xxg - 0.5) ** 2 + (yyg - 0.5) ** 2)
    vig_amt = 0.10 if draft else 0.18
    vig = 1.0 - vig_amt * np.clip((rad - 0.45) / 0.55, 0, 1) ** 1.5
    x = x * vig[..., None]
    pipeline.append("vignette")

    x = srgb_oetf(np.clip(x, 0, 1))
    pipeline.append("srgb")
    if draft:
        pipeline.append("quality=draft")

    return {
        "image": np.clip(x, 0, 1).astype(np.float32),
        "meta": {
            "look": look,
            "pipeline": pipeline,
            "ae_gain": gain,
            "engine": "synthesus_camera_isp",
            "quality": quality,
            "focus_depth": fd if depth_map is not None else None,
            "depth_guided": depth_map is not None and not draft,
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
