"""Distributed forge rendering — correctness and the three failure modes.

House style: prove the refusals, not just the happy path. The dangerous, silent
outcomes here are a seam (a tile rendered against the wrong coordinates or a
skewed engine) and a straggler that quietly makes distribution slower than doing
the work locally. Each has a test that would fail loudly if the guard were
removed.
"""

from __future__ import annotations

import pytest

from services.forge_render.engine import (
    ENGINE_VERSION,
    EngineVersionMismatch,
    Recipe,
    Surface,
    composite,
    render_full,
    render_tile,
    to_png,
)
from services.forge_render.farm import (
    RenderJob,
    Worker,
    WorkStealingScheduler,
    capability_weighted_tiles,
    estimate_cost,
    plan_render,
    split_tiles,
    steal_schedule,
)

W, H = 64, 48
QUALITY = 40
RECIPE = Recipe.from_code("SF1.0.6.42.285.60.0.42")
GYROID = Recipe.from_code("SF1.3.5.30.312.90.1.38")


def _bytes(surf: Surface) -> bytes:
    return bytes(surf.data)


# ----------------------------------------------------------------- seamless


def test_tiles_composite_byte_identically_to_the_whole_frame():
    """The core claim: every pixel is computed from full-frame coordinates, so
    a tiled render is the same image as a single render — no seam."""
    full = render_full(RECIPE, W, H, quality=QUALITY)
    job = RenderJob(recipe=RECIPE, full_w=W, full_h=H, quality=QUALITY)
    frame, results = WorkStealingScheduler(job).render(
        split_tiles(W, H, 3, 2), [Worker("desk"), Worker("phone", speed=0.2)]
    )
    assert len(results) == 6
    assert _bytes(frame) == _bytes(full)


