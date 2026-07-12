#!/usr/bin/env python3
"""
Cinematic scene presets — one-tap SI compositions (not diffusion prompts).
=========================================================================

Each preset is a authored prompt + recommended style/look/seed/aspect for the
SI pipeline (CNC paths + materials + sky + camera ISP). Deterministic, local.

Run: python packages/reasoning/scene_presets.py
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# id → pack definition
PRESETS: Dict[str, Dict[str, Any]] = {
    "cottage_dawn": {
        "name": "Cottage at Dawn",
        "prompt": (
            "a cottage left of a tree on green grass under a blue sky "
            "with a sun and a cloud and a flower"
        ),
        "style": "photo",
        "look": "cinema",
        "detail": "high",
        "path_mode": True,
        "aspect": 1.5,
        "seed": 42,
        "resolution": 768,
        "tags": ["cinematic", "nature", "warm"],
    },
    "harbor_day": {
        "name": "Harbor Day",
        "prompt": (
            "a boat on a river under a sky with a sun and a bridge and a bird "
            "and a person right of a tree"
        ),
        "style": "photo",
        "look": "photo",
        "detail": "high",
        "path_mode": True,
        "aspect": 1.5,
        "seed": 17,
        "resolution": 768,
        "tags": ["water", "daylight"],
    },
    "city_dusk": {
        "name": "City Dusk",
        "prompt": (
            "a person left of a building on a road under a sky with a sun "
            "and a lamp and a car"
        ),
        "style": "photo",
        "look": "vivid",
        "detail": "high",
        "path_mode": True,
        "aspect": 1.5,
        "seed": 88,
        "resolution": 768,
        "tags": ["urban", "dusk"],
    },
    "mountain_lake": {
        "name": "Mountain Lake",
        "prompt": (
            "a mountain and a lake and a tree and a cabin under a sky "
            "with a sun and a cloud"
        ),
        "style": "photo",
        "look": "cinema",
        "detail": "high",
        "path_mode": True,
        "aspect": 1.5,
        "seed": 7,
        "resolution": 768,
        "tags": ["landscape", "nature"],
    },
    "night_village": {
        "name": "Night Village",
        "prompt": (
            "a house and a tree and a person and a star under a night sky "
            "over grass with a moon and a lamp"
        ),
        "style": "night",
        "look": "cinema",
        "detail": "high",
        "path_mode": True,
        "aspect": 1.0,
        "seed": 33,
        "resolution": 768,
        "tags": ["night", "mood"],
    },
    "orchard": {
        "name": "Orchard",
        "prompt": (
            "a red apple and a tree and a bush and a fence on grass "
            "under a sky with a sun and a flower"
        ),
        "style": "photo",
        "look": "photo",
        "detail": "high",
        "path_mode": True,
        "aspect": 1.0,
        "seed": 12,
        "resolution": 640,
        "tags": ["pastoral"],
    },
    "bridge_crossing": {
        "name": "Bridge Crossing",
        "prompt": (
            "a person on a bridge over a river under a sky with a sun "
            "and a tree right of a house"
        ),
        "style": "photo",
        "look": "photo",
        "detail": "high",
        "path_mode": True,
        "aspect": 1.5,
        "seed": 55,
        "resolution": 768,
        "tags": ["story", "travel"],
    },
    "tv_vivid_park": {
        "name": "TV Vivid Park",
        "prompt": (
            "a person left of a tree on grass under a sky with a sun "
            "and a cloud and a bird and a flower"
        ),
        "style": "soft",
        "look": "tv",
        "detail": "high",
        "path_mode": True,
        "aspect": 1.5,
        "seed": 21,
        "resolution": 720,
        "tags": ["display", "punchy"],
    },
}


def list_presets() -> List[Dict[str, Any]]:
    """Public catalog for API/Studio."""
    out = []
    for pid, p in PRESETS.items():
        out.append({
            "id": pid,
            "name": p.get("name", pid),
            "prompt": p.get("prompt", ""),
            "tags": list(p.get("tags") or []),
            "style": p.get("style"),
            "look": p.get("look"),
            "aspect": p.get("aspect"),
        })
    return out


def get_preset(preset_id: str) -> Optional[Dict[str, Any]]:
    if not preset_id:
        return None
    key = preset_id.strip().lower().replace(" ", "_").replace("-", "_")
    # aliases
    aliases = {
        "cottage": "cottage_dawn",
        "dawn": "cottage_dawn",
        "harbor": "harbor_day",
        "city": "city_dusk",
        "mountain": "mountain_lake",
        "night": "night_village",
        "village": "night_village",
        "park": "tv_vivid_park",
        "bridge": "bridge_crossing",
    }
    key = aliases.get(key, key)
    p = PRESETS.get(key)
    if not p:
        return None
    out = dict(p)
    out["id"] = key
    return out


def apply_preset_to_request(body: Dict[str, Any]) -> Dict[str, Any]:
    """Merge preset defaults into a request body (body fields win if set explicitly).

    If body has 'preset', fill missing prompt/style/look/etc from catalog.
    """
    body = dict(body or {})
    pid = body.get("preset") or body.get("preset_id")
    if not pid:
        return body
    p = get_preset(str(pid))
    if not p:
        return body
    # Only fill blanks so explicit user knobs win
    for k in ("prompt", "style", "look", "detail", "path_mode", "aspect", "seed", "resolution"):
        if body.get(k) in (None, "", []):
            if k in p:
                body[k] = p[k]
    body["preset"] = p.get("id")
    body["preset_name"] = p.get("name")
    return body


def demo():
    print("presets:", len(PRESETS))
    for row in list_presets():
        print(f"  {row['id']:20s} {row['name']}")


if __name__ == "__main__":
    demo()
