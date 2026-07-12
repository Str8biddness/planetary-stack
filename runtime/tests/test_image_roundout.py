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
    # Wipe memory + disk so first call is a true miss (disk cache survives restarts).
    clear_image_cache(disk=True)
    prompt = "a red apple on green grass under a blue sky with a sun"
    with tempfile.TemporaryDirectory() as td:
        a = os.path.join(td, "a.png")
        b = os.path.join(td, "b.png")
        m1 = generate_image(prompt, a, res=256, style="flat", seed=9, look="raw")
        m2 = generate_image(prompt, b, res=256, style="flat", seed=9, look="raw")
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
        vpi.render_doc(doc, horizon, res=320, out=out, style="soft", seed=8, detail="high")
        assert os.path.getsize(out) > 1000
        arr = np.asarray(Image.open(out).convert("RGB"))
        assert arr.std() > 5.0


def test_detail_high_and_variations():
    from image_service import generate_image, generate_variations, clear_image_cache

    clear_image_cache()
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "high.png")
        m = generate_image(
            "a tree on grass under a sky with a sun",
            out,
            res=256,
            style="soft",
            seed=1,
            detail="high",
            look="raw",
            use_cache=True,
        )
        assert m["detail"] == "high"
        assert os.path.getsize(out) > 500
        m2 = generate_image(
            "a tree on grass under a sky with a sun",
            os.path.join(td, "high2.png"),
            res=256,
            style="soft",
            seed=1,
            detail="high",
            look="raw",
        )
        assert m2["cache_hit"] is True

    vars_ = generate_variations(
        "a boat on a river under a sky",
        n=3, res=192, style="soft", detail="standard", look="raw",
    )
    assert len(vars_) == 3
    seeds = {v["seed"] for v in vars_}
    assert len(seeds) == 3
    assert all(v.get("image_base64") for v in vars_)


def test_orbit_day_sequence():
    from image_service import generate_orbit_day, clear_image_cache

    clear_image_cache(disk=True)
    frames = generate_orbit_day(
        "a house and a tree on grass under a sky with a sun",
        n=3,
        yaw_span=24,
        t0=0.2,
        t1=0.9,
        res=128,
        style="soft",
        look="raw",
        detail="standard",
        path_mode=False,
        use_cache=False,
        seed=5,
        as_gif=True,
        gif_duration_ms=200,
    )
    assert len(frames) == 3
    assert frames[0]["yaw_deg"] != frames[-1]["yaw_deg"]
    assert frames[0]["time_of_day"] < frames[-1]["time_of_day"]
    assert frames[0].get("orbit_day") is True
    assert frames[0].get("animation") and frames[0]["animation"]["frame_count"] == 3
    assert frames[0]["animation"].get("kind") == "orbit_day"


def test_pitch_gif_and_level_export():
    import world_camera as wc
    import gif_export as ge
    import level_export as le
    from image_service import generate_time_sequence, clear_image_cache

    # Pitch shifts horizon / object bases
    doc = [
        {"entity": "sky", "role": "bg", "color": (0.4, 0.6, 0.9)},
        {"entity": "grass", "role": "ground", "color": (0.3, 0.5, 0.3), "y0": 0.66},
        {"entity": "house", "role": "house", "color": (0.7, 0.4, 0.3),
         "cx": 0.5, "base": 0.66, "w": 0.14, "h": 0.12},
    ]
    d_up, m_up = wc.project_view(doc, pitch_deg=15)
    d_dn, m_dn = wc.project_view(doc, pitch_deg=-15)
    assert m_up["horizon"] != m_dn["horizon"]
    assert "pitch" in m_up.get("axis", [])

    # Level export
    lvl = le.build_level_from_prompt(
        "a house and a tree on grass under a sky",
        seed=2, yaw_deg=5, pitch_deg=-5,
    )
    assert lvl["schema"] == le.LEVEL_SCHEMA
    assert lvl["entity_count"] >= 2
    assert lvl["not_diffusion"] is True
    js = le.level_to_json(lvl)
    assert "entities" in js

    # GIF from time sequence
    clear_image_cache(disk=True)
    frames = generate_time_sequence(
        "a house on grass under a sky with a sun",
        n=2, t0=0.2, t1=0.9, res=128, style="soft", look="raw",
        detail="standard", path_mode=False, use_cache=False, seed=1,
        as_gif=True, gif_duration_ms=200,
    )
    assert len(frames) == 2
    assert frames[0].get("animation") and frames[0]["animation"]["frame_count"] == 2
    assert frames[0]["animation"]["bytes"] > 50

    # Direct gif helper
    anim = ge.frames_to_data_url(frames, fmt="gif", duration_ms=150)
    assert anim["mime_type"] == "image/gif"


