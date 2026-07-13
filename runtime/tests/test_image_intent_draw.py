"""image_intent draw-trigger coverage (loose ends)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages" / "reasoning"))
sys.path.insert(0, str(ROOT / "packages"))

from image_intent import classify_intent  # noqa: E402


def test_make_picture_of_is_draw():
    for msg in (
        "make a picture of a house on grass",
        "make an image of a tree under a sky",
        "create a picture of a river and a boat",
        "generate a drawing of a cabin at dusk",
        "produce an illustration of a mountain",
        "please make me a picture of a sun over grass",
        "make a sketch of a bridge",
    ):
        r = classify_intent(msg)
        assert r["mode"] == "draw", (msg, r)
        assert r.get("prompt")
        # subject extracted (not the whole make-a-picture phrase as sole content)
        assert "house" in r["prompt"] or "tree" in r["prompt"] or "river" in r["prompt"] \
            or "cabin" in r["prompt"] or "mountain" in r["prompt"] or "sun" in r["prompt"] \
            or "bridge" in r["prompt"] or "grass" in r["prompt"]


def test_classic_draw_still_works():
    r = classify_intent("draw a house left of a river")
    assert r["mode"] == "draw"
    assert "house" in r["prompt"]


def test_make_coffee_is_not_draw():
    """Bare make X without picture/image/drawing must not become draw."""
    for msg in (
        "make coffee",
        "make a sandwich",
        "create a plan for dinner",
        "generate a report",
        "make me happy",
    ):
        r = classify_intent(msg)
        assert r["mode"] != "draw", (msg, r)


def test_find_still_find():
    r = classify_intent("find photo of a barn")
    assert r["mode"] == "find"