def test_tile_offset_matters_a_tile_is_not_its_own_little_image():
    """A tile rendered as if it were the whole frame would not match. This
    guards the full_w/full_h coordinate discipline that prevents seams."""
    full = render_full(RECIPE, W, H, quality=QUALITY)
    rect = (W // 2, 0, W, H // 2)
    correct = render_tile(RECIPE, W, H, rect, quality=QUALITY)
    # Same pixels as the whole frame in that rect.
    for ay in range(rect[1], rect[3]):
        for ax in range(rect[0], rect[2]):
            assert correct.px(ax, ay) == full.px(ax, ay)


# --------------------------------------------------- cross-boundary effects


def test_bloom_needs_an_overlap_margin_or_it_seams():
    """A screen-space effect reads neighbours. Without an overlap margin the
    tile boundaries differ from the whole frame; with overlap>=radius they are
    identical. This is the classic distributed-rendering seam and its fix."""
    r = 2
    full = render_full(GYROID, W, H, quality=QUALITY, bloom_radius=r, bloom_strength=0.6)
    tiles = split_tiles(W, H, 3, 2)

    def build(overlap):
        job = RenderJob(
            recipe=GYROID, full_w=W, full_h=H, quality=QUALITY,
            overlap=overlap, bloom_radius=r, bloom_strength=0.6,
        )
        frame, _ = WorkStealingScheduler(job).render(tiles, [Worker("a"), Worker("b")])
        return frame

    assert _bytes(build(0)) != _bytes(full), "no-overlap bloom should seam"
    assert _bytes(build(r)) == _bytes(full), "overlap>=radius must reproduce the whole frame"


# ----------------------------------------------------- version-skew refusal


def test_a_node_refuses_a_job_pinned_to_a_different_engine():
    with pytest.raises(EngineVersionMismatch, match="pinned engine"):
        render_tile(RECIPE, W, H, (0, 0, 10, 10), engine_version="forge-cpu-999")


def test_scheduler_fails_closed_when_no_node_matches_the_engine():
    job = RenderJob(recipe=RECIPE, full_w=W, full_h=H, quality=QUALITY)
    stale = [Worker("old-1", engine_version="forge-cpu-0"), Worker("old-2", engine_version="forge-cpu-0")]
    with pytest.raises(EngineVersionMismatch, match="no node"):
        WorkStealingScheduler(job).render(split_tiles(W, H, 2, 2), stale)


def test_mismatched_nodes_are_excluded_not_silently_used():
    job = RenderJob(recipe=RECIPE, full_w=W, full_h=H, quality=QUALITY)
    workers = [Worker("good"), Worker("stale", engine_version="forge-cpu-0")]
    eligible = WorkStealingScheduler(job).eligible(workers)
    assert [w.node_id for w in eligible] == ["good"]


# ------------------------------------------------------------ work-stealing


def test_work_stealing_gives_the_fast_node_more_tiles_and_covers_each_once():
    tiles = split_tiles(W, H, 4, 4)
    assign, makespan = steal_schedule(tiles, [Worker("fast", speed=4.0), Worker("slow", speed=0.5)])
    # every tile assigned exactly once
    all_idx = sorted(i for lst in assign.values() for i in lst)
    assert all_idx == list(range(len(tiles)))
    # the fast node pulled more than the straggler
    assert len(assign["fast"]) > len(assign["slow"])
    assert makespan > 0


def test_a_straggler_does_not_block_the_others():
    """One very slow node must hold at most a small share; the rest drain the
    queue. Compare makespan to a hypothetical world where the straggler got an
    equal split."""
    tiles = split_tiles(W, H, 4, 4)
    workers = [Worker("desk", speed=8.0), Worker("phone", speed=0.1)]
    assign, makespan = steal_schedule(tiles, workers)
    # equal-split makespan: phone renders half the tiles at 0.1 -> huge
    half_area = sum(
        (t[2] - t[0]) * (t[3] - t[1]) for t in tiles[len(tiles) // 2:]
    )
    equal_split_makespan = half_area / 0.1
    assert makespan < equal_split_makespan
    assert len(assign["phone"]) < len(assign["desk"])


def test_the_shared_queue_is_thread_safe():
    """Real threads draining one queue must still render each tile exactly once."""
    job = RenderJob(recipe=RECIPE, full_w=W, full_h=H, quality=QUALITY)
    full = render_full(RECIPE, W, H, quality=QUALITY)
    tiles = split_tiles(W, H, 4, 2)
    frame, results = WorkStealingScheduler(job).render(
        tiles, [Worker("a"), Worker("b"), Worker("c")], concurrent=True
    )
    assert len(results) == len(tiles)
    assert _bytes(frame) == _bytes(full)


# ------------------------------------------------------------- compositing


def test_composite_refuses_a_gap():
    tiles = split_tiles(W, H, 2, 2)
    surfs = [render_tile(RECIPE, W, H, t, quality=QUALITY) for t in tiles[:-1]]  # drop one
    with pytest.raises(ValueError, match="not fully covered"):
        composite(surfs, W, H)


def test_composite_refuses_an_overlap():
    a = render_tile(RECIPE, W, H, (0, 0, W, H), quality=QUALITY)
    b = render_tile(RECIPE, W, H, (0, 0, 10, 10), quality=QUALITY)
    with pytest.raises(ValueError, match="rendered twice"):
        composite([a, b], W, H)


# --------------------------------------------------------------- adaptive


def test_cheap_scene_stays_local_and_heavy_scene_distributes():
    workers = [Worker("a"), Worker("b"), Worker("c")]
    cheap = plan_render(
        RenderJob(RECIPE, 48, 32, quality=32), workers, local_rate=200000, mesh_overhead_seconds=0.4
    )
    heavy = plan_render(
        RenderJob(GYROID, 2048, 2048, quality=128), workers, local_rate=200000, mesh_overhead_seconds=0.4
    )
    assert cheap.distribute is False
    assert heavy.distribute is True
    assert heavy.distributed_seconds < heavy.local_seconds


def test_a_single_node_never_distributes():
    plan = plan_render(
        RenderJob(GYROID, 4096, 4096, quality=128), [Worker("only")], local_rate=100000, mesh_overhead_seconds=0.1
    )
    assert plan.distribute is False
    assert "one eligible node" in plan.reason


def test_estimate_scales_with_pixels_and_scene_weight():
    small = estimate_cost(RECIPE, 100, 100, quality=64)
    big = estimate_cost(RECIPE, 200, 200, quality=64)
    assert big == pytest.approx(small * 4)
    # the gyroid is weighted heavier than the boolean sculpture
    assert estimate_cost(GYROID, 100, 100) > estimate_cost(RECIPE, 100, 100)


# ------------------------------------------------- real output, not mock


def test_output_is_a_real_png_of_a_real_scene():
    """The composited frame is a genuine render: a valid PNG with both dark
    background and lit surface — not a flat fill or a fabricated placeholder."""
    full = render_full(RECIPE, W, H, quality=QUALITY)
    png = to_png(full)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert b"IEND" in png
    lo, hi = min(full.data), max(full.data)
    assert lo < 30 and hi > 180, "image has no tonal range — would be a flat/mock fill"
    distinct = len(set(bytes(full.data[i:i + 3]) for i in range(0, len(full.data), 3)))
    assert distinct > 50, "too few distinct colours to be a real render"


def test_capability_weighted_tiling_produces_surplus_tiles_to_steal():
    tiles = capability_weighted_tiles(W, H, [Worker("a"), Worker("b")], per_worker=4)
    # more tiles than nodes, so a work-stealing pool always has surplus.
    assert len(tiles) > 2
    # they still cover the frame exactly (composite would accept them).
    from services.forge_render.engine import render_tile as rt
    surfs = [rt(RECIPE, W, H, t, quality=20) for t in tiles]
    composite(surfs, W, H)  # raises if not an exact cover


def test_engine_version_is_pinned_and_visible():
    assert ENGINE_VERSION == "forge-cpu-1"
    assert RenderJob(RECIPE, W, H).engine_version == ENGINE_VERSION
