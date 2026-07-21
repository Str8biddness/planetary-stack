"""Static wiring for the Image Forge (CSG + SDF raymarched generation).

Same contract as test_ui_wiring: every handler the markup names must be
defined, every element the script reads must exist, and — because this product
forbids mock data — the forge must degrade to the word "unknown" and render
nothing when WebGL2 is absent, never a fabricated frame. It must also stay
offline: no CDN, no external origin in the vendored module.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
HTML = (HERE / "index.html").read_text(encoding="utf-8")
SCRIPT = (HERE / "script.js").read_text(encoding="utf-8")
STYLES = (HERE / "styles.css").read_text(encoding="utf-8")
FORGE = (HERE / "assets" / "sdf_forge.js").read_text(encoding="utf-8")

FORGE_HANDLERS = ("openForge", "forgeApply", "forgeRender", "forgeExport", "forgeToggleAnim")
FORGE_IDS = (
    "forge-canvas",
    "forge-unavailable",
    "forge-status",
    "forge-status-detail",
    "forge-animate-btn",
    "forge-download",
    "forge-mode",
    "forge-iters",
    "forge-blend",
    "forge-hue",
)


def _defined_functions() -> set[str]:
    return set(re.findall(r"\bfunction\s+([A-Za-z_$][\w$]*)", SCRIPT))


@pytest.mark.parametrize("handler", FORGE_HANDLERS)
def test_forge_handlers_are_defined(handler):
    assert handler in HTML, f"{handler} is not referenced from the markup"
    assert handler in _defined_functions(), f"{handler} is referenced but never defined"


def test_forge_window_exists_and_has_a_dock_entry():
    assert 'id="win-forge"' in HTML
    assert 'data-win="win-forge"' in HTML


@pytest.mark.parametrize("element_id", FORGE_IDS)
def test_every_forge_element_the_script_reads_exists(element_id):
    tail = SCRIPT[SCRIPT.index("image forge"):]
    reads = set(re.findall(r"getElementById\('([^']+)'\)", tail))
    if element_id in reads:
        assert f'id="{element_id}"' in HTML, f"script reads #{element_id} but markup has no such id"
    else:
        # Still assert the markup carries it, since the controls wire to it.
        assert f'id="{element_id}"' in HTML


def test_module_is_vendored_with_a_cache_bust():
    assert (HERE / "assets" / "sdf_forge.js").exists()
    assert "assets/sdf_forge.js?v=" in HTML
    # script.js and styles.css cache-busts were bumped for this change.
    assert "script.js?v=20260721k" in HTML
    assert "styles.css?v=20260721k" in HTML


def test_module_is_offline_no_external_origin():
    """The product's core claim is that it runs with no network. A CDN or an
    external origin in the boot path would break it offline."""
    for banned in ("http://", "https://", "//cdn", "googleapis", "unpkg", "jsdelivr"):
        assert banned not in FORGE, f"forge module reaches an external origin: {banned}"


def test_forge_carries_the_csg_algebra():
    """The generator is constructive solid geometry, not a bitmap: the union,
    intersection and difference operators must be present in both the CPU math
    and the shader."""
    for op in ("opUnion", "opIntersect", "opSubtract"):
        assert op in FORGE, f"CSG operator {op} missing from the forge math"
    assert "float opU(" in FORGE and "float opI(" in FORGE and "float opS(" in FORGE


def test_forge_reports_unknown_and_renders_nothing_without_webgl():
    """NO MOCK DATA: an unrenderable forge shows 'unknown', not a fake frame."""
    assert "forge-unavailable" in HTML
    assert ">unknown<" in HTML  # the static status detail defaults to unknown
    # The renderer's fps is null (unknown) until measured — never a made-up number.
    assert "this.fps = null" in FORGE
    # No fabricated fallback image path.
    assert "toDataURL" in FORGE
    assert "return null" in FORGE  # toPNG/degrade returns null when unavailable


def test_forge_styles_use_design_tokens_not_arbitrary_values():
    forge_css = STYLES[STYLES.index(".forge-body"):STYLES.index(".forge-body") + 2000]
    assert "var(--" in forge_css
    # The stage keeps the brand accent on the range controls.
    assert "var(--purple)" in STYLES[STYLES.index(".forge-field"):STYLES.index(".forge-field") + 800]
