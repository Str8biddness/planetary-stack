#!/usr/bin/env python3
"""
SI Scene Plan compiler — LLM/rules as outer voice + inner monologue + shape compile.

Synthesus image construction (not diffusion):
  user language
    → plan (synonyms, composites from known roles, camera knobs)
    → SI pattern_document + composite inject
    → CNC / materials / ISP raster

The model (when used) supplies *recipes* and *routing*, never pixels.
Rule-based compile always works offline; optional Ollama enrich is best-effort.

Honesty labels:
  native     — only SHAPES tokens from the prompt
  mapped     — synonyms folded into known entities
  composite  — unknown nouns assembled from role puzzle pieces
  mixed      — mapped + composite
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Optional

import numpy as np

import scene_composer

PLAN_VERSION = "scene-plan-v1"
VALID_ROLES = frozenset(scene_composer.SHAPES.values()) | frozenset(
    getattr(scene_composer, "DEFAULT_ROLES_EXTRA", {}).keys()
)
# Ensure paint roles covered even if only in defaults
VALID_ROLES = frozenset(
    list(VALID_ROLES)
    + [
        "bg", "ground", "disc_top", "cloud_top", "star_top", "disc", "tree",
        "triangle", "house", "strip", "river", "fence", "boat", "person",
        "building", "flower", "bird", "bridge", "bush",
        "lathe", "extrude",
    ]
)

# Machine routing: entity token → lathe | extrude (else mill/composite/native)
LATHE_ENTITIES = frozenset({
    "cup", "mug", "glass", "vase", "urn", "column", "pillar", "bottle", "flask",
    "pot", "jar", "fruit", "apple", "orange", "bowl", "goblet",
})
EXTRUDE_ENTITIES = frozenset({
    "crate", "box", "block", "wall", "brick", "slab", "plinth", "pedestal",
    "container", "dumpster", "cabinet",
})
# Prefer lathe over disc for these even if also in SHAPES
LATHE_OVERRIDE_SHAPES = frozenset({"apple", "orange", "ball"})

# Free-language → SHAPES entity (must be a key of SHAPES)
SYNONYMS: dict[str, str] = {
    # dwellings
    "cabin": "house", "cottage": "house", "hut": "house", "shack": "house",
    "home": "house", "dwelling": "house", "chalet": "house", "villa": "house",
    "farmhouse": "barn", "shed": "house",
    # water
    "creek": "river", "brook": "stream", "pond": "lake", "lagoon": "lake",
    "bay": "sea", "beach": "sand", "shore": "sand", "waterfall": "river",
    # land
    "meadow": "field", "pasture": "field", "lawn": "grass", "forest": "tree",
    "woods": "tree", "woodland": "tree", "pine": "tree", "oak": "tree",
    "peak": "mountain", "summit": "mountain", "cliff": "mountain",
    "dune": "sand", "desert": "sand",
    # sky / light
    "sunrise": "sun", "sunset": "sun", "dawn": "sun", "dusk": "sun",
    "starry": "star", "cloudy": "cloud", "overcast": "cloud",
    "streetlight": "lamp", "lantern": "lamp", "torch": "fire",
    # people / craft
    "man": "person", "woman": "person", "child": "person", "figure": "person",
    "human": "person", "traveler": "person", "sailor": "person",
    "kayak": "boat", "canoe": "boat", "yacht": "ship", "vessel": "boat",
    "truck": "car", "vehicle": "car", "bike": "car",
    # structures
    "skyscraper": "tower", "skyscrapers": "tower", "temple": "building",
    "church": "building", "factory": "building", "barnhouse": "barn",
    "footbridge": "bridge", "dock": "bridge", "pier": "bridge",
    "garden": "flower", "blossom": "flower", "shrub": "bush",
    "pathway": "path", "trail": "path", "highway": "road", "street": "road",
    "avenue": "road",
}

# Multi-word phrases → entity or composite name
PHRASES: dict[str, str] = {
    "espresso machine": "espresso_machine",
    "coffee machine": "espresso_machine",
    "coffee maker": "espresso_machine",
    "vending machine": "vending_machine",
    "food cart": "cart",
    "hot dog cart": "cart",
    "market stall": "stall",
    "lamp post": "lamppost",
    "lamppost": "lamppost",
    "street lamp": "lamppost",
    "wind mill": "windmill",
    "mail box": "mailbox",
    "park bench": "bench",
    "picnic table": "table",
    "water tower": "water_tower",
    "cell tower": "tower",
    "sail boat": "boat",
    "row boat": "boat",
    "log cabin": "cabin",
    "full moon": "moon",
    "blue sky": "sky",
    "night sky": "night",
    "green grass": "grass",
}

# Named composites: list of part templates (role + layout offsets)
# dx: x offset from anchor, dy: base offset (positive = lower on screen)
# scale multiplies default role size
COMPOSITE_RECIPES: dict[str, list[dict[str, Any]]] = {
    "espresso_machine": [
        {"role": "building", "entity": "espresso_body", "dx": 0.0, "dy": 0.0, "scale": 0.55,
         "color": (0.22, 0.22, 0.26)},
        {"role": "disc", "entity": "group_head", "dx": 0.03, "dy": -0.04, "scale": 0.45,
         "color": (0.35, 0.35, 0.4)},
        {"role": "strip", "entity": "drip_tray", "dx": 0.0, "dy": 0.02, "scale": 0.5,
         "color": (0.3, 0.3, 0.32)},
        {"role": "disc", "entity": "cup", "dx": 0.06, "dy": 0.0, "scale": 0.35,
         "color": (0.85, 0.85, 0.9)},
    ],
    "vending_machine": [
        {"role": "building", "entity": "vending_body", "dx": 0.0, "dy": 0.0, "scale": 0.9,
         "color": (0.55, 0.15, 0.18)},
        {"role": "disc", "entity": "coin_slot", "dx": 0.02, "dy": -0.08, "scale": 0.25,
         "color": (0.7, 0.7, 0.75)},
    ],
    "robot": [
        {"role": "building", "entity": "robot_torso", "dx": 0.0, "dy": 0.0, "scale": 0.5,
         "color": (0.55, 0.58, 0.62)},
        {"role": "disc", "entity": "robot_head", "dx": 0.0, "dy": -0.12, "scale": 0.55,
         "color": (0.65, 0.68, 0.72)},
        {"role": "person", "entity": "robot_legs", "dx": 0.0, "dy": 0.02, "scale": 0.7,
         "color": (0.45, 0.48, 0.52)},
    ],
    "cart": [
        {"role": "building", "entity": "cart_body", "dx": 0.0, "dy": -0.02, "scale": 0.45,
         "color": (0.55, 0.35, 0.2)},
        {"role": "disc", "entity": "wheel_l", "dx": -0.05, "dy": 0.02, "scale": 0.4,
         "color": (0.2, 0.2, 0.22)},
        {"role": "disc", "entity": "wheel_r", "dx": 0.05, "dy": 0.02, "scale": 0.4,
         "color": (0.2, 0.2, 0.22)},
        {"role": "strip", "entity": "cart_awning", "dx": 0.0, "dy": -0.08, "scale": 0.6,
         "color": (0.7, 0.25, 0.25)},
    ],
    "stall": [
        {"role": "building", "entity": "stall_body", "dx": 0.0, "dy": 0.0, "scale": 0.5,
         "color": (0.6, 0.45, 0.3)},
        {"role": "strip", "entity": "awning", "dx": 0.0, "dy": -0.1, "scale": 0.7,
         "color": (0.75, 0.3, 0.25)},
        {"role": "fence", "entity": "counter", "dx": 0.0, "dy": 0.0, "scale": 0.8,
         "color": (0.5, 0.35, 0.2)},
    ],
    "lamppost": [
        {"role": "person", "entity": "post", "dx": 0.0, "dy": 0.0, "scale": 1.2,
         "color": (0.25, 0.25, 0.28)},
        {"role": "disc_top", "entity": "lamp", "dx": 0.0, "dy": -0.22, "scale": 0.5,
         "color": (0.95, 0.85, 0.4)},
    ],
    "windmill": [
        {"role": "building", "entity": "mill_tower", "dx": 0.0, "dy": 0.0, "scale": 1.0,
         "color": (0.75, 0.72, 0.65)},
        {"role": "star_top", "entity": "blades", "dx": 0.0, "dy": -0.2, "scale": 1.4,
         "color": (0.85, 0.85, 0.8)},
    ],
    "mailbox": [
        {"role": "building", "entity": "mailbox_body", "dx": 0.0, "dy": -0.02, "scale": 0.35,
         "color": (0.15, 0.35, 0.7)},
        {"role": "person", "entity": "post", "dx": 0.0, "dy": 0.02, "scale": 0.6,
         "color": (0.3, 0.3, 0.32)},
    ],
    "bench": [
        {"role": "fence", "entity": "bench_seat", "dx": 0.0, "dy": 0.0, "scale": 1.1,
         "color": (0.45, 0.32, 0.18)},
        {"role": "strip", "entity": "bench_back", "dx": 0.0, "dy": -0.03, "scale": 0.5,
         "color": (0.4, 0.28, 0.15)},
    ],
    "table": [
        {"role": "strip", "entity": "tabletop", "dx": 0.0, "dy": -0.02, "scale": 0.8,
         "color": (0.5, 0.35, 0.2)},
        {"role": "person", "entity": "leg_l", "dx": -0.04, "dy": 0.02, "scale": 0.5,
         "color": (0.4, 0.28, 0.15)},
        {"role": "person", "entity": "leg_r", "dx": 0.04, "dy": 0.02, "scale": 0.5,
         "color": (0.4, 0.28, 0.15)},
    ],
    "water_tower": [
        {"role": "disc", "entity": "tank", "dx": 0.0, "dy": -0.1, "scale": 1.2,
         "color": (0.55, 0.58, 0.6)},
        {"role": "building", "entity": "legs", "dx": 0.0, "dy": 0.0, "scale": 0.6,
         "color": (0.4, 0.4, 0.42)},
    ],
    "tent": [
        {"role": "triangle", "entity": "tent", "dx": 0.0, "dy": 0.0, "scale": 0.7,
         "color": (0.7, 0.35, 0.25)},
        {"role": "strip", "entity": "floor", "dx": 0.0, "dy": 0.02, "scale": 0.5,
         "color": (0.45, 0.35, 0.25)},
    ],
    "tractor": [
        {"role": "building", "entity": "cab", "dx": 0.02, "dy": -0.03, "scale": 0.45,
         "color": (0.75, 0.2, 0.15)},
        {"role": "boat", "entity": "body", "dx": 0.0, "dy": 0.0, "scale": 1.1,
         "color": (0.7, 0.18, 0.12)},
        {"role": "disc", "entity": "wheel", "dx": -0.05, "dy": 0.02, "scale": 0.7,
         "color": (0.15, 0.15, 0.15)},
    ],
    "fountain": [
        {"role": "disc", "entity": "basin", "dx": 0.0, "dy": 0.0, "scale": 1.0,
         "color": (0.55, 0.6, 0.65)},
        {"role": "disc_top", "entity": "spray", "dx": 0.0, "dy": -0.08, "scale": 0.4,
         "color": (0.6, 0.75, 0.9)},
    ],
    "well": [
        {"role": "disc", "entity": "well_ring", "dx": 0.0, "dy": 0.0, "scale": 0.8,
         "color": (0.45, 0.45, 0.48)},
        {"role": "building", "entity": "well_roof", "dx": 0.0, "dy": -0.06, "scale": 0.4,
         "color": (0.55, 0.35, 0.25)},
    ],
}

# Words that are not scene nouns (skip as entities)
STOP = frozenset({
    "a", "an", "the", "and", "or", "with", "of", "to", "in", "on", "at", "for",
    "from", "by", "as", "is", "are", "be", "this", "that", "it", "its", "into",
    "over", "under", "above", "below", "near", "left", "right", "next", "beside",
    "very", "really", "some", "many", "few", "all", "my", "your", "our", "their",
    "draw", "paint", "render", "picture", "image", "scene", "view", "photo",
    "beautiful", "nice", "lovely", "old", "new", "big", "small", "tiny", "huge",
    "lonely", "quiet", "busy", "dark", "bright", "soft", "hard", "red", "blue",
    "green", "yellow", "white", "black", "brown", "golden", "pink", "purple",
    "gray", "grey", "orange",
    "hour", "hours", "minute", "minutes", "second", "seconds", "time", "times",
    "today", "tomorrow", "yesterday", "am", "pm",
})

MOOD_TIME = [
    (re.compile(r"\b(midnight|night\s+sky|starry|nocturnal)\b", re.I), 0.92, "night"),
    (re.compile(r"\b(dusk|twilight|evening|sunset|golden\s+hour)\b", re.I), 0.82, None),
    (re.compile(r"\b(dawn|sunrise|daybreak|morning)\b", re.I), 0.18, None),
    (re.compile(r"\b(noon|midday|afternoon|daytime|sunny\s+day)\b", re.I), 0.5, None),
]
MOOD_LOOK = [
    (re.compile(r"\b(cinematic|film\s*noir|dramatic)\b", re.I), "cinema"),
    (re.compile(r"\b(vivid|saturated|pop)\b", re.I), "vivid"),
    (re.compile(r"\b(tv|broadcast|crisp)\b", re.I), "tv"),
    (re.compile(r"\b(photo|photoreal|realistic\s+look)\b", re.I), "photo"),
]


def known_entities() -> set[str]:
    return set(scene_composer.SHAPES.keys())


def role_for_entity(entity: str) -> Optional[str]:
    return scene_composer.SHAPES.get(entity)


def _tokenize_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", (text or "").lower())


def _extract_phrases(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Replace multi-word phrases; return scrubbed text + list of (phrase, key)."""
    low = " " + (text or "").lower() + " "
    found: list[tuple[str, str]] = []
    # longer phrases first
    for phrase in sorted(PHRASES.keys(), key=len, reverse=True):
        pat = " " + phrase + " "
        if pat in low:
            key = PHRASES[phrase]
            found.append((phrase, key))
            low = low.replace(pat, f" __PH_{len(found)-1}__ ")
    return low, found


