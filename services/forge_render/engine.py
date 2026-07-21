"""Canonical portable CPU renderer for the Synthesus forge.

Why a CPU engine when the desktop already has WebGL: distributed rendering only
works if *every* node produces byte-identical pixels for the same job. A phone
worker inside proot has no reliable headless WebGL, and mixing a GPU coordinator
with CPU workers is precisely the "version skew" that puts seams through the
image. So the distributed path uses ONE pinned engine — this one — on the
coordinator's own tiles as well as the workers'. The WebGL path stays for
interactive local preview.

Two honesty-critical properties:

* Every pixel is computed from the FULL image coordinates (`full_w`, `full_h`)
  and its absolute pixel position, never from the tile's own size. The camera,
  vignette and grain are therefore identical whether a pixel is rendered alone,
  in a tile, or as part of the whole frame. That is what makes tiling seamless
  for the raymarch and its per-pixel effects — proven by a byte-equality test.

* The one genuinely screen-space effect, bloom, reads neighbours. A tile that
  does not carry an overlap margin wide enough for the blur radius will differ
  at its inner boundaries — the classic distributed-rendering seam. `render_tile`
  renders a padded region and crops it, and the test proves overlap>=radius
  reproduces the whole-frame result while overlap=0 does not.

The engine version is pinned into every job; a node whose engine version differs
must refuse the job rather than contribute a mismatched tile.
"""

from __future__ import annotations

import math
import struct
import zlib
from dataclasses import dataclass

ENGINE_VERSION = "forge-cpu-1"

SCENES = ("Boolean sculpture", "Infinite carved field", "Menger sponge", "Gyroid lattice")
_HUE_MIN, _HUE_MAX = 260, 320


class EngineVersionMismatch(RuntimeError):
    """A render job pinned a different engine version than this node runs."""


@dataclass(frozen=True)
class Recipe:
    """The whole scene description — a few dozen bytes, the thing we ship."""

    mode: int = 0
    iters: int = 6
    blend: int = 35
    hue: int = 285
    glow: int = 60
    palette: int = 0
    cam: int = 42

    @classmethod
    def from_code(cls, code: str) -> "Recipe":
        parts = str(code).strip().split(".")
        if parts[0] != "SF1" or len(parts) < 8:
            raise ValueError("not an SF1 recipe code")
        n = [int(x) for x in parts[1:8]]
        return cls(
            mode=_clamp_int(n[0], 0, len(SCENES) - 1),
            iters=_clamp_int(n[1], 1, 10),
            blend=_clamp_int(n[2], 0, 100),
            hue=_clamp_int(n[3], _HUE_MIN, _HUE_MAX),
            glow=_clamp_int(n[4], 0, 100),
            palette=_clamp_int(n[5], 0, 3),
            cam=_clamp_int(n[6], 30, 52),
        )

    def to_code(self) -> str:
        return ".".join(
            str(v)
            for v in ("SF1", self.mode, self.iters, self.blend, self.hue, self.glow, self.palette, self.cam)
        )


def _clamp_int(v: int, lo: int, hi: int) -> int:
    return lo if v < lo else hi if v > hi else v


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


# --------------------------------------------------------- colour (purple-only)
def _hsl_to_rgb(h: float, s: float, l: float) -> tuple[float, float, float]:
    h = ((h % 360) + 360) % 360 / 360.0

    def f(n: float) -> float:
        k = (n + h * 12) % 12
        a = s * min(l, 1 - l)
        return l - a * max(-1.0, min(k - 3, min(9 - k, 1.0)))

    return f(0), f(8), f(4)


def _palette(hue: int, palette: int) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    profiles = [
        (0.62, 0.50, 0.50, 0.86),
        (0.78, 0.50, 0.60, 0.88),
        (0.72, 0.38, 0.62, 0.80),
        (0.50, 0.62, 0.35, 0.94),
    ]
    sa, la, sb, lb = profiles[palette % len(profiles)]
    return _hsl_to_rgb(hue, sa, la), _hsl_to_rgb(hue + 12, sb, lb)


