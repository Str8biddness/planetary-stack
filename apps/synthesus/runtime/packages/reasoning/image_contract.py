#!/usr/bin/env python3
"""SI image honesty contract — construction modes and truth labels.

Stock of truth = scene graph + plan (not the PNG).
Picture edits are post-raster and must not claim SI rebuilt the world.
"""
from __future__ import annotations

from typing import Any, Optional

# Construction / product modes (meta.construction and plan.construction)
CONSTRUCTION_MODES = frozenset({
    "native",       # only SHAPES tokens from prompt
    "mapped",       # synonyms → known entities
    "composite",    # puzzle pieces from roles
    "mixed",        # mapped + composite and/or machine dialects
    "lathe",        # solids of revolution
    "extrude",      # print-lite / extruded contours
    "mill",         # CNC contour/pocket (default path language)
    "retrieved",    # real media (not SI construct)
    "picture_edit", # post-raster grade/text (not new construction)
})

HONESTY_SI = "si_construct"
HONESTY_RETRIEVED = "retrieved_media"
HONESTY_PICTURE = "picture_edit"

MACHINE_DIALECTS = frozenset({"mill", "lathe", "extrude", "composite"})


def normalize_construction(value: Optional[str], default: str = "native") -> str:
    v = (value or default).lower().strip()
    if v not in CONSTRUCTION_MODES:
        return default
    return v


def merge_construction(*parts: Optional[str]) -> str:
    """Combine construction tags from plan + machines into one label."""
    found = [normalize_construction(p) for p in parts if p]
    if not found:
        return "native"
    s = set(found)
    if "retrieved" in s:
        return "retrieved"
    if "picture_edit" in s and len(s) == 1:
        return "picture_edit"
    machine = s & {"lathe", "extrude", "composite", "mill"}
    mapped = "mapped" in s or "native" in s
    if len(machine) > 1 or (machine and mapped and ("composite" in machine or len(s) > 2)):
        return "mixed"
    if "lathe" in machine and not ({"extrude", "composite"} & machine):
        return "lathe" if not mapped or s <= {"lathe", "native", "mapped", "mill"} else "mixed"
    if "extrude" in machine and not ({"lathe", "composite"} & machine):
        return "extrude" if s <= {"extrude", "native", "mapped", "mill"} else "mixed"
    if "composite" in machine:
        return "mixed" if mapped or len(machine) > 1 else "composite"
    if "mapped" in s:
        return "mapped"
    return found[-1]


def base_meta_flags(
    *,
    construction: str = "native",
    honesty: str = HONESTY_SI,
) -> dict[str, Any]:
    return {
        "construction": normalize_construction(construction),
        "honesty": honesty,
        "not_diffusion": True,
        "stock": "scene_graph",  # PNG is a readout, not the workpiece
    }
