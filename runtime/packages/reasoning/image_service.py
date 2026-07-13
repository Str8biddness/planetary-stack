"""Synthesus image generation service (SI, not AI) — image-wow.

VSA / pattern-geometric text-to-image: text → resolution-free scene graph → HD
raster. Deterministic, CPU-only, no diffusion.

Wow layer:
  - process LRU + optional disk cache (survives restarts)
  - detail: draft | standard | high (draft = fast preview, no pocket)
  - variations: N seeds in one call
  - style / seed / aspect knobs
  - shared scene graph + parallel multi-frame (multiview / orbit / time)
  - scene_plan: rules (+ optional LLM) compile synonyms/composites → SI graph
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
import uuid
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
DETAILS = ("draft", "standard", "high")
# Bump when SHAPES, path raster, ISP, or materials change — invalidates disk/memory cache.
ENGINE_VERSION = "si-image-v6.1-workshop"
VOCAB_VERSION = ENGINE_VERSION  # alias for API meta field
LOOKS = ("raw", "photo", "cinema", "vivid", "tv")
GRADES = ("none", "warm", "cool", "contrast", "fade", "vivid")


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
    yaw_deg: float = 0.0,
    pitch_deg: float = 0.0,
    time_of_day: Optional[float] = None,
    plan_fp: str = "",
    enhance: str = "none",
    enhance_strength: float = 0.55,
) -> str:
    """Hash all knobs that change the PNG bytes (incl. post-raster enhance).

    FIX (Claude review): omitting enhance caused cache collisions — same prompt
    with enhance=none vs si_detail returned the un-enhanced image on hit.
    """
    tod = "none" if time_of_day is None else f"{float(time_of_day):.4f}"
    enh = (enhance or "none").lower().strip() or "none"
    if enh in ("off", "false", "0"):
        enh = "none"
    try:
        estr = f"{float(enhance_strength):.4f}"
    except (TypeError, ValueError):
        estr = "0.5500"
    raw = (
        f"engine={ENGINE_VERSION}|{prompt.strip()}|{res}|{style}|{seed}|"
        f"{aspect:.4f}|{detail}|{look}|path={int(bool(path_mode))}|"
        f"yaw={float(yaw_deg):.3f}|pitch={float(pitch_deg):.3f}|t={tod}|"
        f"plan={plan_fp or 'none'}|"
        f"enh={enh}|estr={estr}"
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
    res: int = 512,
    style: str = "flat",
    seed: Optional[int] = None,
    aspect: float = 1.0,
    use_cache: bool = True,
    detail: str = "standard",
    look: str = "raw",
    path_mode: bool = True,
    preset: Optional[str] = None,
    yaw_deg: float = 0.0,
    time_of_day: Optional[float] = None,
    pitch_deg: float = 0.0,
    return_level: bool = False,
    scene_doc: Optional[list] = None,
    scene_horizon: Optional[float] = None,
    compile_plan: bool = True,
    use_llm_plan: Optional[bool] = None,
    scene_plan: Optional[dict] = None,
    return_plan: bool = True,
    keep_session: bool = True,
    scene_id: Optional[str] = None,
    grade: str = "none",
    edit_text: str = "",
    edit_vignette: float = 0.0,
    enhance: str = "none",
    enhance_strength: float = 0.55,
) -> dict[str, Any]:
    """Reason ``prompt`` into a scene graph and render it to ``out_path`` (PNG).

    look: raw | photo | cinema | vivid | tv — camera/TV ISP finish (not diffusion).
    style=photo also enables soft paint + photo look.
    path_mode: CNC path construction (G1/arc/offset math) for form.
    preset: optional cinematic pack id (scene_presets) fills blanks.
    yaw_deg/pitch_deg: camera orbit/tilt (parallax by Z). time_of_day: 0..1 sun path.
    return_level: attach serializable SI level JSON object for world export.
    scene_doc/scene_horizon: optional prebuilt graph (shared across multiview/orbit frames).
    compile_plan: run scene_plan compiler (synonyms + composite puzzle pieces).
    use_llm_plan: optional LLM enrich (None = env SYNTHESUS_IMAGE_LLM_PLAN).
    scene_plan: precomputed plan dict (skips compile when provided).
    keep_session: store graph in image_session for multi-pass re-render.
    grade/edit_text/edit_vignette: Photoshop-lite post-raster (picture_edit).
    enhance: none | si_detail | si_upscale2 | realesrgan — post-raster polish
      (SI graph remains stock; realesrgan is optional local neural on the raster).
    """
    # Apply cinematic preset pack (fills missing knobs only)
    if preset:
        try:
            import scene_presets as _sp
            merged = _sp.apply_preset_to_request({
                "preset": preset,
                "prompt": prompt,
                "style": style,
                "look": look,
                "detail": detail,
                "path_mode": path_mode,
                "aspect": aspect,
                "seed": seed,
                "resolution": res,
            })
            prompt = merged.get("prompt") or prompt
            style = merged.get("style") or style
            look = merged.get("look") or look
            detail = merged.get("detail") or detail
            path_mode = bool(merged.get("path_mode", path_mode))
            aspect = float(merged.get("aspect", aspect))
            if merged.get("seed") is not None and seed is None:
                seed = merged.get("seed")
            if merged.get("resolution"):
                res = int(merged.get("resolution"))
            preset = merged.get("preset") or preset
        except Exception:
            pass

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
    # Draft: keep detail token so raster/ISP can take the fast path (no pocket, light ISP)
    draft = detail == "draft"
    render_detail = detail  # "draft" | "standard" | "high" — vpi handles draft
    aspect = float(np.clip(float(aspect) if aspect else 1.0, 0.5, 2.0))
    if seed is not None:
        seed = int(seed)
    yaw_deg = float(np.clip(float(yaw_deg or 0.0), -60.0, 60.0))
    pitch_deg = float(np.clip(float(pitch_deg or 0.0), -35.0, 35.0))
    if time_of_day is not None:
        time_of_day = float(np.clip(float(time_of_day), 0.0, 1.0))

    # ── Scene plan: outer/inner compile → SI shapes (not diffusion) ──
    plan: Optional[dict[str, Any]] = scene_plan
    plan_fp = ""
    user_prompt = prompt
    si_prompt = prompt
    if plan is None and compile_plan and scene_doc is None:
        try:
            import scene_plan as _sp
            plan = _sp.compile_scene_plan(prompt, use_llm=use_llm_plan)
            si_prompt = (plan.get("si_prompt") or prompt).strip() or prompt
            plan_fp = _sp.plan_fingerprint(plan)
            cam = plan.get("camera") or {}
            if time_of_day is None and cam.get("time_of_day") is not None:
                time_of_day = float(np.clip(float(cam["time_of_day"]), 0.0, 1.0))
            # Mood from plan only fills soft defaults (never override explicit raw/cinema/tv)
            if look == "photo" and cam.get("look") in LOOKS:
                look = cam["look"]
            if cam.get("style") == "night" and style in ("soft", "flat", "photo"):
                style = "night"
        except Exception as pe:
            plan = {
                "version": "error",
                "source_prompt": prompt,
                "si_prompt": prompt,
                "construction": "native",
                "monologue": f"plan compile failed: {pe}",
                "outer_voice": "SI illustration (plan compiler unavailable).",
                "compile_steps": [f"plan_error:{type(pe).__name__}"],
                "source": "fallback",
                "llm_status": "error",
                "entities": [],
                "composites": [],
                "camera": {},
                "missing": [],
                "honesty": "si_construct",
                "not_diffusion": True,
            }
            si_prompt = prompt
    elif plan is not None:
        try:
            import scene_plan as _sp
            si_prompt = (plan.get("si_prompt") or prompt).strip() or prompt
            plan_fp = _sp.plan_fingerprint(plan)
        except Exception:
            si_prompt = plan.get("si_prompt") or prompt
            plan_fp = "given"

    enhance_norm = (enhance or "none").lower().strip() or "none"
    if enhance_norm in ("off", "false", "0"):
        enhance_norm = "none"
    try:
        enhance_strength_f = float(enhance_strength if enhance_strength is not None else 0.55)
    except (TypeError, ValueError):
        enhance_strength_f = 0.55

    # Fail LOUD before expensive render if neural enhance is requested but missing
    # (same honesty as piper voice — never return 200 implying realesrgan ran).
    if enhance_norm == "realesrgan":
        try:
            import si_enhance as _enh_pre
            st = _enh_pre.realesrgan_status()
            if not st.get("available"):
                raise RuntimeError(
                    "realesrgan_unavailable: "
                    + (st.get("note") or "install onnxruntime + place RealESRGAN x4 ONNX")
                )
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"realesrgan_unavailable: {e}") from e

    key = _cache_key(
        user_prompt, res, style, seed, aspect, detail, look, path_mode,
        yaw_deg, pitch_deg, time_of_day, plan_fp=plan_fp,
        enhance=enhance_norm,
        enhance_strength=enhance_strength_f,
    )
    t0 = time.time()

    if use_cache and scene_doc is None:
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
    if scene_doc is not None and scene_horizon is not None:
        import copy
        doc = copy.deepcopy(scene_doc)
        horizon = float(scene_horizon)
    else:
        doc, horizon = vpi.pattern_document(
            si_prompt,
            s["imag"],
            s["vidx"],
            s["E"],
            seed=seed,
            style=paint_style,
            path_mode=path_mode,
        )
        # Inject composite puzzle pieces from plan
        if plan and (plan.get("composites") or plan.get("machines")):
            try:
                import scene_plan as _sp
                doc = _sp.inject_composites(
                    doc, plan, horizon, seed=seed, path_mode=path_mode,
                )
            except Exception:
                pass
    camera_meta = None
    if abs(yaw_deg) > 1e-6 or abs(pitch_deg) > 1e-6 or time_of_day is not None:
        try:
            import world_camera as _wc
            doc, camera_meta = _wc.project_view(
                doc,
                horizon=horizon,
                yaw_deg=yaw_deg,
                pitch_deg=pitch_deg,
                time_of_day=time_of_day,
            )
            if camera_meta.get("horizon") is not None:
                horizon = float(camera_meta["horizon"])
            if camera_meta.get("style_hint") == "night":
                paint_style = "night"
            if time_of_day is not None and look not in ("raw", "none", "off"):
                # gentle look nudge from time (does not override explicit cinema/tv if set)
                if look in ("photo", "soft", "flat"):
                    look = _wc.look_for_time(time_of_day, default_look=look)
        except Exception:
            camera_meta = {"error": "world_camera_unavailable"}
    # Re-attach paths after view projection if path_mode (draft keeps contours, skips pocket)
    if path_mode:
        try:
            import cnc_paths as _cnc
            for i, prim in enumerate(doc):
                if prim.get("role") in (
                    "house", "building", "triangle", "tree", "bush", "person",
                    "fence", "boat", "flower", "bridge", "disc", "disc_top",
                    "star_top", "cloud_top",
                ):
                    ps = _cnc.paths_for_primitive(prim, seed=int(seed or 0) + i * 17)
                    if ps:
                        if draft:
                            for pth in ps:
                                pth.meta["no_pocket"] = True
                        prim["paths"] = ps
                        prim["path_ops"] = _cnc.path_provenance(ps)
                        prim["construction"] = "cnc_paths"
        except Exception:
            pass
    if draft and path_mode:
        for prim in doc:
            for pth in prim.get("paths") or []:
                pth.meta["no_pocket"] = True
    # Stamp lathe prims with yaw for revolution foreshortening
    if abs(yaw_deg) > 1e-3:
        for p in doc:
            if isinstance(p, dict) and p.get("role") == "lathe":
                p["yaw_deg"] = yaw_deg
    vpi.render_doc(
        doc,
        horizon,
        res=res,
        out=out_path,
        style=paint_style,
        aspect=aspect,
        seed=seed,
        detail=render_detail,
        look=look,
        path_mode=path_mode,
        camera_yaw=yaw_deg,
    )
    # Photoshop-lite post-raster (does not change scene graph)
    picture_meta = None
    grade = (grade or "none").lower().strip()
    if grade not in GRADES:
        grade = "none"
    if grade != "none" or (edit_text and str(edit_text).strip()) or float(edit_vignette or 0) > 0:
        try:
            import picture_edit as _pe
            from PIL import Image as _Im
            arr = np.asarray(_Im.open(out_path).convert("RGB"), dtype=np.float32) / 255.0
            edited = _pe.edit_image(
                arr,
                grade=grade,
                vignette=float(edit_vignette or 0),
                text=str(edit_text or ""),
            )
            _Im.fromarray((edited["image"] * 255).astype(np.uint8)).save(out_path)
            picture_meta = edited.get("meta")
        except Exception as pe:
            picture_meta = {"error": str(pe), "construction": "picture_edit"}

    # Post-raster enhance (SI detail / optional local Real-ESRGAN). Graph stock unchanged.
    enhance_meta = None
    enhance = enhance_norm
    enhance_strength = enhance_strength_f
    if enhance and enhance not in ("none", "off", "false", "0"):
        try:
            import si_enhance as _enh
            enhance_meta = _enh.enhance_file(
                out_path,
                mode=enhance,
                strength=float(enhance_strength),
            )
            if isinstance(enhance_meta, dict):
                enhance_meta.setdefault("enhance_applied", enhance)
                enhance_meta.setdefault("enhance_requested", enhance)
                enhance_meta.setdefault("ok", True)
        except Exception as ee:
            # realesrgan: never soft-degrade to unenhanced 200 (Claude review FIX 2)
            if enhance == "realesrgan" or "realesrgan_unavailable" in str(ee):
                raise RuntimeError(
                    "realesrgan_unavailable: " + str(ee)
                ) from ee
            # si_detail / si_upscale2 unexpected failures: surface in meta, keep SI raster
            enhance_meta = {
                "enhance": enhance,
                "enhance_requested": enhance,
                "enhance_applied": "none",
                "enhance_error": str(ee),
                "error": str(ee),
                "ok": False,
                "note": "Enhance failed — SI raster left unenhanced (no silent neural substitute)",
            }

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
        "engine_version": ENGINE_VERSION,
        "style": style,
        "detail": detail,
        "look": look,
        "path_mode": path_mode,
        "path_entities": path_built,
        "path_ops_sample": path_ops[:16],
        "preset": preset,
        "seed": seed,
        "aspect": aspect,
        "yaw_deg": yaw_deg,
        "pitch_deg": pitch_deg,
        "time_of_day": time_of_day,
        "camera": camera_meta,
        "cache_hit": False,
        "cache_source": None,
        "engine": "+".join(engine_bits + (["world_camera"] if camera_meta else [])),
        "bytes": len(png_bytes),
        "isp": getattr(vpi.render_doc, "last_isp_meta", None),
        "depth": getattr(vpi.render_doc, "last_depth_stats", None),
        "user_prompt": user_prompt,
        "si_prompt": si_prompt,
        "construction": (plan or {}).get("construction"),
        "outer_voice": (plan or {}).get("outer_voice"),
        "monologue": (plan or {}).get("monologue"),
        "not_diffusion": True,
        "stock": "scene_graph",
        "picture_edit": picture_meta,
        "enhance": enhance_meta,
    }
    if plan and return_plan:
        try:
            import scene_plan as _sp
            meta["scene_plan"] = _sp.public_plan_view(plan, full=False)
        except Exception:
            meta["scene_plan"] = {
                "construction": plan.get("construction"),
                "si_prompt": plan.get("si_prompt"),
                "outer_voice": plan.get("outer_voice"),
            }
    composite_n = sum(1 for p in doc if p.get("construction") == "plan_composite")
    if composite_n:
        meta["composite_parts"] = composite_n
        if "plan_composite" not in (meta.get("engine") or ""):
            meta["engine"] = (meta.get("engine") or "") + "+plan_composite"
    lathe_n = sum(1 for p in doc if p.get("role") == "lathe" or p.get("machine") == "lathe")
    extrude_n = sum(1 for p in doc if p.get("role") == "extrude" or p.get("machine") == "extrude")
    if lathe_n:
        meta["lathe_parts"] = lathe_n
        meta["engine"] = (meta.get("engine") or "") + "+lathe"
    if extrude_n:
        meta["extrude_parts"] = extrude_n
        meta["engine"] = (meta.get("engine") or "") + "+extrude"
    if picture_meta and not picture_meta.get("error"):
        meta["engine"] = (meta.get("engine") or "") + "+picture_edit"

    # Multi-pass session: keep graph stock for later passes
    if keep_session:
        try:
            import image_session as _sess
            import copy
            knobs = {
                "style": style, "look": look, "detail": detail,
                "path_mode": path_mode, "aspect": aspect, "res": res,
                "yaw_deg": yaw_deg, "pitch_deg": pitch_deg,
                "time_of_day": time_of_day, "grade": grade,
            }
            prec = {
                "kind": "pass" if scene_doc is not None else "render",
                "look": look,
                "yaw_deg": yaw_deg,
                "time_of_day": time_of_day,
                "grade": grade,
            }
            if scene_id and _sess.get_session(scene_id):
                # Update knobs / pass log; keep original scene_doc stock unless first build
                fields = {"knobs": knobs, "pass_record": prec}
                if scene_doc is None:
                    fields.update(
                        plan=plan,
                        scene_doc=copy.deepcopy(doc),
                        horizon=horizon,
                        prompt=user_prompt,
                        seed=seed,
                    )
                _sess.update_session(scene_id, **fields)
                meta["scene_id"] = scene_id
            elif scene_doc is None:
                sid = _sess.create_session(
                    plan=plan,
                    scene_doc=copy.deepcopy(doc),
                    horizon=horizon,
                    prompt=user_prompt,
                    seed=seed,
                    knobs=knobs,
                )
                _sess.update_session(sid, pass_record=prec)
                meta["scene_id"] = sid
            elif scene_id:
                meta["scene_id"] = scene_id
        except Exception:
            pass
    try:
        from PIL import Image as _Im
        with _Im.open(out_path) as im:
            meta["width"], meta["height"] = im.size
    except Exception:
        pass

    meta["latency_ms"] = round((time.time() - t0) * 1000.0, 2)

    if return_level:
        try:
            import level_export as _le
            meta["level"] = _le.build_level(
                prompt, doc, horizon,
                seed=seed, camera=camera_meta, style=style, look=look,
                path_mode=path_mode, preset=preset,
            )
        except Exception as le:
            meta["level_error"] = str(le)

    if use_cache and not return_level:
        # Don't cache huge level payloads in the small LRU by default
        _cache_put(
            key,
            {
                "png_bytes": png_bytes,
                "meta": {k: v for k, v in meta.items() if k not in ("path", "level")},
            },
        )
    elif use_cache:
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
    preset: Optional[str] = None,
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
                preset=preset if i == 0 else None,
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


def _build_base_scene(prompt, seed, style, path_mode, detail, plan=None, use_llm_plan=None):
    """Shared scene graph for multi-frame sequences (built once).

    Compiles scene_plan (synonyms + composites) then builds the document.
    ``detail`` reserved for per-frame draft pocket skipping in generate_image.
    """
    _ = detail
    if plan is None:
        try:
            import scene_plan as _sp
            plan = _sp.compile_scene_plan(prompt, use_llm=use_llm_plan)
        except Exception:
            plan = None
    si_prompt = (plan or {}).get("si_prompt") or prompt
    s = _imagination()
    paint_style = "soft" if style == "photo" else style
    if paint_style not in ("flat", "soft", "night"):
        paint_style = "soft"
    doc, horizon = vpi.pattern_document(
        si_prompt,
        s["imag"],
        s["vidx"],
        s["E"],
        seed=seed,
        style=paint_style,
        path_mode=path_mode,
    )
    if plan and (plan.get("composites") or plan.get("machines")):
        try:
            import scene_plan as _sp
            doc = _sp.inject_composites(doc, plan, horizon, seed=seed, path_mode=path_mode)
        except Exception:
            pass
    return doc, horizon, plan


def generate_multiview(
    prompt: str,
    n: int = 3,
    yaw_span: float = 30.0,
    res: int = 512,
    style: str = "photo",
    seed: Optional[int] = None,
    aspect: float = 1.0,
    detail: str = "high",
    use_cache: bool = True,
    look: str = "photo",
    path_mode: bool = True,
    preset: Optional[str] = None,
    time_of_day: Optional[float] = None,
    pitch_deg: float = 0.0,
) -> list[dict[str, Any]]:
    """Same scene graph, multiple camera yaws (orbit). Parallel frames when n>1."""
    import base64
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import world_camera as wc

    yaws = wc.yaw_schedule(n=n, span_deg=yaw_span)
    # Apply preset once to knobs
    if preset:
        try:
            import scene_presets as _sp
            merged = _sp.apply_preset_to_request({
                "preset": preset, "prompt": prompt, "style": style, "look": look,
                "detail": detail, "path_mode": path_mode, "aspect": aspect, "seed": seed,
                "resolution": res,
            })
            prompt = merged.get("prompt") or prompt
            style = merged.get("style") or style
            look = merged.get("look") or look
            detail = merged.get("detail") or detail
            path_mode = bool(merged.get("path_mode", path_mode))
            aspect = float(merged.get("aspect", aspect))
            if seed is None and merged.get("seed") is not None:
                seed = merged.get("seed")
        except Exception:
            pass

    base_doc, base_h, base_plan = _build_base_scene(prompt, seed, style, path_mode, detail)
    tmpdir = tempfile.mkdtemp(prefix="synth_img_mv_")
    results: list[Optional[dict]] = [None] * len(yaws)

    def _one(i_yaw):
        i, yaw = i_yaw
        out = os.path.join(tmpdir, f"mv{i}.png")
        meta = generate_image(
            prompt, out, res=res, style=style, seed=seed, aspect=aspect,
            use_cache=use_cache, detail=detail, look=look, path_mode=path_mode,
            yaw_deg=yaw, time_of_day=time_of_day, pitch_deg=pitch_deg,
            scene_doc=base_doc, scene_horizon=base_h, scene_plan=base_plan,
            compile_plan=False,
        )
        with open(out, "rb") as f:
            png = f.read()
        m = dict(meta)
        m["image_base64"] = base64.b64encode(png).decode("ascii")
        m["mime_type"] = "image/png"
        m["view_index"] = i
        m["yaw_deg"] = yaw
        return i, m

    try:
        workers = min(4, max(1, len(yaws)))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(_one, (i, y)) for i, y in enumerate(yaws)]
            for fut in as_completed(futs):
                i, m = fut.result()
                results[i] = m
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
    return [r for r in results if r is not None]


def generate_time_sequence(
    prompt: str,
    n: int = 4,
    t0: float = 0.1,
    t1: float = 0.95,
    res: int = 512,
    style: str = "photo",
    seed: Optional[int] = None,
    aspect: float = 1.0,
    detail: str = "high",
    use_cache: bool = True,
    look: str = "photo",
    path_mode: bool = True,
    preset: Optional[str] = None,
    yaw_deg: float = 0.0,
    pitch_deg: float = 0.0,
    as_gif: bool = False,
    gif_duration_ms: int = 400,
    gif_format: str = "gif",
) -> list[dict[str, Any]]:
    """Same world, time-of-day axis (dawn→night). SI temporal sequence.

    If as_gif=True, appends a synthetic last result is NOT used — caller should
    use sequence_to_animation(results) or set attach_animation on API.
    """
    import base64
    import world_camera as wc

    times = wc.time_schedule(n=n, t0=t0, t1=t1)
    base_doc, base_h, base_plan = _build_base_scene(prompt, seed, style, path_mode, detail)
    results: list = [None] * len(times)
    tmpdir = tempfile.mkdtemp(prefix="synth_img_ts_")

    def _one(i_t):
        i, t = i_t
        out = os.path.join(tmpdir, f"t{i}.png")
        meta = generate_image(
            prompt, out, res=res, style=style, seed=seed, aspect=aspect,
            use_cache=use_cache, detail=detail, look=look, path_mode=path_mode,
            yaw_deg=yaw_deg, time_of_day=t, pitch_deg=pitch_deg,
            scene_doc=base_doc, scene_horizon=base_h, scene_plan=base_plan,
            compile_plan=False,
        )
        with open(out, "rb") as f:
            png = f.read()
        m = dict(meta)
        m["image_base64"] = base64.b64encode(png).decode("ascii")
        m["mime_type"] = "image/png"
        m["frame_index"] = i
        m["time_of_day"] = t
        return i, m

    try:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=min(4, max(1, len(times)))) as ex:
            futs = [ex.submit(_one, (i, t)) for i, t in enumerate(times)]
            for fut in as_completed(futs):
                i, m = fut.result()
                results[i] = m
        results = [r for r in results if r is not None]
        if as_gif and results:
            try:
                import gif_export as _ge
                anim = _ge.frames_to_data_url(
                    results, fmt=gif_format, duration_ms=gif_duration_ms
                )
                results[0]["animation"] = anim
            except Exception as ge:
                results[0]["animation_error"] = str(ge)
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


def sequence_to_animation(
    frames: list[dict[str, Any]],
    *,
    fmt: str = "gif",
    duration_ms: int = 400,
) -> dict[str, Any]:
    """Turn frame metas (with image_base64) into GIF/WebP data URL payload."""
    import gif_export as ge
    return ge.frames_to_data_url(frames, fmt=fmt, duration_ms=duration_ms)


def generate_orbit_day(
    prompt: str,
    n: int = 6,
    yaw_span: float = 40.0,
    t0: float = 0.12,
    t1: float = 0.95,
    res: int = 384,
    style: str = "photo",
    seed: Optional[int] = None,
    aspect: float = 1.5,
    detail: str = "high",
    use_cache: bool = True,
    look: str = "photo",
    path_mode: bool = True,
    preset: Optional[str] = None,
    pitch_deg: float = 0.0,
    as_gif: bool = True,
    gif_duration_ms: int = 280,
    gif_format: str = "gif",
) -> list[dict[str, Any]]:
    """Orbiting day: same SI world, yaw + time advance together → short cinematic GIF.

    Frame i uses yaw from schedule and time_of_day from schedule (locked world seed).
    """
    import base64
    import world_camera as wc

    n = max(2, min(12, int(n)))
    yaws = wc.yaw_schedule(n=n, span_deg=yaw_span)
    times = wc.time_schedule(n=n, t0=t0, t1=t1)
    base_doc, base_h, base_plan = _build_base_scene(prompt, seed, style, path_mode, detail)
    results: list = [None] * n
    tmpdir = tempfile.mkdtemp(prefix="synth_img_od_")

    def _one(i: int):
        out = os.path.join(tmpdir, f"od{i}.png")
        meta = generate_image(
            prompt, out, res=res, style=style, seed=seed, aspect=aspect,
            use_cache=use_cache, detail=detail, look=look, path_mode=path_mode,
            yaw_deg=yaws[i], time_of_day=times[i], pitch_deg=pitch_deg,
            scene_doc=base_doc, scene_horizon=base_h, scene_plan=base_plan,
            compile_plan=False,
        )
        with open(out, "rb") as f:
            png = f.read()
        m = dict(meta)
        m["image_base64"] = base64.b64encode(png).decode("ascii")
        m["mime_type"] = "image/png"
        m["frame_index"] = i
        m["yaw_deg"] = yaws[i]
        m["time_of_day"] = times[i]
        m["orbit_day"] = True
        return i, m

    try:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=min(4, max(1, n))) as ex:
            futs = [ex.submit(_one, i) for i in range(n)]
            for fut in as_completed(futs):
                i, m = fut.result()
                results[i] = m
        results = [r for r in results if r is not None]
        if as_gif and results:
            try:
                import gif_export as _ge
                anim = _ge.frames_to_data_url(
                    results, fmt=gif_format, duration_ms=gif_duration_ms
                )
                anim["kind"] = "orbit_day"
                results[0]["animation"] = anim
            except Exception as ge:
                results[0]["animation_error"] = str(ge)
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


def export_level(
    prompt: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Build SI level JSON for a prompt (no PNG required)."""
    import level_export as le
    return le.build_level_from_prompt(prompt, **kwargs)