# ------------------------------------------------------------------- SDF scene
def _sd_sphere(p, r):
    x, y, z = p
    return math.sqrt(x * x + y * y + z * z) - r


def _sd_box(p, b):
    # Hot path: called ~300k times per 128x128 frame. `max`/`min` builtins were
    # 20% of total runtime purely in call overhead, so they are inlined as
    # conditionals here — identical results for floats, no numerical change.
    qx = abs(p[0]) - b[0]
    qy = abs(p[1]) - b[1]
    qz = abs(p[2]) - b[2]
    ox = qx if qx > 0.0 else 0.0
    oy = qy if qy > 0.0 else 0.0
    oz = qz if qz > 0.0 else 0.0
    outside = math.sqrt(ox * ox + oy * oy + oz * oz)
    m = qy if qy > qz else qz
    if qx > m:
        m = qx
    inside = m if m < 0.0 else 0.0
    return outside + inside


def _op_smooth_union(a, b, k):
    h = 0.5 + 0.5 * (b - a) / k
    if h < 0.0:
        h = 0.0
    elif h > 1.0:
        h = 1.0
    return b * (1 - h) + a * h - k * h * (1.0 - h)


def _scene(p, rc: Recipe) -> float:
    mode = rc.mode
    if mode == 1:
        q = (((p[0] + 2.0) % 4.0) - 2.0, ((p[1] + 2.0) % 4.0) - 2.0, ((p[2] + 2.0) % 4.0) - 2.0)
        box = _sd_box(q, (1.0, 1.0, 1.0))
        return max(-_sd_sphere(q, 1.2), box)
    if mode == 2:
        d = _sd_box(p, (1.0, 1.0, 1.0))
        s = 1.0
        for m in range(min(rc.iters, 10)):
            ax = ((p[0] * s) % 2.0) - 1.0
            ay = ((p[1] * s) % 2.0) - 1.0
            az = ((p[2] * s) % 2.0) - 1.0
            s *= 3.0
            rx, ry, rz = abs(1.0 - 3.0 * abs(ax)), abs(1.0 - 3.0 * abs(ay)), abs(1.0 - 3.0 * abs(az))
            da, db, dc = max(rx, ry), max(ry, rz), max(rz, rx)
            c = (min(da, min(db, dc)) - 1.0) / s
            d = max(d, c)
        return d
    if mode == 3:
        sc = 2.0 + rc.iters * 0.6
        g = abs(
            math.sin(p[0] * sc) * math.cos(p[1] * sc)
            + math.sin(p[1] * sc) * math.cos(p[2] * sc)
            + math.sin(p[2] * sc) * math.cos(p[0] * sc)
        ) / sc - 0.03
        g *= 0.5
        return max(g, _sd_sphere(p, 1.7))
    box = _sd_box(p, (1.15, 1.15, 1.15))
    sph = _sd_sphere(p, 1.5)
    solid = max(box, sph)
    solid = max(-_sd_sphere(p, 0.72), solid)
    orbit = _sd_sphere((p[0] - 0.0, p[1], p[2] - 1.9), 0.55)  # t=0 pose
    return _op_smooth_union(orbit, solid, max(rc.blend / 100.0, 0.001))


def _normal(p, rc: Recipe):
    e = 0.0012
    dx = _scene((p[0] + e, p[1], p[2]), rc) - _scene((p[0] - e, p[1], p[2]), rc)
    dy = _scene((p[0], p[1] + e, p[2]), rc) - _scene((p[0], p[1] - e, p[2]), rc)
    dz = _scene((p[0], p[1], p[2] + e), rc) - _scene((p[0], p[1], p[2] - e), rc)
    ln = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
    return dx / ln, dy / ln, dz / ln


