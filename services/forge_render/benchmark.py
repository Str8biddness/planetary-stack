"""The small measurement that decides whether distributing pays.

Three numbers on real hardware:

    1. local render   — time to render a representative scene here.
    2. single tile    — time to render one tile of it.
    3. mesh round-trip — time to move a recipe-sized object through the real
                         Unisync transport once (lease-bound framing, auth,
                         chunking, receipt).

From them, the crossover: the local render time above which distributing to N
nodes is predicted to win. Below it, coordination costs more than the work and
the scene should render locally.

Honesty: the round-trip here uses the in-process transport, so it captures
framing/auth/verify but NOT the mTLS handshake or the wire. It is a lower bound
on real mesh overhead; a physical LAN number will be larger.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from services.unisync import (
    ContentAddressedStore,
    InProcessObjectTransport,
    TransferContext,
)
from services.unisync.contracts import AuthorizationError

from .engine import Recipe, render_full, render_region
from .farm import split_tiles


class _AllowValidator:
    def validate_transfer(self, context, peer_identity=None):
        return None


@dataclass(frozen=True)
class Measurement:
    local_seconds: float
    tile_seconds: float
    roundtrip_seconds: float
    node_count: int
    crossover_local_seconds: float

    def summary(self) -> str:
        return (
            f"local={self.local_seconds*1000:.1f}ms "
            f"tile={self.tile_seconds*1000:.1f}ms "
            f"roundtrip={self.roundtrip_seconds*1000:.2f}ms "
            f"crossover>={self.crossover_local_seconds*1000:.1f}ms "
            f"(nodes={self.node_count})"
        )


def time_local_render(recipe: Recipe, w: int, h: int, *, quality: int = 64) -> float:
    start = time.perf_counter()
    render_full(recipe, w, h, quality=quality)
    return time.perf_counter() - start


def time_single_tile(recipe: Recipe, w: int, h: int, *, quality: int = 64, cols: int = 4, rows: int = 4) -> float:
    rect = split_tiles(w, h, cols, rows)[0]
    start = time.perf_counter()
    render_region(recipe, w, h, rect[0], rect[1], rect[2], rect[3], quality=quality)
    return time.perf_counter() - start


def time_mesh_roundtrip(*, payload_bytes: int = 4096, repeats: int = 20, tmp: Path | None = None) -> float:
    import tempfile

    base = Path(tmp or tempfile.mkdtemp(prefix="forge-bench-"))
    src = ContentAddressedStore(base / "src")
    payload = b"forge-recipe-payload" * (payload_bytes // 20 + 1)
    payload = payload[:payload_bytes]
    digest = src.put_bytes(payload)
    transport = InProcessObjectTransport(validator=_AllowValidator())
    best = float("inf")
    for i in range(repeats):
        dst = base / f"dst-{i}"
        ctx = TransferContext(
            account_id="account:bench",
            request_sha256="1" * 64,
            lease_id="lease:bench",
            lease_sha256="2" * 64,
            fencing_token=1,
            selected_transport="local_process",
            source_node_id="node:coordinator",
            destination_node_id="node:worker",
            object_sha256=digest,
            byte_length=len(payload),
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        start = time.perf_counter()
        transport.upload_object(context=ctx, source_root=src.root, destination_root=dst)
        best = min(best, time.perf_counter() - start)
    return best


def measure(recipe: Recipe, w: int, h: int, *, quality: int = 64, node_count: int = 3) -> Measurement:
    local = time_local_render(recipe, w, h, quality=quality)
    tile = time_single_tile(recipe, w, h, quality=quality)
    rt = time_mesh_roundtrip()
    # Distribution predicted time ~ node_count round-trips + local/node_count.
    # Solve for the local time L at which distribution just wins:
    #   overhead + L/node_count < L   =>   L > overhead * node_count / (node_count - 1)
    overhead = rt * node_count
    if node_count > 1:
        crossover = overhead * node_count / (node_count - 1)
    else:
        crossover = float("inf")
    return Measurement(
        local_seconds=local,
        tile_seconds=tile,
        roundtrip_seconds=rt,
        node_count=node_count,
        crossover_local_seconds=crossover,
    )
