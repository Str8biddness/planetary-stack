"""Synthesus image generation service (SI, not AI) — image-roundout.

VSA / pattern-geometric text-to-image: text → resolution-free scene graph → HD
raster. Deterministic, CPU-only, no diffusion. Renders concepts in the visual
vocabulary (``scene_composer.SHAPES``).

Roundout:
  - LRU prompt/result cache (prompt + res + style + seed + aspect)
  - style / seed / aspect knobs
  - richer pipeline (parity + multi-object layout) via vsa_pipeline_image
"""
from __future__ import annotations

import hashlib
import os
import tempfile
import threading
import time
from collections import OrderedDict
from typing import Any, Optional

import numpy as np

import scene_composer
from vsa_twolayer import cooccurrence, ppmi, svd_embed
from vsa_hopfield import ModernHopfield
import vsa_pipeline_image as vpi

# Vocab is grounded in renderable shapes — built once.
_VOCAB = sorted(scene_composer.SHAPES.keys())
_lock = threading.Lock()
_state: dict | None = None

# Process-local LRU of PNG bytes. Keyed by full render identity.
_CACHE_MAX = int(os.environ.get("SYNTHESUS_IMAGE_CACHE_SIZE", "32"))
_cache: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
_cache_lock = threading.Lock()

STYLES = sorted(vpi.STYLES)
VOCAB_VERSION = "image-studio-v1"


def renderable_vocabulary() -> list[str]:
    """The concepts this engine can render today (honest capability surface)."""
    return list(_VOCAB)


def clear_image_cache() -> None:
    """Drop the in-process PNG cache (tests / ops)."""
    with _cache_lock:
        _cache.clear()


def cache_stats() -> dict[str, int]:
    with _cache_lock:
        return {"size": len(_cache), "max": _CACHE_MAX}


def _imagination():
    global _state
    if _state is None:
        with _lock:
            if _state is None:
                tk = [w for w in _VOCAB if w in scene_composer.SHAPES]
                vidx = {w: i for i, w in enumerate(sorted(set(tk)))}
                E = svd_embed(
                    ppmi(cooccurrence(tk * 3, vidx, window=4)),
                    min(16, len(vidx)),
                )
                imag = ModernHopfield(
                    np.vstack([E[vidx[w]] for w in vidx]), list(vidx), beta=12.0
                )
                _state = {"imag": imag, "vidx": vidx, "E": E}
    return _state


def _cache_key(
    prompt: str,
    res: int,
    style: str,
    seed: Optional[int],
    aspect: float,
) -> str:
    raw = f"{VOCAB_VERSION}|{prompt.strip()}|{res}|{style}|{seed}|{aspect:.4f}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_get(key: str) -> Optional[dict[str, Any]]:
    with _cache_lock:
        item = _cache.get(key)
        if item is None:
            return None
        _cache.move_to_end(key)
        return item


def _cache_put(key: str, item: dict[str, Any]) -> None:
    with _cache_lock:
        _cache[key] = item
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)


def generate_image(
    prompt: str,
    out_path: str,
    res: int = 1024,
    style: str = "flat",
    seed: Optional[int] = None,
    aspect: float = 1.0,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Reason ``prompt`` into a scene graph and render it to ``out_path`` (PNG).

    Returns real metadata (entities, resolution, cache hit, style). Raises on
    failure — callers degrade loudly (never a fabricated image).
    """
    if not prompt or not prompt.strip():
        raise ValueError("prompt is required")

    res = int(res)
    res = max(128, min(2048, res))
    style = (style or "flat").lower().strip()
    if style not in STYLES:
        style = "flat"
    aspect = float(aspect) if aspect else 1.0
    aspect = float(np.clip(aspect, 0.5, 2.0))
    if seed is not None:
        seed = int(seed)

    key = _cache_key(prompt, res, style, seed, aspect)
    t0 = time.time()

    if use_cache:
        hit = _cache_get(key)
        if hit is not None:
            with open(out_path, "wb") as f:
                f.write(hit["png_bytes"])
            meta = dict(hit["meta"])
            meta["path"] = out_path
            meta["cache_hit"] = True
            meta["latency_ms"] = round((time.time() - t0) * 1000.0, 2)
            return meta

    s = _imagination()
    doc, horizon = vpi.pattern_document(
        prompt, s["imag"], s["vidx"], s["E"], seed=seed, style=style
    )
    vpi.render_doc(
        doc, horizon, res=res, out=out_path, style=style, aspect=aspect, seed=seed
    )
    entities = [
        p.get("entity") for p in doc if isinstance(p, dict) and p.get("entity")
    ]
    roles = sorted({p.get("role") for p in doc if p.get("role")})

    with open(out_path, "rb") as f:
        png_bytes = f.read()
    if len(png_bytes) < 64:
        raise RuntimeError("render produced empty/invalid PNG")

    meta = {
        "prompt": prompt,
        "path": out_path,
        "resolution": res,
        "width": None,
        "height": None,
        "entities": entities,
        "entity_count": len(entities),
        "roles": roles,
        "vocabulary_size": len(s["vidx"]),
        "vocab_version": VOCAB_VERSION,
        "style": style,
        "seed": seed,
        "aspect": aspect,
        "cache_hit": False,
        "engine": "synthesus_vsa_geometric",
        "bytes": len(png_bytes),
    }
    # Fill pixel dims from file
    try:
        from PIL import Image as _Im
        with _Im.open(out_path) as im:
            meta["width"], meta["height"] = im.size
    except Exception:
        pass

    meta["latency_ms"] = round((time.time() - t0) * 1000.0, 2)

    if use_cache:
        _cache_put(key, {"png_bytes": png_bytes, "meta": {k: v for k, v in meta.items() if k != "path"}})

    return meta


if __name__ == "__main__":
    out = os.path.join(tempfile.gettempdir(), "synth_image_service_test.png")
    clear_image_cache()
    meta = generate_image(
        "a house and a tree on green grass under a blue sky with a sun and a star",
        out,
        res=512,
        style="soft",
        seed=3,
    )
    ok = os.path.exists(out) and os.path.getsize(out) > 1000
    print("meta:", meta)
    print("PNG written:", ok, os.path.getsize(out) if ok else 0, "bytes ->", out)
    meta2 = generate_image(
        "a house and a tree on green grass under a blue sky with a sun and a star",
        out + ".2.png",
        res=512,
        style="soft",
        seed=3,
    )
    print("cache_hit second call:", meta2.get("cache_hit"))
    assert ok, "no real PNG produced"
    assert meta2.get("cache_hit") is True
    assert "house" in meta["entities"]
    assert "star" in meta["entities"]
