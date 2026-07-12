#!/usr/bin/env python3
"""
Chat/voice intent routing for SI image surfaces.

Modes (honest, labeled):
  draw  — SI construct (plan + machines + raster)
  find  — retrieve real media (stub: honest refuse + how to cite)
  talk  — no image; conversational only
  pass  — multi-pass knobs on existing scene stock
  refuse — cannot honestly fulfill; offer construct alternative
"""
from __future__ import annotations

import re
from typing import Any, Optional

# Hard fails for SI construct (identity / open photoreal)
REFUSE_PATTERNS = [
    (re.compile(r"\b(photo\s+of|photograph\s+of|selfie\s+of)\b", re.I), "photoreal_capture"),
    (re.compile(r"\b(portrait\s+of|face\s+of|looks?\s+like)\s+[A-Z]", re.I), "identity"),
    (re.compile(r"\b(elon|celebrity|obama|trump|biden|taylor\s+swift)\b", re.I), "identity"),
    (re.compile(r"\b(eiffel|statue\s+of\s+liberty|mount\s+rushmore|taj\s+mahal)\b", re.I), "landmark"),
    (re.compile(r"\b(logo\s+of|coca[- ]cola|mcdonald|nike\s+swoosh)\b", re.I), "brand"),
    (re.compile(r"\b(in\s+the\s+style\s+of|van\s+gogh|ghibli|anime\s+style)\b", re.I), "style_pastiche"),
]

DRAW_PREFIX = re.compile(
    r"^(?:\/draw|draw(?:\s+this)?|imagine|picture|render|paint|illustrate)\s*[:\-]?\s*",
    re.I,
)
FIND_PREFIX = re.compile(
    r"^(?:\/find|find(?:\s+photo)?|search\s+image|show\s+photo|look\s+up\s+image)\s*[:\-]?\s*",
    re.I,
)
PASS_PATTERNS = [
    (re.compile(r"\b(warmer|warm\s+it|more\s+warm)\b", re.I), {"grade": "warm"}),
    (re.compile(r"\b(cooler|cool\s+it|more\s+cool)\b", re.I), {"grade": "cool"}),
    (re.compile(r"\b(more\s+contrast|crisper)\b", re.I), {"grade": "contrast"}),
    (re.compile(r"\b(cinematic|cinema\s+look)\b", re.I), {"look": "cinema"}),
    (re.compile(r"\b(vivid|more\s+color)\b", re.I), {"look": "vivid"}),
    (re.compile(r"\b(raw|no\s+isp|flat\s+look)\b", re.I), {"look": "raw"}),
    (re.compile(r"\b(dusk|golden\s+hour|evening)\b", re.I), {"time_of_day": 0.82, "look": "cinema"}),
    (re.compile(r"\b(dawn|sunrise|morning)\b", re.I), {"time_of_day": 0.18}),
    (re.compile(r"\b(night|midnight)\b", re.I), {"time_of_day": 0.95, "style": "night"}),
    (re.compile(r"\b(turn\s+left|orbit\s+left|yaw\s+left)\b", re.I), {"yaw_delta": -15}),
    (re.compile(r"\b(turn\s+right|orbit\s+right|yaw\s+right)\b", re.I), {"yaw_delta": 15}),
    (re.compile(r"\b(draft|faster|preview)\b", re.I), {"detail": "draft"}),
    (re.compile(r"\b(high\s+detail|more\s+detail)\b", re.I), {"detail": "high"}),
]


def construct_alternative(reason: str, original: str) -> str:
    alts = {
        "photoreal_capture": (
            "I can't honestly produce a real photograph. "
            "I can *draw* an SI illustration (house, tree, vase, river…) — try: "
            "draw a cabin by a river at dusk"
        ),
        "identity": (
            "I won't invent a real person's face. "
            "I can draw a generic *person* figure near a house — try: "
            "draw a person left of a house on grass under a sky"
        ),
        "landmark": (
            "I don't have a true landmark mesh. "
            "I can draw a tower/building stand-in — try: "
            "draw a tower and a bridge on a river under a sky"
        ),
        "brand": (
            "I won't forge brand logos. "
            "I can assemble a simple machine from shapes — try: "
            "draw an espresso machine on a table under a sky"
        ),
        "style_pastiche": (
            "I don't do artist style transfer. "
            "I can use SI camera looks (cinema/vivid/tv) — try: "
            "draw a house on grass under a sky (then re-pass look=cinema)"
        ),
    }
    return alts.get(reason, "I can draw an SI scene from known shapes if you rephrase.")


