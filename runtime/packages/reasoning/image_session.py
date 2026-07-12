#!/usr/bin/env python3
"""
SI image session store — multi-pass on the same world (scene graph stock).

Keeps plan + scene_doc + camera knobs so later passes re-render without
re-prompting from zero. PNG is a readout, not the workpiece.
"""
from __future__ import annotations

import threading
import time
import uuid
from collections import OrderedDict
from typing import Any, Optional

_LOCK = threading.Lock()
_MAX = 64
_SESSIONS: "OrderedDict[str, dict[str, Any]]" = OrderedDict()


def _touch(sid: str) -> None:
    if sid in _SESSIONS:
        _SESSIONS.move_to_end(sid)


def create_session(
    *,
    plan: Optional[dict] = None,
    scene_doc: Optional[list] = None,
    horizon: float = 0.66,
    prompt: str = "",
    seed: Optional[int] = None,
    knobs: Optional[dict] = None,
) -> str:
    sid = uuid.uuid4().hex[:16]
    with _LOCK:
        _SESSIONS[sid] = {
            "scene_id": sid,
            "plan": plan,
            "scene_doc": scene_doc,
            "horizon": float(horizon),
            "prompt": prompt,
            "seed": seed,
            "knobs": dict(knobs or {}),
            "passes": [],
            "created": time.time(),
            "updated": time.time(),
        }
        _SESSIONS.move_to_end(sid)
        while len(_SESSIONS) > _MAX:
            _SESSIONS.popitem(last=False)
    return sid


def get_session(scene_id: str) -> Optional[dict[str, Any]]:
    with _LOCK:
        s = _SESSIONS.get(scene_id)
        if s is None:
            return None
        _touch(scene_id)
        # shallow copy; doc list is shared intentionally for in-place passes
        return s


def update_session(scene_id: str, **fields: Any) -> Optional[dict[str, Any]]:
    with _LOCK:
        s = _SESSIONS.get(scene_id)
        if s is None:
            return None
        for k, v in fields.items():
            if k == "knobs" and isinstance(v, dict):
                s.setdefault("knobs", {}).update(v)
            elif k == "pass_record" and isinstance(v, dict):
                s.setdefault("passes", []).append(v)
            else:
                s[k] = v
        s["updated"] = time.time()
        _touch(scene_id)
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
    }


def clear_sessions() -> None:
    with _LOCK:
        _SESSIONS.clear()