def _soft_shadow(ro, rd, rc: Recipe) -> float:
    res = 1.0
    t = 0.03
    for _ in range(20):
        p = (ro[0] + rd[0] * t, ro[1] + rd[1] * t, ro[2] + rd[2] * t)
        h = _scene(p, rc)
        if h < 0.001:
            return 0.0
        res = min(res, 9.0 * h / t)
        t += _clamp(h, 0.02, 0.3)
        if t > 7.0:
            break
    return _clamp(res, 0.0, 1.0)


def _shade(px: int, py: int, full_w: int, full_h: int, rc: Recipe, cols, *, quality: int):
    """One pixel, computed only from absolute coordinates and full dimensions."""
    col_a, col_b = cols
    # uv from FULL image — this is what makes a tile agree with the whole frame.
    u = (px * 2.0 + 1.0 - full_w) / full_h
    v = (full_h - (py * 2.0 + 1.0)) / full_h  # flip y so it matches GL
    dist = rc.cam * 0.1
    ro = (0.0, 1.4, dist)  # fixed t=0 pose for deterministic distribution
    # camera basis looking at origin
    flen = math.sqrt(ro[0] ** 2 + ro[1] ** 2 + ro[2] ** 2)
    fw = (-ro[0] / flen, -ro[1] / flen, -ro[2] / flen)
    rtx = fw[2] * 1.0 - fw[1] * 0.0
    rty = fw[0] * 0.0 - fw[2] * 0.0
    rtz = fw[1] * 0.0 - fw[0] * 1.0
    rl = math.sqrt(rtx * rtx + rty * rty + rtz * rtz) or 1.0
    rt = (rtx / rl, rty / rl, rtz / rl)
    up = (fw[1] * rt[2] - fw[2] * rt[1], fw[2] * rt[0] - fw[0] * rt[2], fw[0] * rt[1] - fw[1] * rt[0])
    rdx = u * rt[0] + v * up[0] + 1.6 * fw[0]
    rdy = u * rt[1] + v * up[1] + 1.6 * fw[1]
    rdz = u * rt[2] + v * up[2] + 1.6 * fw[2]
    rl = math.sqrt(rdx * rdx + rdy * rdy + rdz * rdz) or 1.0
    rd = (rdx / rl, rdy / rl, rdz / rl)

    t = 0.0
    hit = False
    for _ in range(quality):
        p = (ro[0] + rd[0] * t, ro[1] + rd[1] * t, ro[2] + rd[2] * t)
        d = _scene(p, rc)
        if d < 0.001:
            hit = True
            break
        t += d
        if t > 40.0:
            break

    glow = rc.glow / 100.0
    gy = _clamp(v * 0.5 + 0.5, 0.0, 1.0)
    sky = (
        0.015 * (1 - gy) + col_a[0] * 0.10 * gy,
        0.012 * (1 - gy) + col_a[1] * 0.10 * gy,
        0.020 * (1 - gy) + col_a[2] * 0.10 * gy,
    )
    halo = glow * 0.06 * math.exp(-2.5 * math.sqrt(u * u + v * v))
    r, g, b = sky[0] + col_b[0] * halo, sky[1] + col_b[1] * halo, sky[2] + col_b[2] * halo

    if hit:
        p = (ro[0] + rd[0] * t, ro[1] + rd[1] * t, ro[2] + rd[2] * t)
        n = _normal(p, rc)
        ld = (0.5698, 0.8288, 0.3625)  # normalised (0.55,0.8,0.35)
        dif = _clamp(n[0] * ld[0] + n[1] * ld[1] + n[2] * ld[2], 0.0, 1.0)
        sh = _soft_shadow((p[0] + n[0] * 0.01, p[1] + n[1] * 0.01, p[2] + n[2] * 0.01), ld, rc)
        ndv = _clamp(-(n[0] * rd[0] + n[1] * rd[1] + n[2] * rd[2]), 0.0, 1.0)
        fres = (1.0 - ndv) ** 3
        mixf = 0.35 + 0.5 * dif
        base = (
            col_a[0] * (1 - mixf) + col_b[0] * mixf,
            col_a[1] * (1 - mixf) + col_b[1] * mixf,
            col_a[2] * (1 - mixf) + col_b[2] * mixf,
        )
        lit = 0.14 + 0.9 * dif * sh
        r = base[0] * lit + col_b[0] * fres * (0.6 + glow)
        g = base[1] * lit + col_b[1] * fres * (0.6 + glow)
        b = base[2] * lit + col_b[2] * fres * (0.6 + glow)
        haze = _clamp(t / 40.0, 0.0, 1.0)
        r = r * (1 - haze) + sky[0] * haze
        g = g * (1 - haze) + sky[1] * haze
        b = b * (1 - haze) + sky[2] * haze

    # vignette (uses full-image uv) + deterministic grain (absolute pixel coord)
    vig = 1.0 - 0.30 * (u * u + v * v) * 0.25
    r, g, b = r * vig, g * vig, b * vig
    grain = (_hash21(px, py) - 0.5) * 0.035
    r, g, b = r + grain, g + grain, b + grain
    # gamma
    return (_to_byte(r), _to_byte(g), _to_byte(b))