def classify_intent(
    message: str,
    *,
    has_scene_id: bool = False,
) -> dict[str, Any]:
    """Return mode + payload for chat/Studio routing."""
    text = (message or "").strip()
    if not text:
        return {"mode": "talk", "prompt": "", "reason": "empty"}

    # Pass knobs on existing stock
    if has_scene_id:
        knobs: dict[str, Any] = {}
        for rx, patch in PASS_PATTERNS:
            if rx.search(text):
                knobs.update(patch)
        if knobs and not DRAW_PREFIX.match(text) and not FIND_PREFIX.match(text):
            # pure adjustment language
            if not re.search(r"\b(draw|paint|render|imagine)\b", text, re.I) or len(text) < 80:
                if any(k in knobs for k in ("grade", "look", "yaw_delta", "time_of_day", "detail", "style")):
                    return {
                        "mode": "pass",
                        "prompt": text,
                        "pass_knobs": knobs,
                        "label": "multi-pass on scene stock",
                    }

    # Find mode
    m_find = FIND_PREFIX.match(text)
    if m_find:
        q = text[m_find.end():].strip() or text
        return {
            "mode": "find",
            "prompt": q,
            "label": "retrieve (not SI construct)",
            "status": "not_implemented_retrieve",
            "message": (
                "Find/retrieve mode is labeled separately from SI drawing. "
                "Licensed media APIs are not wired in this build — I won't fake a photo. "
                "I can *draw* a procedural stand-in if you say: draw " + q[:80]
            ),
            "alternative": f"draw {q}",
        }

    # Draw mode
    m_draw = DRAW_PREFIX.match(text)
    prompt = text[m_draw.end():].strip() if m_draw else text
    if m_draw or re.search(r"\b(scene|landscape|illustration)\b", text, re.I):
        for rx, reason in REFUSE_PATTERNS:
            if rx.search(prompt) or rx.search(text):
                return {
                    "mode": "refuse",
                    "prompt": prompt,
                    "reason": reason,
                    "message": construct_alternative(reason, prompt),
                    "alternative": None if reason == "identity" else f"draw a house and a tree on grass under a sky",
                }
        return {
            "mode": "draw",
            "prompt": prompt or text,
            "label": "SI construct (not diffusion)",
        }

    # Bare refuse patterns without draw prefix
    for rx, reason in REFUSE_PATTERNS:
        if rx.search(text):
            return {
                "mode": "refuse",
                "prompt": text,
                "reason": reason,
                "message": construct_alternative(reason, text),
            }

    return {"mode": "talk", "prompt": text, "label": "conversation"}


def capability_card() -> dict[str, Any]:
    return {
        "engine": "si-image-v6+",
        "not_diffusion": True,
        "stock": "scene_graph",
        "can": [
            "SI illustration from known shapes + lathe/extrude/composites",
            "Camera ISP looks: raw|photo|cinema|vivid|tv",
            "Multi-pass: yaw/pitch/time/grade on same scene_id",
            "Draft → finish playlist",
            "Orbit / time GIFs, level JSON export/import",
            "CNC path form (mill) + lathe revolution + extrude volumes",
        ],
        "cannot": [
            "Photoreal photos of real places/people",
            "True faces / celebrity identity",
            "Brand logos and artist style pastiche",
            "Generative fill / diffusion invent",
            "Full 3D mesh CAD",
        ],
        "modes": {
            "draw": "construct SI scene",
            "find": "retrieve media (labeled; API optional)",
            "talk": "chat only",
            "pass": "re-render scene stock",
        },
        "si_vs_ai": (
            "Synthesus SI builds form; optional LLM only plans recipes. "
            "Ollama/inhabitants are not the image engine."
        ),
    }