def _default_composite_parts(name: str) -> list[dict[str, Any]]:
    """Heuristic puzzle pieces for unknown nouns."""
    n = name.replace("_", " ")
    if any(k in n for k in ("machine", "device", "engine", "appliance")):
        return [
            {"role": "building", "entity": f"{name}_body", "dx": 0.0, "dy": 0.0, "scale": 0.6,
             "color": (0.35, 0.36, 0.4)},
            {"role": "disc", "entity": f"{name}_knob", "dx": 0.03, "dy": -0.05, "scale": 0.35,
             "color": (0.55, 0.55, 0.58)},
            {"role": "strip", "entity": f"{name}_base", "dx": 0.0, "dy": 0.02, "scale": 0.5,
             "color": (0.3, 0.3, 0.32)},
        ]
    if any(k in n for k in ("tower", "spire", "antenna")):
        return [
            {"role": "building", "entity": f"{name}_shaft", "dx": 0.0, "dy": 0.0, "scale": 1.1,
             "color": (0.5, 0.52, 0.55)},
            {"role": "disc_top", "entity": f"{name}_top", "dx": 0.0, "dy": -0.2, "scale": 0.4,
             "color": (0.7, 0.7, 0.75)},
        ]
    if any(k in n for k in ("animal", "dog", "cat", "horse", "wolf", "deer", "bear")):
        return [
            {"role": "disc", "entity": f"{name}_body", "dx": 0.0, "dy": 0.0, "scale": 0.9,
             "color": (0.45, 0.35, 0.25)},
            {"role": "disc", "entity": f"{name}_head", "dx": 0.05, "dy": -0.03, "scale": 0.5,
             "color": (0.5, 0.38, 0.28)},
            {"role": "person", "entity": f"{name}_legs", "dx": 0.0, "dy": 0.02, "scale": 0.45,
             "color": (0.4, 0.3, 0.22)},
        ]
    # generic object: box + accent
    return [
        {"role": "building", "entity": f"{name}_main", "dx": 0.0, "dy": 0.0, "scale": 0.55,
         "color": (0.45, 0.42, 0.4)},
        {"role": "disc", "entity": f"{name}_accent", "dx": 0.04, "dy": -0.04, "scale": 0.4,
         "color": (0.55, 0.5, 0.45)},
    ]


