#!/usr/bin/env python3
"""
Photoshop-lite for SI images — post-raster picture edits (not construction).

Honest: meta.construction may note picture_edit; does not invent scene entities.
Ops: global grade presets, vignette strength, title/text overlay.
"""
from __future__ import annotations

import io
from typing import Any, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont


GRADES = {
    "none": {},
    "warm": {"temp": 0.08, "contrast": 1.06, "sat": 1.05},
    "cool": {"temp": -0.08, "contrast": 1.04, "sat": 0.98},
    "contrast": {"temp": 0.0, "contrast": 1.18, "sat": 1.02},
    "fade": {"temp": 0.02, "contrast": 0.88, "sat": 0.9, "lift": 0.06},
    "vivid": {"temp": 0.04, "contrast": 1.12, "sat": 1.2},
}


def _to_rgb_array(img: np.ndarray) -> np.ndarray:
    x = np.asarray(img, dtype=np.float32)
    if x.max() > 1.5:
        x = x / 255.0
    return np.clip(x, 0, 1)


def apply_grade(
    img: np.ndarray,
    grade: str = "none",
    *,
    strength: float = 1.0,
) -> np.ndarray:
    g = GRADES.get((grade or "none").lower().strip(), GRADES["none"])
    if not g:
        return _to_rgb_array(img)
    s = float(np.clip(strength, 0, 1))
    x = _to_rgb_array(img).copy()
    temp = float(g.get("temp", 0.0)) * s
    contrast = 1.0 + (float(g.get("contrast", 1.0)) - 1.0) * s
    sat = 1.0 + (float(g.get("sat", 1.0)) - 1.0) * s
    lift = float(g.get("lift", 0.0)) * s

    x[..., 0] = np.clip(x[..., 0] * (1.0 + temp), 0, 1)
    x[..., 2] = np.clip(x[..., 2] * (1.0 - temp * 0.85), 0, 1)
    mid = 0.5
    x = np.clip((x - mid) * contrast + mid, 0, 1)
    luma = (0.2126 * x[..., 0] + 0.7152 * x[..., 1] + 0.0722 * x[..., 2])[..., None]
    x = np.clip(luma + (x - luma) * sat, 0, 1)
    if lift:
        x = np.clip(x * (1.0 - lift) + lift, 0, 1)
    return x.astype(np.float32)


def apply_vignette(img: np.ndarray, amount: float = 0.25) -> np.ndarray:
    x = _to_rgb_array(img)
    a = float(np.clip(amount, 0, 1))
    if a < 1e-4:
        return x
    h, w = x.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    yy = yy / max(h - 1, 1) - 0.5
    xx = xx / max(w - 1, 1) - 0.5
    rad = np.sqrt(xx * xx + yy * yy)
    vig = 1.0 - a * np.clip((rad - 0.35) / 0.55, 0, 1) ** 1.4
    return (x * vig[..., None]).astype(np.float32)


def apply_text_overlay(
    img: np.ndarray,
    text: str,
    *,
    position: str = "bottom",
    color: Tuple[int, int, int] = (255, 255, 255),
    shadow: bool = True,
) -> np.ndarray:
    text = (text or "").strip()
    if not text:
        return _to_rgb_array(img)
    x = _to_rgb_array(img)
    h, w = x.shape[:2]
    pil = Image.fromarray((x * 255).astype(np.uint8), mode="RGB")
    dr = ImageDraw.Draw(pil)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            size=max(12, min(h, w) // 18),
        )
    except Exception:
        font = ImageFont.load_default()
    # text bbox
    try:
        bbox = dr.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        tw, th = dr.textlength(text, font=font), 14
    margin = max(6, h // 40)
    if position == "top":
        tx, ty = (w - tw) // 2, margin
    elif position == "center":
        tx, ty = (w - tw) // 2, (h - th) // 2
    else:
        tx, ty = (w - tw) // 2, h - th - margin * 2
    if shadow:
        dr.text((tx + 1, ty + 1), text, font=font, fill=(0, 0, 0))
    dr.text((tx, ty), text, font=font, fill=color)
    return (np.asarray(pil, dtype=np.float32) / 255.0)


def edit_image(
    img: np.ndarray,
    *,
    grade: str = "none",
    vignette: float = 0.0,
    text: str = "",
    text_position: str = "bottom",
    strength: float = 1.0,
) -> dict[str, Any]:
    """Apply picture-edit chain. Returns image + meta."""
    ops = []
    x = _to_rgb_array(img)
    if grade and grade.lower() not in ("none", "", "off"):
        x = apply_grade(x, grade, strength=strength)
        ops.append(f"grade={grade}")
    if vignette and float(vignette) > 0:
        x = apply_vignette(x, float(vignette))
        ops.append(f"vignette={float(vignette):.2f}")
    if text and text.strip():
        x = apply_text_overlay(x, text, position=text_position)
        ops.append("text_overlay")
    return {
        "image": np.clip(x, 0, 1).astype(np.float32),
        "meta": {
            "construction": "picture_edit",
            "honesty": "picture_edit",
            "not_diffusion": True,
            "ops": ops,
            "note": "post-raster picture edit — not SI world construction",
        },
    }


def edit_png_bytes(
    png_bytes: bytes,
    **kwargs: Any,
) -> tuple[bytes, dict[str, Any]]:
    pil = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    arr = np.asarray(pil, dtype=np.float32) / 255.0
    out = edit_image(arr, **kwargs)
    buf = io.BytesIO()
    Image.fromarray((out["image"] * 255).astype(np.uint8)).save(buf, format="PNG")
    return buf.getvalue(), out["meta"]
