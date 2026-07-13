#!/usr/bin/env python3
"""
SI image post-enhance — structured raster polish + optional local neural upscale.

HONEST CONTRACT
===============
- SI scene graph remains master stock. Enhance never invents new entities.
- ``si_detail`` / ``si_upscale2``: pure numpy/scipy/PIL — deterministic, offline, no weights.
- ``realesrgan``: optional ONNX Real-ESRGAN when model + onnxruntime exist.
  LOUD degrade if missing — never fakes photoreal.
- Open-domain photoreal still needs a learned prior; pure SI cannot invent skin pores.

Modes
-----
  none         — passthrough
  si_detail    — multi-scale unsharp + micro-contrast (diagram/illustration polish)
  si_upscale2  — Lanczos 2× then si_detail (sharp large prints, still SI)
  realesrgan   — Real-ESRGAN x4 ONNX if available (learned texture fill on SI raster)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np

ENHANCE_MODES = ("none", "si_detail", "si_upscale2", "realesrgan")

# Prefer repo data/, then SYNTHESUS_HOME, then ~/.local/share/synthesus
def _model_candidates() -> list[Path]:
    roots = []
    env = os.environ.get("SYNTHESUS_ESRGAN_MODEL", "").strip()
    if env:
        roots.append(Path(env))
    here = Path(__file__).resolve()
    # reasoning/ -> packages/ -> runtime/
    runtime = here.parents[2]
    roots.append(runtime / "data" / "models" / "realesrgan-x4.onnx")
    roots.append(runtime / "data" / "models" / "RealESRGAN_x4plus.onnx")
    home = Path(os.environ.get("SYNTHESUS_HOME", Path.home() / ".local" / "share" / "synthesus"))
    roots.append(home / "models" / "realesrgan-x4.onnx")
    roots.append(home / "models" / "RealESRGAN_x4plus.onnx")
    return roots


def find_realesrgan_model() -> Optional[Path]:
    for p in _model_candidates():
        if p.is_file() and p.stat().st_size > 1_000_000:
            return p
    return None


def realesrgan_status() -> Dict[str, Any]:
    model = find_realesrgan_model()
    try:
        import onnxruntime  # noqa: F401
        ort_ok = True
        ort_ver = getattr(__import__("onnxruntime"), "__version__", "?")
    except Exception as e:
        ort_ok = False
        ort_ver = str(e)
    return {
        "mode": "realesrgan",
        "available": bool(model and ort_ok),
        "model_path": str(model) if model else None,
        "onnxruntime": ort_ok,
        "onnxruntime_version": ort_ver if ort_ok else None,
        "note": (
            "Local neural upscale of SI raster — not open-domain diffusion. "
            "Scene graph remains SI stock."
            if model and ort_ok
            else "Install onnxruntime + place RealESRGAN x4 ONNX under data/models/ "
            "or set SYNTHESUS_ESRGAN_MODEL. Until then use si_detail / si_upscale2."
        ),
    }


def _to_float_rgb(arr: np.ndarray) -> np.ndarray:
    x = np.asarray(arr)
    if x.dtype == np.uint8:
        x = x.astype(np.float32) / 255.0
    else:
        x = x.astype(np.float32)
        if x.max() > 1.5:
            x = x / 255.0
    if x.ndim == 2:
        x = np.stack([x, x, x], axis=-1)
    if x.shape[-1] == 4:
        x = x[..., :3]
    return np.clip(x, 0.0, 1.0)


def _gaussian_blur(img: np.ndarray, sigma: float) -> np.ndarray:
    """Separable Gaussian blur (HWC float)."""
    if sigma <= 0.05:
        return img
    from scipy import ndimage

    out = np.empty_like(img)
    for c in range(img.shape[2]):
        out[..., c] = ndimage.gaussian_filter(img[..., c], sigma=sigma, mode="nearest")
    return out


def si_detail_enhance(rgb: np.ndarray, strength: float = 0.55) -> np.ndarray:
    """Multi-scale unsharp + local micro-contrast. Deterministic. No neural weights.

    Improves edge snap and print sharpness for SI construction rasters.
    Does NOT invent photoreal texture distributions.
    """
    x = _to_float_rgb(rgb)
    strength = float(np.clip(strength, 0.0, 1.5))
    # Fine detail
    blur_f = _gaussian_blur(x, 0.7)
    detail_f = x - blur_f
    # Medium structure
    blur_m = _gaussian_blur(x, 2.2)
    detail_m = blur_f - blur_m
    y = x + strength * 1.15 * detail_f + strength * 0.55 * detail_m
    # Mild S-curve for print contrast (keeps mid-tones readable)
    y = np.clip(y, 0.0, 1.0)
    y = y * (1.0 - 0.08 * strength) + (y ** 0.92) * (0.08 * strength)
    # Edge guard: don't over-sharpen flat sky regions
    lum = 0.2126 * x[..., 0] + 0.7152 * x[..., 1] + 0.0722 * x[..., 2]
    edge = np.abs(_gaussian_blur(lum[..., None], 0.5)[..., 0] - _gaussian_blur(lum[..., None], 1.8)[..., 0])
    edge_w = np.clip(edge * 6.0, 0.0, 1.0)[..., None]
    y = x * (1.0 - 0.35 * strength * (1.0 - edge_w)) + y * (1.0 - 0.65 * strength * (1.0 - edge_w) + 0.65 * strength)
    # simplify: blend original and enhanced by edge weight
    mix = np.clip(0.35 + 0.65 * edge_w * strength, 0.0, 1.0)
    out = x * (1.0 - mix) + np.clip(y, 0.0, 1.0) * mix
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def si_upscale2(rgb: np.ndarray) -> np.ndarray:
    """Deterministic 2× Lanczos upscale + si_detail. Still pure SI / classical."""
    from PIL import Image

    x = _to_float_rgb(rgb)
    h, w = x.shape[:2]
    pil = Image.fromarray((x * 255).astype(np.uint8), mode="RGB")
    up = pil.resize((w * 2, h * 2), resample=Image.Resampling.LANCZOS)
    arr = np.asarray(up, dtype=np.float32) / 255.0
    return si_detail_enhance(arr, strength=0.45)


def _run_realesrgan_onnx(rgb: np.ndarray, model_path: Path) -> np.ndarray:
    import onnxruntime as ort
    from PIL import Image

    x = _to_float_rgb(rgb)
    # Real-ESRGAN typically expects NCHW RGB float 0..1, multiple of 4
    h, w = x.shape[:2]
    # pad to multiple of 4
    ph = (4 - h % 4) % 4
    pw = (4 - w % 4) % 4
    if ph or pw:
        x = np.pad(x, ((0, ph), (0, pw), (0, 0)), mode="edge")
    inp = x.transpose(2, 0, 1)[None, ...].astype(np.float32)
    sess = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    in_name = sess.get_inputs()[0].name
    out = sess.run(None, {in_name: inp})[0]
    # NCHW -> HWC
    y = np.asarray(out)
    if y.ndim == 4:
        y = y[0]
    if y.shape[0] in (3, 4) and y.shape[-1] not in (3, 4):
        y = y.transpose(1, 2, 0)
    y = y[..., :3]
    y = np.clip(y, 0.0, 1.0)
    # crop pad*scale (x4)
    if ph or pw:
        y = y[: h * 4, : w * 4, :]
    return y.astype(np.float32)


def enhance_image(
    rgb_or_path: Any,
    mode: str = "si_detail",
    *,
    strength: float = 0.55,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Apply enhance mode. Returns (float RGB HWC 0..1, meta).

    Raises RuntimeError with loud message if neural mode unavailable.
    """
    mode = (mode or "none").lower().strip()
    if mode not in ENHANCE_MODES:
        mode = "none"

    if isinstance(rgb_or_path, (str, Path)):
        from PIL import Image
        arr = np.asarray(Image.open(rgb_or_path).convert("RGB"))
    else:
        arr = rgb_or_path

    meta: Dict[str, Any] = {
        "enhance": mode,
        "not_diffusion": True,
        "si_stock_master": True,
    }

    if mode == "none":
        out = _to_float_rgb(arr)
        meta["engine"] = "passthrough"
        return out, meta

    if mode == "si_detail":
        out = si_detail_enhance(arr, strength=strength)
        meta["engine"] = "si_detail_multiscale"
        meta["neural"] = False
        meta["honest"] = "classical multi-scale detail — not photoreal texture invention"
        return out, meta

    if mode == "si_upscale2":
        out = si_upscale2(arr)
        meta["engine"] = "si_lanczos2_detail"
        meta["neural"] = False
        meta["scale"] = 2
        meta["honest"] = "deterministic 2× Lanczos + SI detail — still construction, not diffusion"
        return out, meta

    if mode == "realesrgan":
        st = realesrgan_status()
        if not st["available"]:
            raise RuntimeError(
                "realesrgan_unavailable: " + st["note"]
                + f" (model={st.get('model_path')}, ort={st.get('onnxruntime')})"
            )
        model = Path(st["model_path"])
        out = _run_realesrgan_onnx(arr, model)
        meta["engine"] = "si_raster+realesrgan_onnx"
        meta["neural"] = True
        meta["model"] = str(model)
        meta["scale"] = 4
        meta["honest"] = (
            "Local Real-ESRGAN upscale of SI-constructed raster. "
            "Not open-domain diffusion. Geometry/entities remain SI scene graph stock."
        )
        meta["not_diffusion"] = True  # enhance is not a diffusion pipeline
        meta["breaks_pure_si_pixels"] = True
        return out, meta

    out = _to_float_rgb(arr)
    meta["engine"] = "passthrough"
    return out, meta


def enhance_file(path: str, mode: str = "si_detail", strength: float = 0.55) -> Dict[str, Any]:
    """In-place enhance PNG/JPEG on disk. Returns meta (+ optional new size)."""
    from PIL import Image

    out, meta = enhance_image(path, mode=mode, strength=strength)
    Image.fromarray((out * 255).astype(np.uint8), mode="RGB").save(path)
    meta["path"] = path
    meta["width"] = int(out.shape[1])
    meta["height"] = int(out.shape[0])
    return meta


def capability_enhance() -> Dict[str, Any]:
    return {
        "modes": list(ENHANCE_MODES),
        "default": "none",
        "si_detail": {
            "neural": False,
            "offline": True,
            "deterministic": True,
            "note": "Always available. Diagram/illustration polish.",
        },
        "si_upscale2": {
            "neural": False,
            "offline": True,
            "deterministic": True,
            "note": "2× Lanczos + detail. Always available.",
        },
        "realesrgan": realesrgan_status(),
        "honest_ceiling": (
            "Pure SI construction is optimal for diagrams/schematics/stylized. "
            "Open-domain photoreal needs learned texture priors (realesrgan or ControlNet tier)."
        ),
    }