def run_pass_playlist(
    scene_id: str,
    playlist: str = "finish",
    *,
    res: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Run a named multi-pass finish job on scene stock; returns list of frame metas."""
    import base64
    import image_session as sess

    steps = sess.PLAYLISTS.get(playlist) or sess.PLAYLISTS["finish"]
    results = []
    for i, step in enumerate(steps):
        out = os.path.join(
            tempfile.gettempdir(), f"synth_pl_{scene_id[:8]}_{i}.png"
        )
        try:
            meta = apply_scene_pass(
                scene_id,
                out,
                yaw_deg=step.get("yaw_deg"),
                time_of_day=step.get("time_of_day"),
                look=step.get("look"),
                detail=step.get("detail"),
                res=res,
                grade=step.get("grade"),
                style=step.get("style"),
            )
            with open(out, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            m = dict(meta)
            m["playlist_step"] = step.get("label") or f"step{i}"
            m["image_base64"] = b64
            m["mime_type"] = "image/png"
            results.append(m)
        finally:
            try:
                os.remove(out)
            except OSError:
                pass
    return results


def apply_scene_pass(
    scene_id: str,
    out_path: str,
    *,
    yaw_deg: Optional[float] = None,
    pitch_deg: Optional[float] = None,
    time_of_day: Optional[float] = None,
    look: Optional[str] = None,
    detail: Optional[str] = None,
    res: Optional[int] = None,
    grade: Optional[str] = None,
    edit_text: Optional[str] = None,
    edit_vignette: Optional[float] = None,
    style: Optional[str] = None,
    enhance: Optional[str] = None,
    enhance_strength: Optional[float] = None,
) -> dict[str, Any]:
    """Re-render an existing session graph with new view/ISP/picture-edit knobs.

    Does not re-compile language from zero — multi-pass on scene stock.
    """
    import image_session as sess

    s = sess.get_session(scene_id)
    if not s or not s.get("scene_doc"):
        raise ValueError(f"unknown or empty scene_id: {scene_id}")
    kn = dict(s.get("knobs") or {})
    return generate_image(
        s.get("prompt") or "scene",
        out_path,
        res=int(res if res is not None else kn.get("res") or 512),
        style=style if style is not None else kn.get("style") or "soft",
        seed=s.get("seed"),
        aspect=float(kn.get("aspect") or 1.0),
        use_cache=False,
        detail=detail if detail is not None else kn.get("detail") or "standard",
        look=look if look is not None else kn.get("look") or "photo",
        path_mode=bool(kn.get("path_mode", True)),
        yaw_deg=float(yaw_deg if yaw_deg is not None else kn.get("yaw_deg") or 0.0),
        pitch_deg=float(pitch_deg if pitch_deg is not None else kn.get("pitch_deg") or 0.0),
        time_of_day=(
            time_of_day if time_of_day is not None else kn.get("time_of_day")
        ),
        scene_doc=s.get("scene_doc"),
        scene_horizon=float(s.get("horizon") or 0.66),
        scene_plan=s.get("plan"),
        compile_plan=False,
        keep_session=True,
        scene_id=scene_id,
        grade=grade if grade is not None else kn.get("grade") or "none",
        edit_text=edit_text if edit_text is not None else "",
        edit_vignette=float(edit_vignette if edit_vignette is not None else 0.0),
        enhance=enhance if enhance is not None else kn.get("enhance") or "none",
        enhance_strength=float(
            enhance_strength if enhance_strength is not None else kn.get("enhance_strength") or 0.55
        ),
        return_plan=True,
    )


def execute_image_request(
    params: dict[str, Any],
    progress: Optional[Any] = None,
) -> dict[str, Any]:
    """Full SI image request (sync). Used by API and async job workers.

    params keys mirror ImageRequest + normalized fields.
    progress: optional callable(message, fraction 0..1)
    """
    import base64
    import time as _time

    def _p(msg: str, frac: float = 0.0) -> None:
        if callable(progress):
            try:
                progress(msg, frac)
            except Exception:
                pass

    # Multi-pass: re-render existing scene stock
    scene_id_in = params.get("scene_id")
    pass_only = bool(params.get("pass_only") or params.get("from_scene"))
    playlist = (params.get("playlist") or "").strip().lower()
    if scene_id_in and playlist:
        _p("playlist", 0.15)
        frames = run_pass_playlist(
            str(scene_id_in),
            playlist=playlist,
            res=params.get("resolution"),
        )
        primary = frames[0] if frames else {}
        return {
            "ok": True,
            "playlist": playlist,
            "playlist_frames": frames,
            "image_base64": primary.get("image_base64", ""),
            "mime_type": "image/png",
            "scene_id": scene_id_in,
            "engine": primary.get("engine"),
            "not_diffusion": True,
            "stock": "scene_graph",
            "frame_count": len(frames),
        }

    # Level import → session + optional first render
    if params.get("level") and isinstance(params.get("level"), dict):
        import image_session as _sess
        sid = _sess.session_from_level(params["level"], knobs={
            "res": params.get("resolution") or 512,
            "look": params.get("look") or "photo",
            "style": params.get("style") or "soft",
            "detail": params.get("detail") or "standard",
        })
        if params.get("pass_only") or not (params.get("prompt") or "").strip():
            params = dict(params)
            params["scene_id"] = sid
            params["pass_only"] = True
            params["prompt"] = params.get("prompt") or "level"
            out = execute_image_request(params, progress=progress)
            out["scene_id"] = sid
            out["from_level"] = True
            return out
        params = dict(params)
        params["scene_id"] = sid

    if scene_id_in and pass_only:
        _p("scene_pass", 0.2)
        out_path = os.path.join(tempfile.gettempdir(), f"synth_pass_{uuid.uuid4().hex[:12]}.png")
        try:
            meta = apply_scene_pass(
                str(scene_id_in),
                out_path,
                yaw_deg=params.get("yaw_deg"),
                pitch_deg=params.get("pitch_deg"),
                time_of_day=params.get("time_of_day"),
                look=params.get("look"),
                detail=params.get("detail"),
                res=params.get("resolution"),
                grade=params.get("grade"),
                edit_text=params.get("edit_text"),
                edit_vignette=params.get("edit_vignette"),
                style=params.get("style"),
            )
            with open(out_path, "rb") as f:
                png_b64 = base64.b64encode(f.read()).decode("ascii")
        finally:
            try:
                os.remove(out_path)
            except OSError:
                pass
        return {
            "ok": True,
            "engine": meta.get("engine"),
            "prompt": meta.get("user_prompt") or meta.get("prompt"),
            "resolution": meta.get("resolution"),
            "width": meta.get("width"),
            "height": meta.get("height"),
            "style": meta.get("style"),
            "detail": meta.get("detail"),
            "look": meta.get("look"),
            "image_base64": png_b64,
            "mime_type": "image/png",
            "scene_id": meta.get("scene_id") or scene_id_in,
            "scene_plan": meta.get("scene_plan"),
            "outer_voice": meta.get("outer_voice"),
            "monologue": meta.get("monologue"),
            "construction": meta.get("construction"),
            "si_prompt": meta.get("si_prompt"),
            "picture_edit": meta.get("picture_edit"),
            "not_diffusion": True,
            "stock": "scene_graph",
            "pass": True,
            "entities": meta.get("entities", []),
            "entity_count": meta.get("entity_count", 0),
            "latency_ms": meta.get("latency_ms"),
            "engine_version": meta.get("engine_version"),
        }

    prompt = (params.get("prompt") or "").strip()
    if not prompt and not scene_id_in:
        raise ValueError("prompt is required")
    if not prompt and scene_id_in:
        # treat as pass
        params = dict(params)
        params["pass_only"] = True
        return execute_image_request(params, progress=progress)
    res = max(128, min(2048, int(params.get("resolution") or 512)))
    style = (params.get("style") or "soft").lower().strip()
    look = (params.get("look") or "photo").lower().strip()
    seed = params.get("seed")
    aspect = float(params.get("aspect") or 1.0)
    use_cache = bool(params.get("use_cache", True))
    detail = (params.get("detail") or "high").lower().strip()
    path_mode = bool(params.get("path_mode", True))
    preset = params.get("preset")
    yaw_deg = float(params.get("yaw_deg") or 0.0)
    pitch_deg = float(params.get("pitch_deg") or 0.0)
    time_of_day = params.get("time_of_day")
    n_var = max(1, min(8, int(params.get("variations") or 1)))
    n_views = max(1, min(8, int(params.get("views") or 1)))
    yaw_span = float(params.get("yaw_span") or 30.0)
    n_frames = max(1, min(8, int(params.get("frames") or 1)))
    as_gif = bool(params.get("as_gif", False))
    gif_format = (params.get("gif_format") or "gif").lower().strip()
    if gif_format not in ("gif", "webp"):
        gif_format = "gif"
    gif_duration_ms = int(params.get("gif_duration_ms") or 400)
    return_level = bool(params.get("return_level", False))
    orbit_day = bool(params.get("orbit_day", False))
    orbit_frames = max(2, min(12, int(params.get("orbit_frames") or 6)))
    compile_plan = bool(params.get("compile_plan", True))
    use_llm_plan = params.get("use_llm_plan")  # None | bool
    if isinstance(use_llm_plan, str):
        use_llm_plan = use_llm_plan.strip().lower() in ("1", "true", "yes", "on")
    return_plan = bool(params.get("return_plan", True))
    keep_session = bool(params.get("keep_session", True))
    grade = (params.get("grade") or "none")
    edit_text = params.get("edit_text") or ""
    edit_vignette = float(params.get("edit_vignette") or 0.0)
    enhance = (params.get("enhance") or "none")
    enhance_strength = float(params.get("enhance_strength") or 0.55)

    t0 = _time.time()
    _p("starting", 0.05)

    def _grid(items, kind: str) -> dict[str, Any]:
        primary = items[0]
        key = "variations" if kind == "seed" else (
            "views" if kind == "yaw" else ("frames" if kind in ("time", "orbit_day") else "items")
        )
        grid = []
        for v in items:
            grid.append({
                "image_base64": v.get("image_base64"),
                "entities": v.get("entities", []),
                "latency_ms": v.get("latency_ms"),
                "cache_hit": v.get("cache_hit"),
                "width": v.get("width"),
                "height": v.get("height"),
                "seed": v.get("seed"),
                "yaw_deg": v.get("yaw_deg"),
                "time_of_day": v.get("time_of_day"),
            })
        out = {
            "ok": True,
            "engine": primary.get("engine", "synthesus_vsa_geometric"),
            "prompt": prompt,
            "resolution": res,
            "width": primary.get("width"),
            "height": primary.get("height"),
            "style": style,
            "detail": detail,
            "look": look,
            "seed": primary.get("seed"),
            "aspect": aspect,
            "entities": primary.get("entities", []),
            "entity_count": primary.get("entity_count", 0),
            "roles": primary.get("roles", []),
            "renderable_vocabulary": renderable_vocabulary(),
            "cache_hit": bool(primary.get("cache_hit")),
            "cache_source": primary.get("cache_source"),
            "latency_ms": round((_time.time() - t0) * 1000.0, 1),
            "image_base64": primary.get("image_base64", ""),
            "mime_type": "image/png",
            "vocab_version": primary.get("vocab_version"),
            "isp": primary.get("isp"),
            "depth": primary.get("depth"),
            "camera": primary.get("camera"),
            "path_mode": path_mode,
            "path_entities": primary.get("path_entities"),
            "path_ops_sample": primary.get("path_ops_sample"),
            "preset": primary.get("preset") or preset,
            "yaw_deg": primary.get("yaw_deg", yaw_deg),
            "pitch_deg": primary.get("pitch_deg", pitch_deg),
            "time_of_day": primary.get("time_of_day", time_of_day),
            "grid_kind": kind,
            key: grid,
            "variations": grid if kind == "seed" else None,
        }
        if primary.get("animation"):
            out["animation"] = primary["animation"]
        for k in (
            "scene_plan", "outer_voice", "monologue", "construction",
            "si_prompt", "user_prompt", "composite_parts", "not_diffusion",
        ):
            if primary.get(k) is not None:
                out[k] = primary.get(k)
        return out

    if orbit_day:
        _p("orbit_day", 0.2)
        items = generate_orbit_day(
            prompt, orbit_frames, yaw_span if yaw_span else 40.0,
            0.12, 0.95, min(res, 512), style, seed, aspect, detail,
            use_cache, look, path_mode, preset, pitch_deg,
            True if as_gif or True else True, gif_duration_ms, gif_format,
        )
        payload = _grid(items, "orbit_day")
        payload["frames"] = [
            {
                "image_base64": v.get("image_base64"),
                "yaw_deg": v.get("yaw_deg"),
                "time_of_day": v.get("time_of_day"),
                "width": v.get("width"),
                "height": v.get("height"),
            }
            for v in items
        ]
        _p("done", 1.0)
        return payload

    if n_frames > 1:
        _p("time_sequence", 0.2)
        items = generate_time_sequence(
            prompt, n_frames, 0.1, 0.95, res, style, seed, aspect,
            detail, use_cache, look, path_mode, preset, yaw_deg, pitch_deg,
            as_gif, gif_duration_ms, gif_format,
        )
        _p("done", 1.0)
        return _grid(items, "time")

    if n_views > 1:
        _p("multiview", 0.2)
        items = generate_multiview(
            prompt, n_views, yaw_span, res, style, seed, aspect,
            detail, use_cache, look, path_mode, preset, time_of_day, pitch_deg,
        )
        payload = _grid(items, "yaw")
        if as_gif and items:
            try:
                payload["animation"] = sequence_to_animation(
                    items, fmt=gif_format, duration_ms=gif_duration_ms
                )
            except Exception as ge:
                payload["animation_error"] = str(ge)
        _p("done", 1.0)
        return payload

    if n_var > 1:
        _p("variations", 0.2)
        items = generate_variations(
            prompt, n_var, res, style, seed, aspect, detail,
            use_cache, look, path_mode, preset,
        )
        _p("done", 1.0)
        return _grid(items, "seed")

    _p("render", 0.3)
    out_path = os.path.join(tempfile.gettempdir(), f"synth_img_{uuid.uuid4().hex[:12]}.png")
    try:
        meta = generate_image(
            prompt, out_path, res, style, seed, aspect, use_cache, detail,
            look, path_mode, preset, yaw_deg, time_of_day, pitch_deg, return_level,
            compile_plan=compile_plan,
            use_llm_plan=use_llm_plan,
            return_plan=return_plan,
            keep_session=keep_session,
            grade=grade,
            edit_text=edit_text,
            edit_vignette=edit_vignette,
            enhance=enhance,
            enhance_strength=enhance_strength,
        )
        with open(out_path, "rb") as f:
            png_b64 = base64.b64encode(f.read()).decode("ascii")
    finally:
        try:
            os.remove(out_path)
        except OSError:
            pass

    payload = {
        "ok": True,
        "engine": meta.get("engine", "synthesus_vsa_geometric"),
        "prompt": prompt,
        "resolution": res,
        "width": meta.get("width"),
        "height": meta.get("height"),
        "style": style,
        "detail": detail,
        "look": look,
        "seed": meta.get("seed", seed),
        "aspect": aspect,
        "entities": meta.get("entities", []),
        "entity_count": meta.get("entity_count", 0),
        "roles": meta.get("roles", []),
        "renderable_vocabulary": renderable_vocabulary(),
        "cache_hit": bool(meta.get("cache_hit")),
        "cache_source": meta.get("cache_source"),
        "latency_ms": round((_time.time() - t0) * 1000.0, 1),
        "image_base64": png_b64,
        "mime_type": "image/png",
        "vocab_version": meta.get("vocab_version"),
        "isp": meta.get("isp"),
        "depth": meta.get("depth"),
        "preset": meta.get("preset") or preset,
        "path_mode": path_mode,
        "path_entities": meta.get("path_entities"),
        "path_ops_sample": meta.get("path_ops_sample"),
        "yaw_deg": meta.get("yaw_deg", yaw_deg),
        "pitch_deg": meta.get("pitch_deg", pitch_deg),
        "time_of_day": meta.get("time_of_day", time_of_day),
        "camera": meta.get("camera"),
        "level": meta.get("level"),
        "scene_plan": meta.get("scene_plan"),
        "outer_voice": meta.get("outer_voice"),
        "monologue": meta.get("monologue"),
        "construction": meta.get("construction"),
        "si_prompt": meta.get("si_prompt"),
        "user_prompt": meta.get("user_prompt", prompt),
        "composite_parts": meta.get("composite_parts"),
        "lathe_parts": meta.get("lathe_parts"),
        "extrude_parts": meta.get("extrude_parts"),
        "picture_edit": meta.get("picture_edit"),
        "enhance": meta.get("enhance"),
        "scene_id": meta.get("scene_id"),
        "stock": "scene_graph",
        "not_diffusion": True,
        "engine_version": meta.get("engine_version"),
    }
    # Top-level enhance honesty (never imply a mode ran if it didn't)
    em = meta.get("enhance") if isinstance(meta.get("enhance"), dict) else None
    if em:
        payload["enhance_requested"] = em.get("enhance_requested") or em.get("enhance") or enhance
        payload["enhance_applied"] = em.get("enhance_applied") or (
            em.get("enhance") if em.get("ok") is not False and not em.get("error") else "none"
        )
        if em.get("enhance_error") or em.get("error"):
            payload["enhance_error"] = em.get("enhance_error") or em.get("error")
        if em.get("width"):
            payload["width"] = em["width"]
        if em.get("height"):
            payload["height"] = em["height"]
    else:
        payload["enhance_requested"] = enhance if enhance and enhance not in ("none", "off") else "none"
        payload["enhance_applied"] = (
            enhance if enhance and enhance not in ("none", "off", "false", "0") else "none"
        )
    _p("done", 1.0)
    return payload


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
