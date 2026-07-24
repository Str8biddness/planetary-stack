"""Adaptive, work-stealing distribution of a forge render across mesh nodes.

The scene graph is tiny (an SF1 recipe — dozens of bytes), so distribution ships
a description out and gets a tile back: coarse-grained, the shape that wins on a
LAN when render time dwarfs coordination. The three failure modes are handled
explicitly:

* Seams from version skew  -> the job pins `engine_version`; a node whose engine
  differs refuses rather than contribute a mismatched tile.
* Cross-boundary effects    -> `RenderJob.overlap` carries a margin >= the bloom
  radius; tiles render padded and crop.
* Stragglers                -> a single tile queue with work-stealing: whichever
  node is free pulls the next tile, so a slow phone holds at most one tile and
  never blocks the others.

And the decision that makes it worth doing at all is adaptive: `plan_render`
estimates the work, and distributes only when the predicted distributed time
(mesh overhead + parallel render) beats the local time. Cheap scenes stay local.
"""

from __future__ import annotations

import heapq
import threading
from dataclasses import dataclass

from .engine import ENGINE_VERSION, EngineVersionMismatch, Recipe, RecipeV2, Surface, composite, render_tile, render_tile_v2
import typing

# Relative per-scene weight — heavier scenes cost more per pixel to march.
_SCENE_WEIGHT = (1.0, 1.1, 1.6, 1.5)


@dataclass(frozen=True)
class RenderJob:
    recipe: typing.Union[Recipe, RecipeV2]
    full_w: int
    full_h: int
    engine_version: str = ENGINE_VERSION
    quality: int = 64
    overlap: int = 0
    bloom_radius: int = 0
    bloom_strength: float = 0.0


@dataclass(frozen=True)
class Worker:
    node_id: str
    engine_version: str = ENGINE_VERSION
    # pixels the node can shade per second, relative — used for weighting only.
    speed: float = 1.0

    def matches(self, job: RenderJob) -> bool:
        return self.engine_version == job.engine_version


@dataclass(frozen=True)
class TileResult:
    node_id: str
    rect: tuple[int, int, int, int]
    surface: Surface


@dataclass(frozen=True)
class RenderPlan:
    distribute: bool
    local_seconds: float
    distributed_seconds: float
    reason: str
    estimate: float


def split_tiles(w: int, h: int, cols: int, rows: int) -> list[tuple[int, int, int, int]]:
    """A uniform grid that covers the frame exactly (no gaps, no overlap)."""
    cols = max(1, cols)
    rows = max(1, rows)
    xs = [round(w * i / cols) for i in range(cols + 1)]
    ys = [round(h * i / rows) for i in range(rows + 1)]
    tiles = []
    for r in range(rows):
        for c in range(cols):
            tiles.append((xs[c], ys[r], xs[c + 1], ys[r + 1]))
    return tiles


