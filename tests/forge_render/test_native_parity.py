"""The compiled core must be indistinguishable from the Python reference.

Distributed tiles composite without seams only if every node produces identical
pixels. A node with the .so built and a node without must therefore agree
exactly — otherwise a mixed mesh renders visible tile boundaries. That is the
property under test here, and it is worth more than the speed.
"""

from __future__ import annotations

import hashlib

import pytest

from services.forge_render import Recipe, render_region
from services.forge_render.engine import _render_region_python, native_available

SIZE = 64
QUALITY = 32


def _digest(surface) -> str:
    return hashlib.sha256(bytes(surface.data)).hexdigest()


@pytest.mark.skipif(not native_available(), reason="native core not built")
@pytest.mark.parametrize("mode", [0, 1, 2, 3])
def test_native_matches_python_byte_for_byte(mode):
    rc = Recipe(mode=mode)
    native = render_region(rc, SIZE, SIZE, 0, 0, SIZE, SIZE, quality=QUALITY)
    reference = _render_region_python(rc, SIZE, SIZE, 0, 0, SIZE, SIZE, quality=QUALITY)
    assert _digest(native) == _digest(reference), (
        f"mode {mode}: native and Python disagree — a mixed mesh would seam"
    )


@pytest.mark.skipif(not native_available(), reason="native core not built")
def test_native_tiles_match_python_full_frame():
    """A tile rendered natively must fit a frame rendered in Python."""
    rc = Recipe(mode=0)
    full = _render_region_python(rc, SIZE, SIZE, 0, 0, SIZE, SIZE, quality=QUALITY)
    half = render_region(rc, SIZE, SIZE, 0, 0, SIZE // 2, SIZE, quality=QUALITY)
    for y in range(SIZE):
        for x in range(SIZE // 2):
            assert half.px(x, y) == full.px(x, y), f"pixel ({x},{y}) differs"


@pytest.mark.skipif(not native_available(), reason="native core not built")
def test_palette_variants_match():
    """Colour is computed in both paths; HSL conversion must agree too."""
    for palette in range(4):
        for hue in (0, 285, 359):
            rc = Recipe(mode=0, palette=palette, hue=hue)
            a = render_region(rc, 32, 32, 0, 0, 32, 32, quality=16)
            b = _render_region_python(rc, 32, 32, 0, 0, 32, 32, quality=16)
            assert _digest(a) == _digest(b), f"palette={palette} hue={hue} differ"


def test_python_path_still_works_without_native():
    """A checkout with no compiler must still render, just slowly."""
    surface = _render_region_python(Recipe(mode=0), 24, 24, 0, 0, 24, 24, quality=12)
    assert len(surface.data) == 24 * 24 * 3
    assert any(surface.data), "reference renderer produced an empty frame"
