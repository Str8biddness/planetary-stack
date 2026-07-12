#!/usr/bin/env python3
"""
Lightweight materials / mood library for SI plans (not scraped photos).

Optional knowledge-cloud-style defaults: palettes and ground/sky biases
applied as plan camera/color hints. Honest: procedural knobs, not media.
"""
from __future__ import annotations

from typing import Any, Optional

# Region-ish / mood palettes (RGB 0-1)
PALETTES: dict[str, dict[str, Any]] = {
    "temperate": {
        "grass": (0.30, 0.52, 0.28),
        "sky": (0.45, 0.65, 0.90),
        "time_bias": None,
    },
    "desert": {
        "grass": (0.72, 0.62, 0.38),  # sand ground
        "sky": (0.55, 0.72, 0.92),
        "time_bias": 0.55,
    },
    "nordic": {
        "grass": (0.55, 0.62, 0.55),
        "sky": (0.55, 0.60, 0.70),
        "time_bias": 0.35,
        "look": "cool",
    },
    "tropical": {
        "grass": (0.20, 0.55, 0.30),
        "sky": (0.35, 0.70, 0.95),
        "time_bias": 0.45,
        "look": "vivid",
    },
    "autumn": {
        "grass": (0.45, 0.40, 0.22),
        "sky": (0.60, 0.55, 0.50),
        "time_bias": 0.75,
        "look": "cinema",
    },
}

MOOD_KEYS = [
    (r"desert|dune|sahara|arid", "desert"),
    (r"snow|arctic|nordic|tundra|pine\s+forest", "nordic"),
    (r"tropical|jungle|palm|island", "tropical"),
    (r"autumn|fall\s+colors|harvest", "autumn"),
]


def mood_from_prompt(prompt: str) -> Optional[str]:
    import re
    p = prompt or ""
    for pat, key in MOOD_KEYS:
        if re.search(pat, p, re.I):
            return key
    return None


def apply_material_hints(plan: dict[str, Any], prompt: Optional[str] = None) -> dict[str, Any]:
    """Mutate/return plan camera + compile note with palette hints."""
    plan = dict(plan)
    prompt = prompt or plan.get("source_prompt") or ""
    key = mood_from_prompt(prompt)
    if not key or key not in PALETTES:
        plan.setdefault("material_lib", {"palette": None})
        return plan
    pal = PALETTES[key]
    cam = dict(plan.get("camera") or {})
    if pal.get("time_bias") is not None and cam.get("time_of_day") is None:
        cam["time_of_day"] = float(pal["time_bias"])
    if pal.get("look") and not cam.get("look"):
        # look may be grade-like; map cool→photo for ISP
        lk = pal["look"]
        if lk in ("cinema", "vivid", "photo", "tv", "raw"):
            cam["look"] = lk
    plan["camera"] = cam
    plan["material_lib"] = {
        "palette": key,
        "grass_rgb": pal.get("grass"),
        "sky_rgb": pal.get("sky"),
        "note": "procedural mood palette — not retrieved photo",
    }
    steps = list(plan.get("compile_steps") or [])
    steps.append(f"material_lib palette={key}")
    plan["compile_steps"] = steps
    return plan