def _mood_from_prompt(prompt: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for rx, t, style in MOOD_TIME:
        if rx.search(prompt or ""):
            out["time_of_day"] = t
            if style:
                out["style"] = style
            break
    for rx, look in MOOD_LOOK:
        if rx.search(prompt or ""):
            out["look"] = look
            break
    return out


def _relation_snippets(tokens: list[str], entity_set: set[str]) -> list[str]:
    """Build 'a X left of a Y' fragments using mapped entity names present in tokens."""
    rels = []
    # tokens here should already be mapped si names where possible
    for i, t in enumerate(tokens):
        if t not in entity_set and t not in scene_composer.SHAPES:
            continue
        # look ahead for relation word + object
        for j in range(i + 1, min(i + 6, len(tokens))):
            if tokens[j] in ("left",) and j + 1 < len(tokens) and tokens[j + 1] == "of":
                for k in range(j + 2, min(j + 5, len(tokens))):
                    if tokens[k] in scene_composer.SHAPES or tokens[k] in entity_set:
                        rels.append(f"a {t} left of a {tokens[k]}")
                        break
            if tokens[j] in ("right",) and j + 1 < len(tokens) and tokens[j + 1] == "of":
                for k in range(j + 2, min(j + 5, len(tokens))):
                    if tokens[k] in scene_composer.SHAPES or tokens[k] in entity_set:
                        rels.append(f"a {t} right of a {tokens[k]}")
                        break
            if tokens[j] == "near" or tokens[j] == "beside":
                for k in range(j + 1, min(j + 4, len(tokens))):
                    if tokens[k] in scene_composer.SHAPES or tokens[k] in entity_set:
                        rels.append(f"a {t} near a {tokens[k]}")
                        break
    return rels


def compile_scene_plan_rules(prompt: str) -> dict[str, Any]:
    """Deterministic offline compile (no network)."""
    prompt = (prompt or "").strip()
    steps: list[str] = []
    steps.append("parse user language into SI constructible plan")

    scrubbed, phrases = _extract_phrases(prompt)
    tokens = _tokenize_tokens(scrubbed)
    # restore phrase placeholders as single tokens
    restored: list[str] = []
    for t in tokens:
        m = re.match(r"__ph_(\d+)__", t)
        if m:
            restored.append(phrases[int(m.group(1))][1])
        else:
            restored.append(t)
    tokens = restored

    entities: list[dict[str, Any]] = []
    composites: list[dict[str, Any]] = []
    mapped_names: list[str] = []
    missing: list[str] = []
    seen: set[str] = set()

    def add_entity(name: str, maps_to: str, how: str) -> None:
        if maps_to in seen:
            return
        role = role_for_entity(maps_to)
        if not role:
            return
        seen.add(maps_to)
        entities.append({
            "name": name,
            "maps_to": maps_to,
            "role": role,
            "how": how,
        })
        mapped_names.append(maps_to)
        steps.append(f"map {name!r} → {maps_to} ({role})")

    def add_composite(name: str, parts: list[dict[str, Any]], how: str) -> None:
        key = f"composite:{name}"
        if key in seen:
            return
        seen.add(key)
        # validate roles
        clean_parts = []
        for p in parts:
            role = p.get("role")
            if role not in VALID_ROLES:
                continue
            clean_parts.append(dict(p))
        if not clean_parts:
            missing.append(name)
            steps.append(f"reject composite {name!r}: no valid roles")
            return
        composites.append({
            "name": name,
            "parts": clean_parts,
            "how": how,
            "construction": "plan_composite",
        })
        steps.append(f"compose {name!r} from {len(clean_parts)} puzzle pieces ({how})")

    # Phrase hits first
    for phrase, key in phrases:
        if key in COMPOSITE_RECIPES:
            add_composite(key, COMPOSITE_RECIPES[key], "recipe")
        elif key in scene_composer.SHAPES:
            add_entity(phrase, key, "phrase")
        elif key in SYNONYMS:
            add_entity(phrase, SYNONYMS[key], "phrase_synonym")
        else:
            # treat as composite name
            if key in COMPOSITE_RECIPES:
                add_composite(key, COMPOSITE_RECIPES[key], "recipe")
            else:
                add_composite(key, _default_composite_parts(key), "heuristic")

    machines: list[dict[str, Any]] = []

    def add_lathe(name: str, entity: str, how: str = "lathe") -> None:
        key = f"lathe:{entity}"
        if key in seen:
            return
        seen.add(key)
        machines.append({
            "machine": "lathe",
            "name": name,
            "entity": entity,
            "how": how,
            "construction": "lathe",
        })
        steps.append(f"lathe {name!r} as solid of revolution ({entity})")

    def add_extrude(name: str, entity: str, how: str = "extrude") -> None:
        key = f"extrude:{entity}"
        if key in seen:
            return
        seen.add(key)
        machines.append({
            "machine": "extrude",
            "name": name,
            "entity": entity,
            "how": how,
            "construction": "extrude",
            "layers": 4 if entity in ("wall", "brick", "crate") else 1,
        })
        steps.append(f"extrude {name!r} print-lite volume ({entity})")

    for t in tokens:
        if t.startswith("__ph_"):
            continue
        if t in STOP or len(t) < 2:
            continue
        # Machine dialects first (lathe / extrude)
        if t in LATHE_ENTITIES or t in LATHE_OVERRIDE_SHAPES:
            add_lathe(t, t if t in LATHE_ENTITIES or t in LATHE_OVERRIDE_SHAPES else t)
            continue
        if t in EXTRUDE_ENTITIES:
            add_extrude(t, t)
            continue
        if t in scene_composer.SHAPES:
            add_entity(t, t, "native")
            continue
        if t in SYNONYMS:
            mapped = SYNONYMS[t]
            if mapped in LATHE_ENTITIES or mapped in LATHE_OVERRIDE_SHAPES:
                add_lathe(t, mapped, "synonym_lathe")
            elif mapped in EXTRUDE_ENTITIES:
                add_extrude(t, mapped, "synonym_extrude")
            else:
                add_entity(t, mapped, "synonym")
            continue
        if t in COMPOSITE_RECIPES:
            add_composite(t, COMPOSITE_RECIPES[t], "recipe")
            continue
        # skip relation words already handled
        if t in ("left", "right", "of", "near", "beside", "under", "over", "above", "below"):
            continue
        # unknown content word → composite heuristic (not lathe unless keyword)
        if t.isalpha() and t not in seen:
            if any(k in t for k in ("cup", "vase", "pot", "bottle", "column")):
                add_lathe(t, "vase" if "vase" in t else "cup", "heuristic_lathe")
            elif any(k in t for k in ("crate", "box", "block", "wall")):
                add_extrude(t, "crate", "heuristic_extrude")
            else:
                add_composite(t, _default_composite_parts(t), "heuristic")

    # Ensure minimal landscape if we have ground objects but no ground/sky
    has_ground = any(e["role"] == "ground" for e in entities)
    has_bg = any(e["role"] == "bg" for e in entities)
    ground_objects = any(
        e["role"] in (
            "house", "tree", "building", "person", "boat", "fence", "bridge",
            "flower", "bush", "triangle", "disc", "strip", "river",
        )
        for e in entities
    ) or bool(composites) or bool(machines)

    if ground_objects and not has_ground:
        add_entity("grass", "grass", "default_ground")
        steps.append("inject default ground (grass)")
    if (ground_objects or has_ground) and not has_bg:
        add_entity("sky", "sky", "default_sky")
        steps.append("inject default sky")

    # Build SI prompt from known entities + relation language
    # Map tokens for relation parse
    tok_mapped = []
    for t in tokens:
        if t in scene_composer.SHAPES:
            tok_mapped.append(t)
        elif t in SYNONYMS:
            tok_mapped.append(SYNONYMS[t])
        else:
            tok_mapped.append(t)
    rel_bits = _relation_snippets(tok_mapped, set(mapped_names))

    if rel_bits:
        core = " and ".join(rel_bits)
        extras = [m for m in mapped_names if m not in core]
        si_prompt = core
        if extras:
            si_prompt += " with " + " and ".join(extras[:8])
        if "grass" in mapped_names or "sky" in mapped_names:
            if "grass" in mapped_names and "grass" not in si_prompt:
                si_prompt += " on grass"
            if "sky" in mapped_names and "sky" not in si_prompt:
                si_prompt += " under a sky"
    else:
        # "a house and a tree on grass under a sky"
        groundish = []
        skyish = []
        for m in mapped_names:
            role = role_for_entity(m)
            if role in ("bg", "disc_top", "cloud_top", "star_top", "bird"):
                skyish.append(m)
            elif role == "ground":
                groundish.append(m)
            else:
                groundish.append(m)
        parts = []
        objs = [m for m in groundish if role_for_entity(m) != "ground"]
        grounds = [m for m in groundish if role_for_entity(m) == "ground"]
        if objs:
            parts.append("a " + " and a ".join(objs[:10]))
        if grounds:
            parts.append("on " + " and ".join(grounds[:3]))
        if skyish:
            parts.append("under a " + " with a ".join(skyish[:4]))
        elif "sky" in mapped_names:
            parts.append("under a sky")
        si_prompt = " ".join(parts).strip() or prompt

    mood = _mood_from_prompt(prompt)
    if mood:
        steps.append(f"mood knobs from language: {mood}")

    try:
        from image_contract import merge_construction
        tags = []
        if any(e.get("how") == "native" for e in entities):
            tags.append("native")
        if any(e.get("how") in ("synonym", "phrase_synonym", "phrase", "default_ground", "default_sky") for e in entities):
            tags.append("mapped")
        if composites:
            tags.append("composite")
        for m in machines:
            tags.append(m.get("machine") or m.get("construction") or "mill")
        construction = merge_construction(*tags) if tags else "native"
    except Exception:
        construction = "mixed" if (composites or machines) else (
            "mapped" if entities else "native"
        )

    monologue = _build_monologue(prompt, entities, composites, mood, construction, machines)
    outer = _build_outer_voice(construction, entities, composites, missing, machines)

    plan = {
        "version": PLAN_VERSION,
        "source_prompt": prompt,
        "si_prompt": si_prompt,
        "entities": entities,
        "composites": composites,
        "machines": machines,
        "relations_text": rel_bits,
        "camera": mood,
        "missing": missing,
        "construction": construction,
        "monologue": monologue,
        "outer_voice": outer,
        "compile_steps": steps,
        "source": "rules",
        "honesty": "si_construct",
        "not_diffusion": True,
        "stock": "scene_graph",
    }
    return plan


def _build_monologue(
    prompt: str,
    entities: list[dict],
    composites: list[dict],
    mood: dict,
    construction: str,
    machines: Optional[list] = None,
) -> str:
    bits = [
        f"Inner: user asked for {prompt!r}.",
        f"Construction mode={construction} (SI build, not diffusion).",
    ]
    if entities:
        maps = ", ".join(f"{e['name']}→{e['maps_to']}" for e in entities[:12])
        bits.append(f"Map to known shapes: {maps}.")
    for m in (machines or [])[:8]:
        bits.append(
            f"Machine {m.get('machine')}: {m.get('name')} → {m.get('entity')}."
        )
    if composites:
        for c in composites[:6]:
            roles = "+".join(p["role"] for p in c["parts"])
            bits.append(f"Assemble {c['name']} from puzzle pieces [{roles}] ({c.get('how')}).")
    if mood:
        bits.append(f"Camera/mood: {mood}.")
    bits.append("Hand plan to SI raster (mill/lathe/extrude + optional ISP).")
    return " ".join(bits)


def _build_outer_voice(
    construction: str,
    entities: list[dict],
    composites: list[dict],
    missing: list[str],
    machines: Optional[list] = None,
) -> str:
    if construction == "native":
        base = "SI illustration from known shapes in your prompt."
    elif construction == "mapped":
        base = "SI illustration — I mapped your words onto Synthesus shape vocabulary."
    elif construction == "lathe":
        base = "SI illustration — lathe (solid of revolution) construction for round forms."
    elif construction == "extrude":
        base = "SI illustration — extruded / print-lite volumes."
    elif construction == "composite":
        base = (
            "SI illustration — some objects aren't single primitives, so I assembled "
            "them from shape puzzle pieces (procedural stand-ins, not photos)."
        )
    else:
        base = (
            "SI illustration — mill paths, lathe/extrude machines, and/or composites. "
            "Not diffusion; not a real photograph."
        )
    if machines:
        names = ", ".join(
            f"{m.get('name')}({m.get('machine')})" for m in machines[:6]
        )
        base += f" Machines: {names}."
    if composites:
        names = ", ".join(c["name"].replace("_", " ") for c in composites[:5])
        base += f" Composites: {names}."
    if missing:
        base += f" Could not build: {', '.join(missing)}."
    return base


def _extract_json_object(text: str) -> Optional[dict]:
    if not text:
        return None
    text = text.strip()
    # fenced
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def _llm_plan_enabled(use_llm: Optional[bool]) -> bool:
    if use_llm is True:
        return True
    if use_llm is False:
        return False
    env = os.environ.get("SYNTHESUS_IMAGE_LLM_PLAN", "").strip().lower()
    return env in ("1", "true", "yes", "on", "auto")


def llm_enrich_plan(plan: dict[str, Any], timeout_s: float = 8.0) -> dict[str, Any]:
    """Optional Ollama (or OpenAI-compatible) enrich — best effort, never required.

    Asks only for synonym maps + composite part lists using VALID roles.
    Merges into existing rule plan; invalid roles discarded.
    """
    if not _llm_plan_enabled(True):
        return plan

    roles = sorted(VALID_ROLES)
    shapes = sorted(known_entities())[:80]
    system = (
        "You are Synthesus inner monologue for SI image construction (NOT diffusion). "
        "Output ONLY JSON. Map the user scene to known shape entities and optional "
        "composites built from allowed roles. Never invent pixel data."
    )
    user = {
        "task": "scene_plan",
        "user_prompt": plan.get("source_prompt"),
        "allowed_entities": shapes,
        "allowed_roles": roles,
        "schema": {
            "entities": [{"name": "str", "maps_to": "entity from allowed_entities"}],
            "composites": [{
                "name": "str",
                "parts": [{"role": "allowed_role", "dx": 0.0, "dy": 0.0, "scale": 1.0}],
            }],
            "camera": {"look": "photo|cinema|vivid|tv|raw|null", "time_of_day": "0..1|null"},
            "monologue": "short inner strategy",
        },
    }
    prompt = (
        f"{system}\n\nUSER_JSON:\n{json.dumps(user)}\n\n"
        "Respond with JSON only matching schema."
    )

    raw_text = _call_llm_text(prompt, timeout_s=timeout_s)
    if not raw_text:
        plan = dict(plan)
        plan["llm_status"] = "unavailable"
        return plan

    obj = _extract_json_object(raw_text)
    if not obj:
        plan = dict(plan)
        plan["llm_status"] = "parse_fail"
        return plan

    plan = dict(plan)
    plan["llm_status"] = "ok"
    plan["source"] = "llm+rules"
    steps = list(plan.get("compile_steps") or [])
    steps.append("llm enrich merge")

    # merge entities
    seen_maps = {e["maps_to"] for e in plan.get("entities") or []}
    for e in obj.get("entities") or []:
        if not isinstance(e, dict):
            continue
        maps_to = str(e.get("maps_to") or e.get("entity") or "").lower().strip()
        name = str(e.get("name") or maps_to).lower().strip()
        if maps_to in scene_composer.SHAPES and maps_to not in seen_maps:
            role = role_for_entity(maps_to)
            plan.setdefault("entities", []).append({
                "name": name,
                "maps_to": maps_to,
                "role": role,
                "how": "llm",
            })
            seen_maps.add(maps_to)
            steps.append(f"llm map {name!r} → {maps_to}")

    # merge composites
    existing = {c["name"] for c in plan.get("composites") or []}
    for c in obj.get("composites") or []:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or "object").lower().strip().replace(" ", "_")
        if name in existing:
            continue
        parts_in = c.get("parts") or []
        parts = []
        for p in parts_in:
            if not isinstance(p, dict):
                continue
            role = str(p.get("role") or "").lower().strip()
            if role not in VALID_ROLES:
                continue
            parts.append({
                "role": role,
                "entity": str(p.get("entity") or f"{name}_{role}"),
                "dx": float(np.clip(float(p.get("dx") or 0.0), -0.3, 0.3)),
                "dy": float(np.clip(float(p.get("dy") or 0.0), -0.3, 0.3)),
                "scale": float(np.clip(float(p.get("scale") or 1.0), 0.2, 2.0)),
                "color": p.get("color"),
            })
        if parts:
            plan.setdefault("composites", []).append({
                "name": name,
                "parts": parts,
                "how": "llm",
                "construction": "plan_composite",
            })
            existing.add(name)
            steps.append(f"llm composite {name} ({len(parts)} parts)")

    cam = obj.get("camera") if isinstance(obj.get("camera"), dict) else {}
    plan_cam = dict(plan.get("camera") or {})
    if cam.get("look") in ("raw", "photo", "cinema", "vivid", "tv"):
        plan_cam.setdefault("look", cam["look"])
    if cam.get("time_of_day") is not None:
        try:
            plan_cam.setdefault("time_of_day", float(np.clip(float(cam["time_of_day"]), 0, 1)))
        except (TypeError, ValueError):
            pass
    plan["camera"] = plan_cam

    if obj.get("monologue"):
        plan["monologue"] = (
            f"{plan.get('monologue', '')} LLM: {str(obj['monologue'])[:400]}"
        ).strip()

    # rebuild si_prompt lightly if empty entities grew
    if plan.get("entities"):
        names = [e["maps_to"] for e in plan["entities"]]
        objs = [n for n in names if role_for_entity(n) not in ("bg", "ground", None)]
        grounds = [n for n in names if role_for_entity(n) == "ground"]
        skies = [n for n in names if role_for_entity(n) in ("bg", "disc_top", "cloud_top", "star_top")]
        bits = []
        if objs:
            bits.append("a " + " and a ".join(dict.fromkeys(objs)))
        if grounds:
            bits.append("on " + " and ".join(dict.fromkeys(grounds)))
        if skies:
            bits.append("under a " + " with a ".join(dict.fromkeys(skies)))
        if bits:
            plan["si_prompt"] = " ".join(bits)

    # construction label
    if plan.get("composites") and plan.get("entities"):
        plan["construction"] = "mixed"
    elif plan.get("composites"):
        plan["construction"] = "composite"
    plan["compile_steps"] = steps
    plan["outer_voice"] = _build_outer_voice(
        plan["construction"], plan.get("entities") or [], plan.get("composites") or [],
        plan.get("missing") or [],
    )
    return plan


