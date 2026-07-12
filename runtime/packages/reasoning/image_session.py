#!/usr/bin/env python3
"""
SI image session store — multi-pass on the same world (scene graph stock).

Keeps plan + scene_doc + camera knobs so later passes re-render without
re-prompting from zero. PNG is a readout, not the workpiece.

Persistence: optional disk under ~/.cache/synthesus/image_sessions (or
SYNTHESUS_IMAGE_SESSION_DIR). Survives process restart.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any, Optional

_LOCK = threading.Lock()
_MAX = int(os.environ.get("SYNTHESUS_IMAGE_SESSION_MAX", "64"))
_SESSIONS: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
_DISK_ROOT = Path(
    os.environ.get(
        "SYNTHESUS_IMAGE_SESSION_DIR",
        str(Path.home() / ".cache" / "synthesus" / "image_sessions"),
    )
)
_DISK_ON = os.environ.get("SYNTHESUS_IMAGE_SESSION_DISK_OFF", "").strip().lower() not in (
    "1", "true", "yes", "on",
)


def _disk_path(sid: str) -> Path:
    return _DISK_ROOT / f"{sid}.json"


def _serialize_doc(doc: Optional[list]) -> list:
    """JSON-safe scene doc (strip Path objects)."""
    if not doc:
        return []
    out = []
    for p in doc:
        if not isinstance(p, dict):
            continue
        item = {}
        for k, v in p.items():
            if k == "paths":
                continue
            if isinstance(v, (str, int, float, bool)) or v is None:
                item[k] = v
            elif isinstance(v, (list, tuple)):
                try:
                    item[k] = [
                        float(x) if isinstance(x, (int, float)) else x for x in v
                    ]
                except Exception:
                    item[k] = list(v) if not any(callable(x) for x in v) else str(v)
            elif isinstance(v, dict):
                item[k] = {
                    sk: sv for sk, sv in v.items()
                    if isinstance(sv, (str, int, float, bool, list, type(None)))
                }
        out.append(item)
    return out


def _write_disk(sid: str, payload: dict[str, Any]) -> None:
    if not _DISK_ON:
        return
    try:
        _DISK_ROOT.mkdir(parents=True, exist_ok=True)
        safe = {
            "scene_id": sid,
            "plan": payload.get("plan"),
            "scene_doc": _serialize_doc(payload.get("scene_doc")),
            "horizon": payload.get("horizon"),
            "prompt": payload.get("prompt"),
            "seed": payload.get("seed"),
            "knobs": payload.get("knobs") or {},
            "passes": (payload.get("passes") or [])[-32:],
            "created": payload.get("created"),
            "updated": payload.get("updated"),
            "stock": "scene_graph",
            "not_diffusion": True,
        }
        tmp = _disk_path(sid).with_suffix(".tmp")
        tmp.write_text(json.dumps(safe, indent=0), encoding="utf-8")
        tmp.replace(_disk_path(sid))
    except OSError:
        pass


def _read_disk(sid: str) -> Optional[dict[str, Any]]:
    if not _DISK_ON:
        return None
    path = _disk_path(sid)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not data.get("scene_doc"):
            return None
        data["scene_id"] = sid
        return data
    except (OSError, json.JSONDecodeError):
        return None


def _touch(sid: str) -> None:
    if sid in _SESSIONS:
        _SESSIONS.move_to_end(sid)


def _evict() -> None:
    while len(_SESSIONS) > _MAX:
        old_id, old = _SESSIONS.popitem(last=False)
        _write_disk(old_id, old)


def create_session(
    *,
    plan: Optional[dict] = None,
    scene_doc: Optional[list] = None,
    horizon: float = 0.66,
    prompt: str = "",
    seed: Optional[int] = None,
    knobs: Optional[dict] = None,
    scene_id: Optional[str] = None,
) -> str:
    sid = (scene_id or uuid.uuid4().hex[:16]).strip()
    now = time.time()
    rec = {
        "scene_id": sid,
        "plan": plan,
        "scene_doc": scene_doc,
        "horizon": float(horizon),
        "prompt": prompt,
        "seed": seed,
        "knobs": dict(knobs or {}),
        "passes": [],
        "created": now,
        "updated": now,
    }
    with _LOCK:
        _SESSIONS[sid] = rec
        _SESSIONS.move_to_end(sid)
        _evict()
        _write_disk(sid, rec)
    return sid


def get_session(scene_id: str) -> Optional[dict[str, Any]]:
    if not scene_id:
        return None
    with _LOCK:
        s = _SESSIONS.get(scene_id)
        if s is not None:
            _touch(scene_id)
            return s
    # disk load
    disk = _read_disk(scene_id)
    if disk is None:
        return None
    with _LOCK:
        _SESSIONS[scene_id] = disk
        _SESSIONS.move_to_end(scene_id)
        _evict()
        return disk


def update_session(scene_id: str, **fields: Any) -> Optional[dict[str, Any]]:
    with _LOCK:
        s = _SESSIONS.get(scene_id)
        if s is None:
            disk = _read_disk(scene_id)
            if disk is None:
                return None
            s = disk
            _SESSIONS[scene_id] = s
        for k, v in fields.items():
            if k == "knobs" and isinstance(v, dict):
                s.setdefault("knobs", {}).update(v)
            elif k == "pass_record" and isinstance(v, dict):
                s.setdefault("passes", []).append(v)
                s["passes"] = s["passes"][-48:]
            else:
                s[k] = v
        s["updated"] = time.time()
        _touch(scene_id)
        _write_disk(scene_id, s)
        return s


def public_session_view(scene_id: str) -> Optional[dict[str, Any]]:
    s = get_session(scene_id)
    if not s:
        return None
    plan = s.get("plan") or {}
    return {
        "scene_id": scene_id,
        "prompt": s.get("prompt"),
        "seed": s.get("seed"),
        "horizon": s.get("horizon"),
        "knobs": s.get("knobs") or {},
        "pass_count": len(s.get("passes") or []),
        "passes": s.get("passes") or [],
        "construction": plan.get("construction"),
        "si_prompt": plan.get("si_prompt"),
        "entity_count": len(s.get("scene_doc") or []),
        "stock": "scene_graph",
        "not_diffusion": True,
        "disk_backed": _DISK_ON,
    }


def session_from_level(level: dict[str, Any], *, knobs: Optional[dict] = None) -> str:
    """Create a session from SI level JSON (re-render path)."""
    if not isinstance(level, dict):
        raise ValueError("level must be a dict")
    entities = level.get("entities") or level.get("scene_doc") or []
    if not entities:
        raise ValueError("level has no entities")
    doc = []
    for e in entities:
        if isinstance(e, dict) and e.get("role"):
            doc.append(dict(e))
    plan = level.get("plan") or {
        "si_prompt": level.get("prompt") or "level",
        "construction": "native",
        "source": "level_import",
        "not_diffusion": True,
        "entities": [],
        "composites": [],
        "machines": [],
    }
    cam = level.get("camera") or {}
    k = {
        "style": level.get("style") or "soft",
        "look": level.get("look") or "photo",
        "path_mode": bool(level.get("path_mode", True)),
        "yaw_deg": float(cam.get("yaw_deg") or 0.0),
        "pitch_deg": float(cam.get("pitch_deg") or 0.0),
        "time_of_day": cam.get("time_of_day"),
        "res": 512,
        "detail": "standard",
        "aspect": 1.0,
    }
    if knobs:
        k.update(knobs)
    return create_session(
        plan=plan,
        scene_doc=doc,
        horizon=float(level.get("horizon") or 0.66),
        prompt=level.get("prompt") or "level",
        seed=level.get("seed"),
        knobs=k,
    )


def clear_sessions(*, disk: bool = False) -> None:
    with _LOCK:
        _SESSIONS.clear()
    if disk and _DISK_ROOT.is_dir():
        for p in _DISK_ROOT.glob("*.json"):
            try:
                p.unlink()
            except OSError:
                pass


# ── Pass playlists (finish jobs) ─────────────────────────────────────

PLAYLISTS: dict[str, list[dict[str, Any]]] = {
    "finish": [
        {"label": "draft", "detail": "draft", "look": "raw", "grade": "none"},
        {"label": "standard", "detail": "standard", "look": "photo", "grade": "none"},
        {"label": "cinema", "detail": "high", "look": "cinema", "grade": "none"},
        {"label": "warm", "detail": "high", "look": "cinema", "grade": "warm"},
    ],
    "orbit_sample": [
        {"label": "yaw-15", "yaw_deg": -15, "look": "photo"},
        {"label": "yaw0", "yaw_deg": 0, "look": "photo"},
        {"label": "yaw15", "yaw_deg": 15, "look": "photo"},
    ],
    "day_cycle": [
        {"label": "dawn", "time_of_day": 0.15, "look": "photo"},
        {"label": "noon", "time_of_day": 0.5, "look": "vivid"},
        {"label": "dusk", "time_of_day": 0.82, "look": "cinema"},
        {"label": "night", "time_of_day": 0.95, "look": "cinema", "style": "night"},
    ],
}


def list_playlists() -> dict[str, list]:
    return {k: list(v) for k, v in PLAYLISTS.items()}
