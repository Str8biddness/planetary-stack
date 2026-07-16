#!/usr/bin/env python3
"""
SI level export — scene graph as a portable mini-world JSON.
============================================================

Exports the constructed scene (entities, roles, layout, depth, camera, materials
hints) for:
  - re-render
  - virtual-world / game-style loaders
  - multi-agent handoff

Not a Unity package. Honest: SI construction dump, not a full engine scene.

Run: python packages/reasoning/level_export.py
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

LEVEL_SCHEMA = "synthesus.si_level.v1"


def _jsonable_prim(p: Dict[str, Any]) -> Dict[str, Any]:
    """Strip non-JSON path objects; keep layout + construction metadata."""
    out: Dict[str, Any] = {}
    skip = {"paths"}  # Path dataclasses not JSON
    for k, v in p.items():
        if k in skip:
            continue
        if k == "color" and isinstance(v, (list, tuple)):
            out[k] = [round(float(c), 4) for c in v]
        elif isinstance(v, (str, int, bool)) or v is None:
            out[k] = v
        elif isinstance(v, float):
            out[k] = round(v, 5)
        elif isinstance(v, (list, tuple)):
            try:
                out[k] = list(v)
            except Exception:
                out[k] = str(v)
        elif isinstance(v, dict):
            out[k] = {sk: sv for sk, sv in v.items() if not callable(sv)}
        else:
            # skip Path and other objects
            continue
    # ensure depth
    if "depth_z" not in out:
        try:
            import depth_buffer as db
            out["depth_z"] = round(db.depth_for_primitive(p), 5)
        except Exception:
            pass
    return out


def build_level(
    prompt: str,
    doc: List[Dict[str, Any]],
    horizon: float = 0.66,
    *,
    seed: Optional[int] = None,
    camera: Optional[Dict[str, Any]] = None,
    style: str = "soft",
    look: str = "photo",
    path_mode: bool = True,
    preset: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a serializable SI level document from a pattern_document result."""
    entities = []
    for p in doc:
        if not isinstance(p, dict):
            continue
        entities.append(_jsonable_prim(p))

    # World AABB in normalized coords
    xs, zs = [], []
    for e in entities:
        for k in ("x", "cx", "x0", "x1"):
            if k in e and isinstance(e[k], (int, float)):
                xs.append(float(e[k]))
        if "depth_z" in e:
            zs.append(float(e["depth_z"]))

    level = {
        "schema": LEVEL_SCHEMA,
        "engine": "synthesus_si_construction",
        "not_diffusion": True,
        "created_unix": int(time.time()),
        "prompt": prompt,
        "preset": preset,
        "seed": seed,
        "style": style,
        "look": look,
        "path_mode": path_mode,
        "horizon": round(float(horizon), 5),
        "camera": camera or {"yaw_deg": 0.0, "pitch_deg": 0.0},
        "axes": ["x", "y", "z", "yaw", "pitch", "time"],
        "bounds": {
            "x_min": round(min(xs), 4) if xs else 0.0,
            "x_max": round(max(xs), 4) if xs else 1.0,
            "z_min": round(min(zs), 4) if zs else 0.0,
            "z_max": round(max(zs), 4) if zs else 1.0,
        },
        "entity_count": len(entities),
        "entities": entities,
        "notes": (
            "SI level dump: load entities by role/layout; re-render via image API "
            "or consume as a lightweight virtual-world blueprint."
        ),
    }
    if extra:
        level["extra"] = extra
    return level


def level_to_json(level: Dict[str, Any], indent: int = 2) -> str:
    return json.dumps(level, indent=indent, ensure_ascii=False)


def build_level_from_prompt(
    prompt: str,
    *,
    seed: Optional[int] = None,
    style: str = "soft",
    look: str = "photo",
    path_mode: bool = True,
    preset: Optional[str] = None,
    yaw_deg: float = 0.0,
    pitch_deg: float = 0.0,
    time_of_day: Optional[float] = None,
) -> Dict[str, Any]:
    """Convenience: pattern_document + world_camera → level JSON object."""
    import vsa_pipeline_image as vpi
    import world_camera as wc

    paint_style = "night" if style == "night" else "soft"
    if preset:
        try:
            import scene_presets as sp
            body = sp.apply_preset_to_request({
                "preset": preset, "prompt": prompt, "style": style, "look": look,
                "path_mode": path_mode, "seed": seed,
            })
            prompt = body.get("prompt") or prompt
            style = body.get("style") or style
            look = body.get("look") or look
            seed = body.get("seed", seed)
            preset = body.get("preset") or preset
        except Exception:
            pass

    doc, horizon = vpi.pattern_document(
        prompt, seed=seed, style=paint_style, path_mode=path_mode
    )
    cam_meta = None
    if abs(yaw_deg) > 1e-6 or abs(pitch_deg) > 1e-6 or time_of_day is not None:
        doc, cam_meta = wc.project_view(
            doc,
            horizon=horizon,
            yaw_deg=yaw_deg,
            pitch_deg=pitch_deg,
            time_of_day=time_of_day,
        )
        horizon = float(cam_meta.get("horizon", horizon))
    return build_level(
        prompt, doc, horizon,
        seed=seed, camera=cam_meta, style=style, look=look,
        path_mode=path_mode, preset=preset,
    )


def demo():
    lvl = build_level_from_prompt(
        "a house and a tree on grass under a sky with a sun",
        seed=3, yaw_deg=10, pitch_deg=-5,
    )
    print(level_to_json(lvl)[:500])
    print("entities", lvl["entity_count"], "schema", lvl["schema"])


if __name__ == "__main__":
    demo()