def _call_llm_text(prompt: str, timeout_s: float = 8.0) -> Optional[str]:
    """Minimal Ollama generate call; returns None on any failure."""
    model = os.environ.get("SYNTHESUS_MODEL", "llama3.2:3b")
    base = os.environ.get("OLLAMA_API_URL", "http://localhost:11434")
    # support both .../api/generate and host root
    if base.rstrip("/").endswith("/api/generate"):
        url = base
    else:
        url = base.rstrip("/") + "/api/generate"
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 512},
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("response") or data.get("text")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def compile_scene_plan(
    prompt: str,
    *,
    use_llm: Optional[bool] = None,
    llm_timeout_s: float = 8.0,
) -> dict[str, Any]:
    """Full compile: rules always; optional LLM enrich when enabled."""
    plan = compile_scene_plan_rules(prompt)
    if _llm_plan_enabled(use_llm):
        try:
            plan = llm_enrich_plan(plan, timeout_s=llm_timeout_s)
        except Exception as exc:
            plan = dict(plan)
            plan["llm_status"] = f"error:{type(exc).__name__}"
    else:
        plan["llm_status"] = "skipped"
    return plan


def plan_fingerprint(plan: dict[str, Any]) -> str:
    raw = json.dumps(
        {
            "v": plan.get("version"),
            "si": plan.get("si_prompt"),
            "e": [(x.get("maps_to"), x.get("how")) for x in plan.get("entities") or []],
            "c": [
                (x.get("name"), [(p.get("role"), p.get("dx"), p.get("dy")) for p in x.get("parts") or []])
                for x in plan.get("composites") or []
            ],
            "m": [
                (x.get("machine"), x.get("entity"), x.get("name"))
                for x in plan.get("machines") or []
            ],
            "cam": plan.get("camera"),
        },
        sort_keys=True,
    )
    import hashlib
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _prim_for_role(
    role: str,
    entity: str,
    *,
    cx: float,
    base: float,
    scale: float,
    color: Optional[tuple],
    horizon: float,
    rng: np.random.Generator,
) -> dict[str, Any]:
    """Build a paintable primitive matching vsa_pipeline_image conventions."""
    sc = float(np.clip(scale, 0.2, 2.5))
    col = color
    if col is None:
        # scene_composer DEFAULT is 0-255
        rgb = scene_composer.DEFAULT.get(role, (150, 150, 150))
        col = (rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0)
    elif len(col) == 3 and max(col) > 1.5:
        col = (col[0] / 255.0, col[1] / 255.0, col[2] / 255.0)
    prim: dict[str, Any] = {
        "entity": entity,
        "role": role,
        "color": tuple(float(c) for c in col[:3]),
        "construction": "plan_composite",
    }
    base = float(np.clip(base, 0.35, 0.95))
    cx = float(np.clip(cx, 0.05, 0.95))

    if role == "bg":
        prim.update(x=0.0, y=0.0, w=1.0, h=1.0)
    elif role == "ground":
        prim.update(y0=horizon)
    elif role == "strip":
        prim.update(y0=base, h=0.05 * sc, taper=0.35)
    elif role == "river":
        prim.update(y0=base, h=0.045 * sc, meander=0.03)
    elif role == "disc_top":
        prim.update(x=cx, y=float(np.clip(base, 0.05, 0.5)), r=0.06 * sc)
    elif role == "cloud_top":
        prim.update(x=cx, y=float(np.clip(base, 0.05, 0.45)), r=0.06 * sc)
    elif role == "star_top":
        prim.update(x=cx, y=float(np.clip(base, 0.04, 0.45)), r=0.03 * sc, points=5)
    elif role == "bird":
        prim.update(x=cx, y=float(np.clip(base, 0.08, 0.5)), s=0.03 * sc)
    elif role == "triangle":
        prim.update(cx=cx, base=base, h=0.28 * sc, hw=0.22 * sc)
    elif role == "disc":
        r = 0.06 * sc
        prim.update(x=cx, y=base - r * 0.95, r=r)
    elif role == "tree":
        prim.update(x=cx, base=base, r=0.09 * sc, fractal=True)
    elif role == "bush":
        prim.update(x=cx, base=base, r=0.05 * sc)
    elif role == "house":
        prim.update(cx=cx, base=base, w=0.14 * sc, h=0.12 * sc)
    elif role == "building":
        prim.update(cx=cx, base=base, w=0.10 * sc, h=0.18 * sc)
    elif role == "fence":
        prim.update(
            x0=float(np.clip(cx - 0.1 * sc, 0.05, 0.7)),
            x1=float(np.clip(cx + 0.1 * sc, 0.2, 0.95)),
            base=base,
            h=0.055 * sc,
        )
    elif role == "boat":
        prim.update(x=cx, y=base, w=0.10 * sc, h=0.035 * sc)
    elif role == "person":
        prim.update(x=cx, base=base, h=0.10 * sc)
    elif role == "flower":
        prim.update(x=cx, base=base, r=0.025 * sc)
    elif role == "bridge":
        prim.update(cx=cx, base=base, w=0.2 * sc, h=0.07 * sc)
    else:
        prim.update(x=cx, y=base, r=0.05 * sc)
    return prim


