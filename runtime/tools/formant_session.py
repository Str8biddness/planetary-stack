#!/usr/bin/env python3
"""
Utterance stock store for SI formant multi-pass (mirror image_session).

Stock = utterance_plan (+ last render knobs). WAV is a readout.
Optional disk under ~/.cache/synthesus/formant_sessions.
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
_MAX = int(os.environ.get("SYNTHESUS_FORMANT_SESSION_MAX", "48"))
_SESSIONS: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
_DISK_ROOT = Path(
    os.environ.get(
        "SYNTHESUS_FORMANT_SESSION_DIR",
        str(Path.home() / ".cache" / "synthesus" / "formant_sessions"),
    )
)
_DISK_ON = os.environ.get("SYNTHESUS_FORMANT_SESSION_DISK_OFF", "").strip().lower() not in (
    "1", "true", "yes", "on",
)


def _path(sid: str) -> Path:
    return _DISK_ROOT / f"{sid}.json"


def _write_disk(sid: str, rec: dict[str, Any]) -> None:
    if not _DISK_ON:
        return
    try:
        _DISK_ROOT.mkdir(parents=True, exist_ok=True)
        safe = {
            "utterance_id": sid,
            "plan": rec.get("plan"),
            "text": rec.get("text"),
            "seed": rec.get("seed"),
            "fs": rec.get("fs"),
            "passes": (rec.get("passes") or [])[-32:],
            "created": rec.get("created"),
            "updated": rec.get("updated"),
            "stock": "utterance_plan",
            "not_neural_tts": True,
        }
        tmp = _path(sid).with_suffix(".tmp")
        tmp.write_text(json.dumps(safe), encoding="utf-8")
        tmp.replace(_path(sid))
    except OSError:
        pass


def _read_disk(sid: str) -> Optional[dict[str, Any]]:
    if not _DISK_ON:
        return None
    p = _path(sid)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not data.get("plan"):
            return None
        data["utterance_id"] = sid
        return data
    except (OSError, json.JSONDecodeError):
        return None


def create_session(
    *,
    plan: dict,
    text: str = "",
    seed: int = 25,
    fs: int = 16000,
    utterance_id: Optional[str] = None,
) -> str:
    sid = (utterance_id or uuid.uuid4().hex[:16]).strip()
    now = time.time()
    rec = {
        "utterance_id": sid,
        "plan": plan,
        "text": text or plan.get("source_text") or "",
        "seed": seed,
        "fs": fs,
        "passes": [{"kind": "create", "t": now}],
        "created": now,
        "updated": now,
    }
    with _LOCK:
        _SESSIONS[sid] = rec
        _SESSIONS.move_to_end(sid)
        while len(_SESSIONS) > _MAX:
            oid, old = _SESSIONS.popitem(last=False)
            _write_disk(oid, old)
        _write_disk(sid, rec)
    return sid


def get_session(utterance_id: str) -> Optional[dict[str, Any]]:
    if not utterance_id:
        return None
    with _LOCK:
        s = _SESSIONS.get(utterance_id)
        if s is not None:
            _SESSIONS.move_to_end(utterance_id)
            return s
    disk = _read_disk(utterance_id)
    if disk is None:
        return None
    with _LOCK:
        _SESSIONS[utterance_id] = disk
        _SESSIONS.move_to_end(utterance_id)
        return disk


def update_session(utterance_id: str, **fields: Any) -> Optional[dict[str, Any]]:
    with _LOCK:
        s = _SESSIONS.get(utterance_id)
        if s is None:
            s = _read_disk(utterance_id)
            if s is None:
                return None
            _SESSIONS[utterance_id] = s
        for k, v in fields.items():
            if k == "pass_record" and isinstance(v, dict):
                s.setdefault("passes", []).append(v)
                s["passes"] = s["passes"][-48:]
            elif k == "plan" and isinstance(v, dict):
                s["plan"] = v
            else:
                s[k] = v
        s["updated"] = time.time()
        _SESSIONS.move_to_end(utterance_id)
        _write_disk(utterance_id, s)
        return s


def public_view(utterance_id: str) -> Optional[dict[str, Any]]:
    s = get_session(utterance_id)
    if not s:
        return None
    plan = s.get("plan") or {}
    return {
        "utterance_id": utterance_id,
        "text": s.get("text"),
        "seed": s.get("seed"),
        "fs": s.get("fs"),
        "pass_count": len(s.get("passes") or []),
        "passes": s.get("passes") or [],
        "word_count": len(plan.get("words") or []),
        "rate": plan.get("rate"),
        "f0_base_hz": plan.get("f0_base_hz"),
        "stock": "utterance_plan",
        "not_neural_tts": True,
        "disk_backed": _DISK_ON,
    }


def clear_sessions(*, disk: bool = False) -> None:
    with _LOCK:
        _SESSIONS.clear()
    if disk and _DISK_ROOT.is_dir():
        for p in _DISK_ROOT.glob("*.json"):
            try:
                p.unlink()
            except OSError:
                pass


# Named multi-pass playlists
PLAYLISTS = {
    "clear": [
        {"label": "base", "knobs": {}},
        {"label": "slower", "knobs": {"slower": True}},
        {"label": "clear_rise", "knobs": {"slower": True, "rising_final": True}},
    ],
    "pitch_demo": [
        {"label": "low", "knobs": {"lower": True}},
        {"label": "mid", "knobs": {}},
        {"label": "high", "knobs": {"higher": True}},
    ],
}