def test_world_camera_multiview_and_time():
    import world_camera as wc
    from image_service import generate_multiview, generate_time_sequence, clear_image_cache

    yaws = wc.yaw_schedule(3, 30)
    assert len(yaws) == 3 and yaws[1] == 0.0
    times = wc.time_schedule(4, 0.1, 0.9)
    assert len(times) == 4 and times[0] < times[-1]

    doc = [
        {"entity": "sky", "role": "bg", "color": (0.4, 0.6, 0.9)},
        {"entity": "grass", "role": "ground", "color": (0.3, 0.5, 0.3), "y0": 0.66},
        {"entity": "house", "role": "house", "color": (0.7, 0.4, 0.3),
         "cx": 0.55, "base": 0.66, "w": 0.14, "h": 0.12},
    ]
    d_left, m = wc.project_view(doc, yaw_deg=-20)
    d_right, _ = wc.project_view(doc, yaw_deg=20)
    # Near house should shift opposite directions for opposite yaws
    assert d_left[2]["cx"] != d_right[2]["cx"]
    _, m_night = wc.project_view(doc, time_of_day=0.95)
    assert m_night.get("style_hint") == "night"

    clear_image_cache(disk=True)
    views = generate_multiview(
        "a house and a tree on grass under a sky with a sun",
        n=2, yaw_span=20, res=192, style="soft", look="raw",
        detail="standard", path_mode=True, use_cache=False, seed=3,
    )
    assert len(views) == 2
    assert views[0]["yaw_deg"] != views[1]["yaw_deg"]
    assert all(v.get("image_base64") for v in views)

    frames = generate_time_sequence(
        "a house on grass under a sky",
        n=2, t0=0.15, t1=0.95, res=160, style="soft", look="raw",
        detail="standard", path_mode=False, use_cache=False, seed=2,
    )
    assert len(frames) == 2
    assert frames[0]["time_of_day"] < frames[1]["time_of_day"]


def test_presets_and_depth_buffer():
    import scene_presets as sp
    import depth_buffer as db

    catalog = sp.list_presets()
    assert len(catalog) >= 6
    p = sp.get_preset("cottage_dawn")
    assert p and "cottage" in p["prompt"].lower()
    body = sp.apply_preset_to_request({"preset": "harbor_day"})
    assert "boat" in body["prompt"]
    assert body.get("look")

    h, w = 32, 48
    depth = db.make_depth_buffer(h, w)
    mask = np.ones((h, w), dtype=np.float32)
    mask[:10, :] = 0
    db.write_depth(depth, mask, 0.3)
    assert depth.max() <= 1.0
    assert float(depth[20, 10]) <= 0.35
    z = db.depth_for_primitive({"role": "person", "base": 0.75})
    assert 0.0 <= z <= 1.0
    fd = db.focus_from_doc([{"role": "person", "base": 0.7}, {"role": "tree", "base": 0.66}])
    assert 0.0 <= fd <= 1.0


def test_materials_and_sky_modules():
    import materials as mat
    import sky_model as sky

    m = mat.resolve_material("water", "river")
    assert m["fresnel"] > 0.1
    assert m["roughness"] < 0.5

    h, w = 48, 64
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    yy /= max(h - 1, 1)
    xx /= max(w - 1, 1)
    sk = sky.render_sky(xx, yy, sun_pos=(0.7, 0.2), style="soft")
    assert sk.shape == (h, w, 3)
    assert sk.mean() > 0.05

    img = np.zeros((h, w, 3), dtype=np.float32)
    mask = (np.sqrt((xx - 0.5) ** 2 + (yy - 0.5) ** 2) < 0.25).astype(np.float32)
    mat.blend_shaded(img, mask, (0.2, 0.5, 0.3), xx, yy, (0.7, 0.2), entity="grass")
    assert img.max() > 0.05


def test_cnc_path_engine_and_render():
    """CNC path math builds form; path_mode paint produces real PNG + ops sample."""
    import cnc_paths as cnc
    from image_service import generate_image, clear_image_cache

    # Unit: house contour closed, discretize, fill mask nonzero
    hp = cnc.house_contour(0.5, 0.66, 0.16, 0.14)
    assert hp.closed
    poly = cnc.discretize(hp)
    assert len(poly) >= 4
    ops = cnc.path_provenance([hp])
    assert any(o.startswith("G1") for o in ops)

    # Offset multi-pass
    offs = cnc.multi_pass_offsets(poly, 0.01, passes=2, closed=True)
    assert len(offs) == 2

    clear_image_cache()
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "cnc.png")
        m = generate_image(
            "a house and a tree and a person on grass under a sky",
            path,
            res=256,
            style="soft",
            look="raw",
            detail="standard",
            seed=11,
            path_mode=True,
            use_cache=False,
        )
        assert m.get("path_mode") is True
        assert (m.get("path_entities") or 0) >= 2
        assert "cnc_paths" in (m.get("engine") or "")
        assert os.path.getsize(path) > 800
        # legacy path_mode off still works
        m2 = generate_image(
            "a house on grass under a sky",
            os.path.join(td, "legacy.png"),
            res=192,
            look="raw",
            path_mode=False,
            use_cache=False,
        )
        assert m2.get("path_mode") is False


def test_camera_isp_photo_look():
    """Camera/TV ISP produces real PNG + pipeline meta (not diffusion)."""
    import camera_isp as isp
    from image_service import generate_image, clear_image_cache

    # Unit: ISP alone
    h, w = 64, 96
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    yy /= h - 1
    img = np.stack([0.4 + 0.3 * (1 - yy), 0.45 * np.ones_like(yy), 0.55 - 0.2 * yy], -1)
    out = isp.apply_camera_look(img, yy, horizon=0.66, look="photo", seed=2)
    assert out["image"].shape == (h, w, 3)
    assert out["meta"]["engine"] == "synthesus_camera_isp"
    assert "filmic" in out["meta"]["pipeline"]
    assert "ae_gain" in "".join(out["meta"]["pipeline"]) or out["meta"].get("ae_gain")

    clear_image_cache()
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "photo.png")
        m = generate_image(
            "a house and a tree on grass under a sky with a sun",
            path,
            res=256,
            style="photo",
            look="photo",
            detail="high",
            seed=9,
            use_cache=False,
        )
        assert os.path.getsize(path) > 800
        assert m.get("look") == "photo"
        assert "camera_isp" in (m.get("engine") or "")
        assert m.get("isp") is not None
        arr = np.asarray(Image.open(path).convert("RGB"))
        assert arr.std() > 5.0