def inject_composites(
    doc: list[dict[str, Any]],
    plan: dict[str, Any],
    horizon: float,
    *,
    seed: Optional[int] = None,
    path_mode: bool = True,
) -> list[dict[str, Any]]:
    """Append composite puzzle-pieces + lathe/extrude machine prims to a scene document."""
    composites = plan.get("composites") or []
    machines = plan.get("machines") or []
    if not composites and not machines:
        return doc

    rng = np.random.default_rng(int(seed) if seed is not None else 0)
    n = len(composites) + len(machines)
    xs = np.linspace(0.28, 0.78, max(n, 1)) if n else []
    out = list(doc)
    slot = 0

    for i, comp in enumerate(composites):
        ax = float(comp.get("anchor_x") if comp.get("anchor_x") is not None else xs[slot % len(xs)])
        slot += 1
        ax = float(np.clip(ax + float(rng.uniform(-0.03, 0.03)), 0.12, 0.88))
        base = float(np.clip(horizon + float(comp.get("anchor_yoff") or 0.0), 0.45, 0.9))
        parts = comp.get("parts") or []
        for j, part in enumerate(parts):
            role = part.get("role")
            if role not in VALID_ROLES:
                continue
            entity = str(part.get("entity") or f"{comp.get('name', 'obj')}_{role}")
            cx = ax + float(part.get("dx") or 0.0)
            b = base + float(part.get("dy") or 0.0)
            if role in ("disc_top", "cloud_top", "star_top", "bird"):
                b = float(np.clip(0.15 + float(part.get("dy") or 0.0), 0.05, 0.45))
            color = part.get("color")
            if isinstance(color, (list, tuple)) and len(color) >= 3:
                color = tuple(color[:3])
            else:
                color = None
            prim = _prim_for_role(
                role,
                entity,
                cx=cx,
                base=b,
                scale=float(part.get("scale") or 1.0),
                color=color,
                horizon=horizon,
                rng=rng,
            )
            prim["composite_of"] = comp.get("name")
            prim["construction"] = "plan_composite"
            prim["machine"] = "composite"
            if path_mode:
                try:
                    import cnc_paths as _cnc
                    ps = _cnc.paths_for_primitive(prim, seed=int(seed or 0) + 1000 + i * 50 + j)
                    if ps:
                        for pth in ps:
                            pth.meta["no_pocket"] = bool(part.get("no_pocket", False))
                        prim["paths"] = ps
                        prim["path_ops"] = _cnc.path_provenance(ps)
                except Exception:
                    pass
            out.append(prim)

    # Lathe / extrude machines
    for mi, mach in enumerate(machines):
        ax = float(mach.get("anchor_x") if mach.get("anchor_x") is not None else xs[slot % len(xs)])
        slot += 1
        ax = float(np.clip(ax + float(rng.uniform(-0.02, 0.02)), 0.15, 0.85))
        base = float(np.clip(horizon + float(mach.get("anchor_yoff") or 0.0), 0.5, 0.9))
        entity = str(mach.get("entity") or mach.get("name") or "object")
        kind = (mach.get("machine") or "lathe").lower()
        if kind == "lathe":
            try:
                import lathe_paths as _lathe
                colors = {
                    "cup": (0.85, 0.85, 0.9),
                    "vase": (0.7, 0.35, 0.28),
                    "column": (0.75, 0.72, 0.65),
                    "bottle": (0.3, 0.55, 0.4),
                    "apple": (0.75, 0.2, 0.15),
                    "fruit": (0.85, 0.45, 0.15),
                    "pot": (0.55, 0.4, 0.3),
                    "bowl": (0.6, 0.55, 0.5),
                }
                col = colors.get(entity, (0.55, 0.45, 0.38))
                hgt = 0.10 if entity in ("cup", "bowl", "apple", "fruit") else 0.14
                if entity in ("column", "vase", "bottle"):
                    hgt = 0.18
                r = 0.045 if entity in ("cup", "bottle") else 0.055
                prim = _lathe.lathe_primitive(
                    entity, cx=ax, base=base, height=hgt, max_radius=r, color=col,
                )
            except Exception:
                prim = {
                    "entity": entity, "role": "lathe", "cx": ax, "base": base,
                    "h": 0.12, "r": 0.05, "color": (0.55, 0.45, 0.4),
                    "construction": "lathe", "machine": "lathe",
                }
        else:
            try:
                import extrude_paths as _ex
                layers = int(mach.get("layers") or 1)
                prim = _ex.extrude_primitive(
                    entity, cx=ax, base=base, width=0.11, height=0.14,
                    color=(0.5, 0.48, 0.45), layers=layers,
                )
            except Exception:
                prim = {
                    "entity": entity, "role": "extrude", "cx": ax, "base": base,
                    "w": 0.11, "h": 0.14, "color": (0.5, 0.48, 0.45),
                    "layers": 1, "construction": "extrude", "machine": "extrude",
                }
        out.append(prim)
    return out