def _hash21(x: int, y: int) -> float:
    # deterministic per absolute pixel — identical in a tile or the whole frame
    v = (x * 374761393 + y * 668265263) & 0xFFFFFFFF
    v = (v ^ (v >> 13)) * 1274126177 & 0xFFFFFFFF
    return ((v ^ (v >> 16)) & 0xFFFFFFFF) / 4294967296.0


def _to_byte(c: float) -> int:
    c = c if c > 0.0 else 0.0
    c = c ** 0.4545
    return int(_clamp(c, 0.0, 1.0) * 255.0 + 0.5)


# ------------------------------------------------------------------- surfaces
class Surface:
    """A tight RGB pixel buffer covering an absolute region of the full frame."""

    __slots__ = ("x0", "y0", "w", "h", "data")

    def __init__(self, x0: int, y0: int, w: int, h: int, data: bytearray | None = None) -> None:
        self.x0, self.y0, self.w, self.h = x0, y0, w, h
        self.data = data if data is not None else bytearray(w * h * 3)

    def px(self, ax: int, ay: int) -> tuple[int, int, int]:
        i = ((ay - self.y0) * self.w + (ax - self.x0)) * 3
        return self.data[i], self.data[i + 1], self.data[i + 2]

    def set(self, ax: int, ay: int, rgb: tuple[int, int, int]) -> None:
        i = ((ay - self.y0) * self.w + (ax - self.x0)) * 3
        self.data[i], self.data[i + 1], self.data[i + 2] = rgb


def render_region(rc: Recipe, full_w: int, full_h: int, x0: int, y0: int, x1: int, y1: int, *, quality: int = 64) -> Surface:
    """Render absolute rect [x0,x1)×[y0,y1) using full-frame coordinates."""
    x0 = max(0, x0)
    y0 = max(0, y0)
    x1 = min(full_w, x1)
    y1 = min(full_h, y1)
    cols = _palette(rc.hue, rc.palette)
    surf = Surface(x0, y0, x1 - x0, y1 - y0)
    for ay in range(y0, y1):
        for ax in range(x0, x1):
            surf.set(ax, ay, _shade(ax, ay, full_w, full_h, rc, cols, quality=quality))
    return surf


