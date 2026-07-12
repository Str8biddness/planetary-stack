"""Synthesus image generation service (SI, not AI) — image-wow.

VSA / pattern-geometric text-to-image: text → resolution-free scene graph → HD
raster. Deterministic, CPU-only, no diffusion.

Wow layer:
  - process LRU + optional disk cache (survives restarts)
  - detail: standard | high (richer trees/atmosphere)
  - variations: N seeds in one call
  - style / seed / aspect knobs
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Optional

import numpy as np

import scene_composer
from vsa_twolayer import cooccurrence, ppmi, svd_embed
from vsa_hopfield import ModernHopfield
import vsa_pipeline_image as vpi

_VOCAB = sorted(scene_composer.SHAPES.keys())
_lock = threading.Lock()
_state: dict | None = None

_CACHE_MAX = int(os.environ.get("SYNTHESUS_IMAGE_CACHE_SIZE", "48"))
_cache: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
_cache_lock = threading.Lock()

# Disk cache (optional). Default: ~/.cache/synthesus/image_cache
_DISK_CACHE = os.environ.get(
    "SYNTHESUS_IMAGE_DISK_CACHE",
    str(Path.home() / ".cache" / "synthesus" / "image_cache"),
)
_DISK_ENABLED = os.environ.get("SYNTHESUS_IMAGE_DISK_CACHE_OFF", "").strip() not in (
    "1", "true", "yes", "on",
)

STYLES = sorted(vpi.STYLES)
DETAILS = ("standard", "high")
VOCAB_VERSION = "image-cnc-paths-v1"
LOOKS = ("raw", "photo", "cinema", "vivid", "tv")


def renderable_vocabulary() -> list[str]:
    return list(_VOCAB)


def clear_image_cache(*, disk: bool = False) -> None:
    """Drop process cache; optionally wipe disk cache dir."""
    with _cache_lock:
        _cache.clear()
    if disk and _DISK_CACHE and os.path.isdir(_DISK_CACHE):
        for name in os.listdir(_DISK_CACHE):
            if name.endswith((".png", ".json")):
                try:
                    os.remove(os.path.join(_DISK_CACHE, name))
                except OSError:
                    pass


def cache_stats() -> dict[str, Any]:
    with _cache_lock:
        mem = len(_cache)
    disk_n = 0
    if _DISK_ENABLED and os.path.isdir(_DISK_CACHE):
        disk_n = sum(1 for n in os.listdir(_DISK_CACHE) if n.endswith(".png"))
    return {
        "size": mem,
        "max": _CACHE_MAX,
        "disk_enabled": _DISK_ENABLED,
        "disk_dir": _DISK_CACHE if _DISK_ENABLED else None,
        "disk_entries": disk_n,
    }


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
    detail: str,
    look: str = "raw",
    path_mode: bool = True,
) -> str:
    raw = (
        f"{VOCAB_VERSION}|{prompt.strip()}|{res}|{style}|{seed}|"
        f"{aspect:.4f}|{detail}|{look}|path={int(bool(path_mode))}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_get(key: str) -> Optional[dict[str, Any]]:
    with _cache_lock:
        item = _cache.get(key)
        if item is not None:
            _cache.move_to_end(key)
            return item
    if not _DISK_ENABLED:
        return None
    png_path = os.path.join(_DISK_CACHE, f"{key}.png")
    meta_path = os.path.join(_DISK_CACHE, f"{key}.json")
    if not (os.path.isfile(png_path) and os.path.isfile(meta_path)):
        return None
    try:
        with open(png_path, "rb") as f:
            png_bytes = f.read()
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        if len(png_bytes) < 64:
            return None
        item = {"png_bytes": png_bytes, "meta": meta, "disk": True}
        _cache_put(key, item, write_disk=False)
        return item
    except Exception:
        return None


def _cache_put(key: str, item: dict[str, Any], write_disk: bool = True) -> None:
    with _cache_lock:
        _cache[key] = item
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)
    if write_disk and _DISK_ENABLED:
        try:
            os.makedirs(_DISK_CACHE, exist_ok=True)
            png_path = os.path.join(_DISK_CACHE, f"{key}.png")
            meta_path = os.path.join(_DISK_CACHE, f"{key}.json")
            with open(png_path, "wb") as f:
                f.write(item["png_bytes"])
            meta = {k: v for k, v in item["meta"].items() if k != "path"}
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f)
        except Exception:
            pass  # disk cache is best-effort


def generate_image(
    prompt: str,
    out_path: str,
    res: int = 1024,
    style: str = "flat",
    seed: Optional[int] = None,
    aspect: float = 1.0,
    use_cache: bool = True,
    detail: str = "standard",
    look: str = "raw",
    path_mode: bool = True,
) -> dict[str, Any]:
    """Reason ``prompt`` into a scene graph and render it to ``out_path`` (PNG).

    look: raw | photo | cinema | vivid | tv — camera/TV ISP finish (not diffusion).
    style=photo also enables soft paint + photo look.
    path_mode: CNC path construction (G1/arc/offset math) for form.
    """
    if not prompt or not prompt.strip():
        raise ValueError("prompt is required")

    res = max(128, min(2048, int(res)))
    style = (style or "flat").lower().strip()
    look = (look or "raw").lower().strip()
    path_mode = bool(path_mode)
    if style == "photo":
        if look in ("raw", "", "none"):
            look = "photo"
        style = "soft"
    if style not in ("flat", "soft", "night", "photo"):
        style = "flat"
    detail = (detail or "standard").lower().strip()
    if detail not in DETAILS:
        detail = "standard"
    if look not in LOOKS:
        look = "raw"
    aspect = float(np.clip(float(aspect) if aspect else 1.0, 0.5, 2.0))
    if seed is not None:
        seed = int(seed)

    key = _cache_key(prompt, res, style, seed, aspect, detail, look, path_mode)
    t0 = time.time()

    if use_cache:
        hit = _cache_get(key)
        if hit is not None:
            with open(out_path, "wb") as f:
                f.write(hit["png_bytes"])
            meta = dict(hit["meta"])
            meta["path"] = out_path
            meta["cache_hit"] = True
            meta["cache_source"] = "disk" if hit.get("disk") else "memory"
            meta["latency_ms"] = round((time.time() - t0) * 1000.0, 2)
            return meta

    s = _imagination()
    paint_style = "soft" if style == "photo" else style
    if paint_style not in ("flat", "soft", "night"):
        paint_style = "soft" if look != "raw" else "flat"
    doc, horizon = vpi.pattern_document(
        prompt,
        s["imag"],
        s["vidx"],
        s["E"],
        seed=seed,
        style=paint_style,
        path_mode=path_mode,
    )
    vpi.render_doc(
        doc,
        horizon,
        res=res,
        out=out_path,
        style=paint_style,
        aspect=aspect,
        seed=seed,
        detail=detail,
        look=look,
        path_mode=path_mode,
    )
    entities = [
        p.get("entity") for p in doc if isinstance(p, dict) and p.get("entity")
    ]
    roles = sorted({p.get("role") for p in doc if p.get("role")})
    path_built = sum(1 for p in doc if p.get("construction") == "cnc_paths")
    path_ops: list[str] = []
    for p in doc:
        for op in (p.get("path_ops") or [])[:8]:
            path_ops.append(op)
        if len(path_ops) >= 24:
            break

    with open(out_path, "rb") as f:
        png_bytes = f.read()
    if len(png_bytes) < 64:
        raise RuntimeError("render produced empty/invalid PNG")

    engine_bits = ["synthesus_vsa_geometric"]
    if path_mode and path_built:
        engine_bits.append("cnc_paths")
    if look not in ("raw", "none", "off"):
        engine_bits.append("camera_isp")

    meta: dict[str, Any] = {
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
        "detail": detail,
        "look": look,
        "path_mode": path_mode,
        "path_entities": path_built,
        "path_ops_sample": path_ops[:16],
        "seed": seed,
        "aspect": aspect,
        "cache_hit": False,
        "cache_source": None,
        "engine": "+".join(engine_bits),
        "bytes": len(png_bytes),
        "isp": getattr(vpi.render_doc, "last_isp_meta", None),
    }
    try:
        from PIL import Image as _Im
        with _Im.open(out_path) as im:
            meta["width"], meta["height"] = im.size
    except Exception:
        pass

    meta["latency_ms"] = round((time.time() - t0) * 1000.0, 2)

    if use_cache:
        _cache_put(
            key,
            {
                "png_bytes": png_bytes,
                "meta": {k: v for k, v in meta.items() if k != "path"},
            },
        )

    return meta


def generate_variations(
    prompt: str,
    n: int = 4,
    res: int = 512,
    style: str = "soft",
    base_seed: Optional[int] = None,
    aspect: float = 1.0,
    detail: str = "standard",
    use_cache: bool = True,
    look: str = "photo",
    path_mode: bool = True,
) -> list[dict[str, Any]]:
    """Render N variations with different seeds. Returns list of metas (+ png on path)."""
    n = max(1, min(8, int(n)))
    if base_seed is None:
        h = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:8]
        base_seed = int(h, 16) % (2**31 - 1)
    results = []
    tmpdir = tempfile.mkdtemp(prefix="synth_img_var_")
    try:
        for i in range(n):
            seed = int(base_seed) + i * 9973
            out = os.path.join(tmpdir, f"v{i}.png")
            meta = generate_image(
                prompt,
                out,
                res=res,
                style=style,
                seed=seed,
                aspect=aspect,
                use_cache=use_cache,
                detail=detail,
                look=look,
                path_mode=path_mode,
            )
            with open(out, "rb") as f:
                png = f.read()
            import base64
            m = dict(meta)
            m["image_base64"] = base64.b64encode(png).decode("ascii")
            m["mime_type"] = "image/png"
            m["variation_index"] = i
            results.append(m)
    finally:
        for name in os.listdir(tmpdir):
            try:
                os.remove(os.path.join(tmpdir, name))
            except OSError:
                pass
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass
    return results


if __name__ == "__main__":
    out = os.path.join(tempfile.gettempdir(), "synth_image_service_test.png")
    clear_image_cache()
    meta = generate_image(
        "a house and a tree on green grass under a blue sky with a sun and a star",
        out,
        res=512,
        style="soft",
        seed=3,
        detail="high",
    )
    ok = os.path.exists(out) and os.path.getsize(out) > 1000
    print("meta:", {k: meta[k] for k in meta if k != "path"})
    print("PNG written:", ok, os.path.getsize(out) if ok else 0)
    meta2 = generate_image(
        "a house and a tree on green grass under a blue sky with a sun and a star",
        out + ".2.png",
        res=512,
        style="soft",
        seed=3,
        detail="high",
    )
    print("cache_hit:", meta2.get("cache_hit"), "source:", meta2.get("cache_source"))
    vars_ = generate_variations("a boat on a river under a sky", n=2, res=256, style="soft")
    print("variations:", len(vars_), "seeds", [v.get("seed") for v in vars_])
    assert ok and meta2.get("cache_hit") is True