def public_plan_view(plan: dict[str, Any], *, full: bool = False) -> dict[str, Any]:
    """API-safe plan summary."""
    view = {
        "version": plan.get("version"),
        "si_prompt": plan.get("si_prompt"),
        "construction": plan.get("construction"),
        "honesty": plan.get("honesty", "si_construct"),
        "not_diffusion": True,
        "source": plan.get("source"),
        "llm_status": plan.get("llm_status"),
        "outer_voice": plan.get("outer_voice"),
        "monologue": plan.get("monologue"),
        "entity_maps": [
            {"name": e.get("name"), "maps_to": e.get("maps_to"), "role": e.get("role"), "how": e.get("how")}
            for e in (plan.get("entities") or [])
        ],
        "composites": [
            {
                "name": c.get("name"),
                "how": c.get("how"),
                "parts": [p.get("role") for p in (c.get("parts") or [])],
            }
            for c in (plan.get("composites") or [])
        ],
        "machines": [
            {
                "machine": m.get("machine"),
                "name": m.get("name"),
                "entity": m.get("entity"),
            }
            for m in (plan.get("machines") or [])
        ],
        "camera": plan.get("camera") or {},
        "missing": plan.get("missing") or [],
        "fingerprint": plan_fingerprint(plan),
        "stock": "scene_graph",
    }
    if full:
        view["compile_steps"] = plan.get("compile_steps")
        view["raw_composites"] = plan.get("composites")
    return view


def demo():
    samples = [
        "a lonely cabin by a creek at golden hour",
        "espresso machine on a table under a sky",
        "a robot near a house on grass",
        "draw a windmill and a barn at dusk",
    ]
    for s in samples:
        p = compile_scene_plan(s, use_llm=False)
        print("===", s)
        print("si_prompt:", p["si_prompt"])
        print("construction:", p["construction"], "composites:", [c["name"] for c in p["composites"]])
        print("outer:", p["outer_voice"][:120], "...")
        print()


if __name__ == "__main__":
    demo()