def _box_blur_bright(surf: Surface, radius: int, strength: float) -> Surface:
    """Screen-space bloom: blur the bright parts and add them back.

    Samples clamp to the SURFACE bounds. On the whole frame the surface is the
    image, so this clamps to the image edge. On a padded tile the surface is the
    padded region, so an interior output pixel needs its neighbours within
    `radius` to be present — i.e. overlap>=radius — or the clamp uses the wrong
    edge and the boundary differs. That difference is the seam.
    """
    if radius <= 0 or strength <= 0:
        return surf
    w, h = surf.w, surf.h
    out = Surface(surf.x0, surf.y0, w, h, bytearray(surf.data))
    n = (2 * radius + 1) ** 2
    for ly in range(h):
        for lx in range(w):
            sr = sg = sb = 0
            for dy in range(-radius, radius + 1):
                yy = min(max(ly + dy, 0), h - 1)
                for dx in range(-radius, radius + 1):
                    xx = min(max(lx + dx, 0), w - 1)
                    i = (yy * w + xx) * 3
                    sr += surf.data[i]
                    sg += surf.data[i + 1]
                    sb += surf.data[i + 2]
            i = (ly * w + lx) * 3
            out.data[i] = min(255, surf.data[i] + int((sr / n) * strength))
            out.data[i + 1] = min(255, surf.data[i + 1] + int((sg / n) * strength))
            out.data[i + 2] = min(255, surf.data[i + 2] + int((sb / n) * strength))
    return out


def render_full(rc: Recipe, w: int, h: int, *, quality: int = 64, bloom_radius: int = 0, bloom_strength: float = 0.0) -> Surface:
    surf = render_region(rc, w, h, 0, 0, w, h, quality=quality)
    if bloom_radius > 0:
        surf = _box_blur_bright(surf, bloom_radius, bloom_strength)
    return surf


def render_tile(
    rc: Recipe,
    full_w: int,
    full_h: int,
    rect: tuple[int, int, int, int],
    *,
    quality: int = 64,
    overlap: int = 0,
    bloom_radius: int = 0,
    bloom_strength: float = 0.0,
    engine_version: str = ENGINE_VERSION,
) -> Surface:
    """Render one tile. Refuses if the pinned engine version is not ours.

    Renders the tile padded by `overlap`, applies bloom on the padded surface,
    then crops back to `rect`. With overlap>=bloom_radius the crop is identical
    to the whole-frame result.
    """
    if engine_version != ENGINE_VERSION:
        raise EngineVersionMismatch(
            f"job pinned engine {engine_version!r}; this node runs {ENGINE_VERSION!r}"
        )
    x0, y0, x1, y1 = rect
    pad = overlap
    padded = render_region(rc, full_w, full_h, x0 - pad, y0 - pad, x1 + pad, y1 + pad, quality=quality)
    if bloom_radius > 0:
        padded = _box_blur_bright(padded, bloom_radius, bloom_strength)
    cx0 = max(0, x0)
    cy0 = max(0, y0)
    cx1 = min(full_w, x1)
    cy1 = min(full_h, y1)
    out = Surface(cx0, cy0, cx1 - cx0, cy1 - cy0)
    for ay in range(cy0, cy1):
        for ax in range(cx0, cx1):
            out.set(ax, ay, padded.px(ax, ay))
    return out


def composite(surfaces: list[Surface], w: int, h: int) -> Surface:
    """Assemble tiles into the full frame. Refuses gaps and overlaps."""
    full = Surface(0, 0, w, h)
    covered = bytearray(w * h)
    for s in surfaces:
        for ay in range(s.y0, s.y0 + s.h):
            for ax in range(s.x0, s.x0 + s.w):
                if not (0 <= ax < w and 0 <= ay < h):
                    raise ValueError("tile lies outside the frame")
                ci = ay * w + ax
                if covered[ci]:
                    raise ValueError("tiles overlap; a pixel was rendered twice")
                covered[ci] = 1
                full.set(ax, ay, s.px(ax, ay))
    if any(c == 0 for c in covered):
        raise ValueError("frame is not fully covered by the tiles")
    return full


def to_png(surf: Surface) -> bytes:
    """Minimal, dependency-free RGB8 PNG encoder (stdlib zlib only)."""
    w, h = surf.w, surf.h
    raw = bytearray()
    for y in range(h):
        raw.append(0)  # filter type 0
        start = y * w * 3
        raw.extend(surf.data[start:start + w * 3])

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b"")
