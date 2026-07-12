"""Golden / parity tests for SI image generation (feat/image-roundout).

Proves:
  - house / star / multi-object actually enter the graph and paint
  - multi-object layout spreads x positions (not all at 0.5)
  - styles and aspect are accepted
  - cache hits on identical params
  - real PNG bytes produced
  - ImageRequest / ImageResponse schemas validate
  - every SHAPES role has a paint path (no silent drop)
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
for _path in (
    ROOT / "packages" / "reasoning",
    ROOT / "packages" / "api",
    ROOT / "packages",
    ROOT,
):
    _value = str(_path)
    if _value not in sys.path:
        sys.path.insert(0, _value)

import scene_composer  # noqa: E402
import vsa_pipeline_image as vpi  # noqa: E402
from image_service import (  # noqa: E402
    clear_image_cache,
    generate_image,
    renderable_vocabulary,
    cache_stats,
)


# Roles that must have explicit paint branches in render_doc
PAINTABLE_ROLES = frozenset({
    "bg", "ground", "disc_top", "cloud_top", "star_top",
    "triangle", "disc", "tree", "house",
    # image-studio expansions
    "strip", "river", "fence", "boat", "person", "building",
    "flower", "bird", "bridge", "bush",
})


def test_vocab_roles_are_all_paintable():
    roles = set(scene_composer.SHAPES.values())
    missing = roles - PAINTABLE_ROLES
    assert not missing, f"SHAPES roles missing from renderer: {missing}"


def test_house_and_star_in_document_and_png():
    prompt = "a house and a star on green grass under a blue sky with a sun"
    doc, horizon = vpi.pattern_document(prompt, seed=11, style="flat")
    entities = {p["entity"] for p in doc}
    roles = {p["role"] for p in doc}
    assert "house" in entities
    assert "star" in entities
    assert "house" in roles
    assert "star_top" in roles

    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "house_star.png")
        vpi.render_doc(doc, horizon, res=256, out=out, style="flat", seed=11)
        assert os.path.getsize(out) > 800
        arr = np.asarray(Image.open(out).convert("RGB"))
        # Not a blank / near-white canvas
        assert arr.std() > 5.0


def test_multi_object_layout_spreads_x():
    prompt = "an apple and a ball and a rock and a tree and a house on grass under sky"
    doc, _ = vpi.pattern_document(prompt, seed=5, style="flat")
    xs = []
    for p in doc:
        if p["role"] in vpi.GROUND_ROLES:
            if "x" in p:
                xs.append(p["x"])
            elif "cx" in p:
                xs.append(p["cx"])
    assert len(xs) >= 3, f"expected multiple ground objects, got {xs}"
    # Spread: not all collapsed to the same x
    assert max(xs) - min(xs) > 0.12, f"objects not spread: {xs}"


def test_styles_and_aspect_produce_real_pngs():
    clear_image_cache()
    with tempfile.TemporaryDirectory() as td:
        for style in ("flat", "soft", "night"):
            out = os.path.join(td, f"{style}.png")
            meta = generate_image(
                "a mountain and a tree on grass under a sky with a moon",
                out,
                res=256,
                style=style,
                seed=2,
                aspect=1.5,
                use_cache=False,
            )
            assert meta["style"] == style
            assert meta["entity_count"] >= 2
            im = Image.open(out)
            w, h = im.size
            assert w > h  # aspect 1.5 → wider
            assert os.path.getsize(out) > 500


def test_cache_hit_on_second_call():
    clear_image_cache()
    prompt = "a red apple on green grass under a blue sky with a sun"
    with tempfile.TemporaryDirectory() as td:
        a = os.path.join(td, "a.png")
        b = os.path.join(td, "b.png")
        m1 = generate_image(prompt, a, res=256, style="flat", seed=9)
        m2 = generate_image(prompt, b, res=256, style="flat", seed=9)
        assert m1["cache_hit"] is False
        assert m2["cache_hit"] is True
        assert os.path.getsize(a) == os.path.getsize(b)
        assert cache_stats()["size"] >= 1


def test_empty_prompt_raises():
    with tempfile.TemporaryDirectory() as td:
        with pytest.raises(ValueError):
            generate_image("  ", os.path.join(td, "x.png"))


def test_renderable_vocabulary_nonempty():
    vocab = renderable_vocabulary()
    assert "house" in vocab
    assert "star" in vocab
    assert "tree" in vocab
    assert len(vocab) >= 20


def test_image_schemas():
    # Prefer api package path; knowledge/schemas.py shadows bare "schemas".
    try:
        from api.schemas import ImageRequest, ImageResponse
    except ImportError:
        import importlib.util
        path = ROOT / "packages" / "api" / "schemas.py"
        spec = importlib.util.spec_from_file_location("api_schemas_image", path)
        mod = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(mod)
        ImageRequest, ImageResponse = mod.ImageRequest, mod.ImageResponse

    req = ImageRequest(prompt="a sun over grass", resolution=512, style="soft", aspect=1.0)
    assert req.resolution == 512
    with pytest.raises(Exception):
        ImageRequest(prompt="ok", resolution=50)  # below 128

    resp = ImageResponse(
        ok=True,
        prompt="a sun over grass",
        resolution=512,
        entities=["sun", "grass"],
        entity_count=2,
        image_base64="AAAA",
        style="soft",
    )
    assert resp.engine == "synthesus_vsa_geometric"


def test_known_entity_coverage_measure():
    """Organism-style bar: known SHAPES words in prompt appear in the doc."""
    tests = [
        "a red apple on green grass under a blue sky with a sun",
        "a mountain and a tree on grass under a sky with a cloud",
        "a house and a star under a night sky over snow",
        "a boat on a river under a sky with a bird",
        "a person left of a house near a fence and a flower",
    ]
    tot = cov = 0
    for req in tests:
        known = [w for w in req.lower().split() if w in scene_composer.SHAPES]
        doc, _ = vpi.pattern_document(req, seed=1, style="flat")
        rendered = {p["entity"] for p in doc}
        for w in known:
            tot += 1
            cov += int(w in rendered)
    score = cov / tot if tot else 0.0
    assert score >= 0.9, f"entity coverage {score:.2f} below 0.9 ({cov}/{tot})"


def test_relation_left_of_places_subject_left():
    doc, _ = vpi.pattern_document(
        "a tree left of a house on grass under a sky",
        seed=3, style="flat",
    )
    by_ent = {p["entity"]: p for p in doc}
    assert "tree" in by_ent and "house" in by_ent
    tx = by_ent["tree"].get("x", by_ent["tree"].get("cx"))
    hx = by_ent["house"].get("x", by_ent["house"].get("cx"))
    assert tx is not None and hx is not None
    assert tx < hx, f"tree ({tx}) should be left of house ({hx})"


def test_relation_right_of_places_subject_right():
    doc, _ = vpi.pattern_document(
        "a person right of a building on grass under a sky",
        seed=4, style="flat",
    )
    by_ent = {p["entity"]: p for p in doc}
    assert "person" in by_ent and "building" in by_ent
    px = by_ent["person"].get("x", by_ent["person"].get("cx"))
    bx = by_ent["building"].get("x", by_ent["building"].get("cx"))
    assert px > bx, f"person ({px}) should be right of building ({bx})"


def test_studio_vocab_entities_paint():
    prompt = (
        "a road and a river and a fence and a boat and a person and a building "
        "and a flower and a bird and a bridge and a bush on grass under a sky"
    )
    doc, horizon = vpi.pattern_document(prompt, seed=8, style="soft")
    entities = {p["entity"] for p in doc}
    for e in ("road", "river", "fence", "boat", "person", "building",
              "flower", "bird", "bridge", "bush"):
        assert e in entities, f"missing entity {e}"
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "studio.png")
        vpi.render_doc(doc, horizon, res=320, out=out, style="soft", seed=8)
        assert os.path.getsize(out) > 1000
        arr = np.asarray(Image.open(out).convert("RGB"))
        assert arr.std() > 5.0