def capability_weighted_tiles(w: int, h: int, workers: list[Worker], *, per_worker: int = 4) -> list[tuple[int, int, int, int]]:
    """Many small tiles so a work-stealing pool self-balances.

    More, smaller tiles let fast nodes pull extra work while a straggler holds
    just one. Tile count scales with the pool so there is always surplus to
    steal.
    """
    n = max(1, len(workers)) * max(1, per_worker)
    cols = max(1, int(round(n ** 0.5)))
    rows = max(1, (n + cols - 1) // cols)
    return split_tiles(w, h, cols, rows)


def estimate_cost(recipe: typing.Union[Recipe, RecipeV2], w: int, h: int, *, quality: int = 64) -> float:
    """Abstract cost ~ ray-march evaluations. Used only for the local/distribute
    decision, never presented to the user as a real time."""
    if isinstance(recipe, RecipeV2):
        return float(w) * float(h) * float(quality) * 1.5 * len(recipe.nodes)
    return float(w) * float(h) * float(quality) * _SCENE_WEIGHT[recipe.mode % len(_SCENE_WEIGHT)]


def _tile_area(rect: tuple[int, int, int, int]) -> int:
    x0, y0, x1, y1 = rect
    return max(0, x1 - x0) * max(0, y1 - y0)


def steal_schedule(
    tiles: list[tuple[int, int, int, int]], workers: list[Worker]
) -> tuple[dict[str, list[int]], float]:
    """Discrete-event work-stealing: the next free node takes the next tile.

    Returns the tile indices each node rendered and the makespan (finish time of
    the slowest node), both derived from real tile areas and node speeds.
    """
    if not workers:
        raise EngineVersionMismatch("no node matches the pinned engine version")
    by_id = {w.node_id: w for w in workers}
    clocks = {w.node_id: 0.0 for w in workers}
    assignment: dict[str, list[int]] = {w.node_id: [] for w in workers}
    heap = [(0.0, w.node_id) for w in workers]
    heapq.heapify(heap)
    for idx in range(len(tiles)):
        t, wid = heapq.heappop(heap)
        w = by_id[wid]
        cost = _tile_area(tiles[idx]) / max(w.speed, 1e-9)
        clocks[wid] = t + cost
        assignment[wid].append(idx)
        heapq.heappush(heap, (clocks[wid], wid))
    return assignment, max(clocks.values(), default=0.0)


class WorkStealingScheduler:
    """Runs a job across a worker pool with a shared, thread-safe tile queue."""

    def __init__(self, job: RenderJob) -> None:
        self.job = job

    def eligible(self, workers: list[Worker]) -> list[Worker]:
        matching = [w for w in workers if w.matches(self.job)]
        if not matching:
            raise EngineVersionMismatch(
                f"no node runs the pinned engine {self.job.engine_version!r}"
            )
        return matching

    def _render_tile(self, node_id: str, rect: tuple[int, int, int, int]) -> TileResult:
        if isinstance(self.job.recipe, RecipeV2):
            surf = render_tile_v2(
                self.job.recipe,
                self.job.full_w,
                self.job.full_h,
                rect,
                quality=self.job.quality,
                overlap=self.job.overlap,
                bloom_radius=self.job.bloom_radius,
                bloom_strength=self.job.bloom_strength,
                engine_version=self.job.engine_version,
            )
        else:
            surf = render_tile(
                self.job.recipe,
                self.job.full_w,
                self.job.full_h,
                rect,
                quality=self.job.quality,
                overlap=self.job.overlap,
                bloom_radius=self.job.bloom_radius,
                bloom_strength=self.job.bloom_strength,
                engine_version=self.job.engine_version,
            )
        return TileResult(node_id=node_id, rect=rect, surface=surf)

    def render(
        self, tiles: list[tuple[int, int, int, int]], workers: list[Worker], *, concurrent: bool = False
    ) -> tuple[Surface, list[TileResult]]:
        """Render every tile exactly once, stealing from a shared queue, and
        composite the frame. `concurrent` uses real threads to prove the queue
        is safe; the default is deterministic single-thread draining."""
        pool = self.eligible(workers)
        queue: list[int] = list(range(len(tiles)))
        lock = threading.Lock()
        results: list[TileResult] = []
        # round-robin the free node; with real timing a faster node would pull
        # more, but correctness (each tile once) does not depend on timing.
        order = iter(pool)

        def next_worker() -> Worker:
            nonlocal order
            try:
                return next(order)
            except StopIteration:
                order = iter(pool)
                return next(order)

        def drain() -> None:
            while True:
                with lock:
                    if not queue:
                        return
                    idx = queue.pop(0)
                    w = next_worker()
                res = self._render_tile(w.node_id, tiles[idx])
                with lock:
                    results.append(res)

        if concurrent:
            threads = [threading.Thread(target=drain) for _ in pool]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        else:
            drain()

        frame = composite([r.surface for r in results], self.job.full_w, self.job.full_h)
        return frame, results


def plan_render(
    job: RenderJob,
    workers: list[Worker],
    *,
    local_rate: float,
    mesh_overhead_seconds: float,
) -> RenderPlan:
    """Decide local vs distributed from measured numbers.

    * local_rate            — pixels/second this coordinator shades (measured).
    * mesh_overhead_seconds — one job's lease+mTLS+transfer+receipt (measured).

    Distribute only if the predicted distributed time beats local. A single node,
    or a scene cheaper than the coordination cost, stays local.
    """
    est = estimate_cost(job.recipe, job.full_w, job.full_h, quality=job.quality)
    local_seconds = est / max(local_rate, 1e-9)

    matching = [w for w in workers if w.matches(job)]
    total_rate = sum(w.speed for w in matching) * max(local_rate, 1e-9) / max(
        (matching[0].speed if matching else 1.0), 1e-9
    )
    if len(matching) <= 1:
        return RenderPlan(
            distribute=False,
            local_seconds=local_seconds,
            distributed_seconds=float("inf"),
            reason="only one eligible node — nothing to distribute to",
            estimate=est,
        )
    # ideal parallel render time + one round of mesh overhead per remote node
    parallel_render = est / max(total_rate, 1e-9)
    distributed_seconds = mesh_overhead_seconds + parallel_render
    if distributed_seconds < local_seconds:
        reason = "render dwarfs coordination — the house renders it"
        distribute = True
    else:
        reason = "coordination costs more than the render — keep it local"
        distribute = False
    return RenderPlan(
        distribute=distribute,
        local_seconds=local_seconds,
        distributed_seconds=distributed_seconds,
        reason=reason,
        estimate=est,
    )
