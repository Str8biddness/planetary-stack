"""Static consistency between the desktop HTML and its script.

This is NOT a substitute for rendering the page in a browser — it cannot tell
you whether anything looks right. What it does catch is the failure mode that
static markup plus hand-written DOM lookups actually produce: an `onclick` that
names a function nobody defined, or a `getElementById` for an element that was
never added.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
HTML = (HERE / "index.html").read_text(encoding="utf-8")
SCRIPT = (HERE / "script.js").read_text(encoding="utf-8")
STYLES = (HERE / "styles.css").read_text(encoding="utf-8")

# Handlers referenced from markup we added or rely on for the new windows.
NEW_HANDLERS = (
    "openDevices",
    "openSettings",
    "openDashboard",
    "devicesAdd",
    "devicesDiscover",
    "settingsSaveEvidence",
)

NEW_WINDOW_IDS = ("win-devices", "win-settings", "win-dashboard")


def _defined_functions() -> set[str]:
    return set(re.findall(r"\bfunction\s+([A-Za-z_$][\w$]*)", SCRIPT))


@pytest.mark.parametrize("handler", NEW_HANDLERS)
def test_markup_handlers_are_defined(handler):
    assert handler in HTML, f"{handler} is not referenced from the markup"
    assert handler in _defined_functions(), f"{handler} is referenced but never defined"


@pytest.mark.parametrize("window_id", NEW_WINDOW_IDS)
def test_new_windows_exist_and_have_a_dock_entry(window_id):
    assert f'id="{window_id}"' in HTML
    assert f'data-win="{window_id}"' in HTML, f"{window_id} has no dock button"


def test_every_element_the_new_script_reads_exists_in_the_markup():
    """getElementById targets in the new UI code must exist in index.html."""
    tail = SCRIPT[SCRIPT.index("Devices & Permissions, Settings, Dashboard.") :]
    ids = set(re.findall(r"getElementById\('([^']+)'\)", tail))
    # Ids created dynamically by devicesRenderRow are not in the static markup.
    ids = {value for value in ids if not value.startswith("cap-")}
    missing = sorted(value for value in ids if f'id="{value}"' not in HTML)
    assert not missing, f"script reads elements that do not exist: {missing}"


def test_result_viewer_has_a_provenance_badge_host():
    assert 'id="jobs-result-evidence"' in HTML
    assert "psEvidenceBadge" in SCRIPT
    assert "X-Synthesus-Evidence-Status" in SCRIPT


def test_demo_panels_are_visibly_marked():
    """Any mock-up panel must carry the DEMO treatment.

    Shipping a panel that looks live but is not is the visual form of
    overclaiming, so the marker is asserted rather than trusted.
    """
    assert ".demo-chrome::after" in STYLES
    assert 'content: "DEMO"' in STYLES
    assert "ps-demo-note" in HTML
    # The mock cards are inside the dashboard and each one is tagged.
    dashboard = HTML[HTML.index('id="win-dashboard"') : HTML.index('<nav class="dock"')]
    assert dashboard.count("demo-chrome") >= 8, "mock cards are not all marked DEMO"


def test_live_dashboard_reports_unknown_rather_than_guessing():
    """A value that cannot be read must never render as a real number."""
    assert "'unknown'" in SCRIPT
    assert "Controller unreachable" in SCRIPT


def test_discovered_section_exists_above_the_manual_add_form():
    """Candidates are offered first; typing an id stays available underneath."""
    devices = HTML[HTML.index('id="win-devices"') : HTML.index('id="win-settings"')]
    assert 'id="dev-discovered"' in devices
    assert devices.index("Discovered on your mesh") < devices.index("Add a device")


def test_discovery_ui_says_a_source_can_never_be_discovered():
    """Cameras and TVs hold no certificate, so they are never enrolled.

    If the UI implied otherwise, an owner would wait for a camera to appear in
    a list it can never appear in.
    """
    devices = HTML[HTML.index('id="win-devices"') : HTML.index('id="win-settings"')]
    assert "never enrolled" in devices
    assert "source" in devices


def test_adding_a_discovered_node_says_it_grants_nothing():
    """The consent claim is made in the UI copy, not just in the store."""
    block = SCRIPT[SCRIPT.index("function devicesRenderCandidate") :]
    block = block[: block.index("\nasync function devicesAddDiscovered")]
    assert "grants it nothing" in block
    # Expiry and revocation are rendered, not silently dropped.
    assert "node.expired" in block and "node.revoked" in block
    assert "node.available" in block


def test_discovered_add_posts_the_peer_role_to_the_existing_endpoint():
    add = SCRIPT[SCRIPT.index("async function devicesAddDiscovered") :]
    add = add[: add.index("\n/* ----------------------------------------------------------- settings */")]
    assert "'/api/devices'" in add
    assert "role: 'peer'" in add


def test_permissions_ui_refreshes_from_the_controller_after_a_toggle():
    """The switch must show what was stored, not what was clicked."""
    toggle = SCRIPT[SCRIPT.index("async function devicesToggle") :]
    toggle = toggle[: toggle.index("\nasync function devicesRemove")]
    assert "devicesRefresh()" in toggle


# ---------------------------------------------------------------------------
# Installable phone app (PWA)
#
# There are no browser tools in the environment these tests were written in, so
# NOTHING below proves the app installs, renders, or lays out on a phone. What
# these do catch is the set of failures that make a PWA silently not install:
# a manifest that is not valid JSON, an icon path that points at a file that
# was never generated, a manifest nobody linked, and a service worker that
# caches live controller data.
# ---------------------------------------------------------------------------

import json

MANIFEST_PATH = HERE / "manifest.webmanifest"
SW_PATH = HERE / "sw.js"


def test_manifest_exists_and_is_valid_json():
    assert MANIFEST_PATH.exists(), "manifest.webmanifest is missing"
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["display"] == "standalone"
    assert manifest["name"] and manifest["short_name"]
    assert manifest["start_url"]
    # Chrome refuses to offer installation without a 192px and a 512px icon.
    sizes = {icon["sizes"] for icon in manifest["icons"]}
    assert "192x192" in sizes and "512x512" in sizes


def test_every_manifest_icon_exists_on_disk():
    """A manifest that names a file nobody generated fails install silently."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    missing = [
        icon["src"] for icon in manifest["icons"] if not (HERE / icon["src"]).is_file()
    ]
    assert not missing, f"manifest references icons that do not exist: {missing}"


def test_manifest_colors_come_from_the_stylesheet_palette():
    """The splash must not be a colour that appears nowhere in the product."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for key in ("background_color", "theme_color"):
        assert manifest[key] in STYLES, f"{key} {manifest[key]} is not a palette colour"


def test_index_links_the_manifest_and_declares_a_theme_colour():
    assert 'rel="manifest"' in HTML
    assert 'href="manifest.webmanifest"' in HTML
    assert 'name="theme-color"' in HTML


def test_index_apple_touch_icon_exists_on_disk():
    match = re.search(r'rel="apple-touch-icon"\s+href="([^"]+)"', HTML)
    assert match, "no apple-touch-icon declared"
    assert (HERE / match.group(1)).is_file()


def test_the_page_registers_the_service_worker():
    assert "serviceWorker" in SCRIPT
    assert "register('sw.js')" in SCRIPT
    assert SW_PATH.exists(), "sw.js is registered but does not exist"


def test_service_worker_never_caches_api_responses():
    """Stale API data would render as fabricated state, so it is never cached.

    The rule is asserted three ways: the guard list names /api/, the guard is
    actually consulted in the fetch handler, and no cache write is reachable
    without passing it.
    """
    sw = SW_PATH.read_text(encoding="utf-8")
    assert "'/api/'" in sw, "the never-cache list does not name /api/"
    assert "isNeverCached" in sw
    fetch_handler = sw[sw.index("addEventListener('fetch'") :]
    # The bail-out must come before anything that opens or reads the cache.
    bail = fetch_handler.index("isNeverCached")
    for cache_call in ("caches.match", "caches.open"):
        assert bail < fetch_handler.index(cache_call), (
            f"{cache_call} is reachable before the /api/ guard"
        )
    # Precaching must not list an API path either.
    shell = sw[sw.index("const SHELL") : sw.index("const NEVER_CACHE")]
    assert "/api/" not in shell


def test_service_worker_versions_its_cache_and_drops_old_ones():
    sw = SW_PATH.read_text(encoding="utf-8")
    assert "CACHE_VERSION" in sw
    activate = sw[sw.index("addEventListener('activate'") : sw.index("addEventListener('fetch'")]
    assert "caches.delete" in activate, "old caches are never cleaned up"


def test_every_precached_shell_asset_exists_on_disk():
    sw = SW_PATH.read_text(encoding="utf-8")
    shell = sw[sw.index("const SHELL") : sw.index("const NEVER_CACHE")]
    paths = [p for p in re.findall(r"'([^']+)'", shell) if p not in ("./",)]
    missing = [p for p in paths if not (HERE / p).is_file()]
    assert not missing, f"the service worker precaches files that do not exist: {missing}"


# Absolute URLs that were already in the tree before the PWA work. They are
# recorded here rather than waved through: the point of the test below is that
# this list must never grow. Each entry is a (literal, expected count) pair.
#   http://' + window.location.host  — same-origin, built from the current page
#   http://localhost:1234            — the operator's local LM Studio default
#   https://rclone.org/install.sh    — printed as a copy-paste instruction
PRE_EXISTING_ABSOLUTE_URLS = {
    "index.html": {"http://localhost:1234": 1},
    "script.js": {
        "http://' + window.location.host": 9,
        "http://localhost:1234": 2,
        "https://rclone.org/install.sh": 1,
    },
    "sw.js": {},
}


@pytest.mark.parametrize("filename", sorted(PRE_EXISTING_ABSOLUTE_URLS))
def test_no_new_external_urls_are_introduced(filename):
    """The product must work with no network and no external dependency.

    A CDN link or a remote asset would make an offline phone install render
    broken, so every absolute URL has to be an already-known one.
    """
    text = (HERE / filename).read_text(encoding="utf-8")
    allowed = PRE_EXISTING_ABSOLUTE_URLS[filename]
    seen: dict[str, int] = {}
    for match in re.finditer(r"https?://", text):
        tail = text[match.start() :]
        literal = next((a for a in allowed if tail.startswith(a)), None)
        assert literal is not None, (
            f"{filename} introduces a new absolute URL: {tail[:60]!r}"
        )
        seen[literal] = seen.get(literal, 0) + 1
    assert seen == {k: v for k, v in allowed.items() if v}, (
        f"{filename}: absolute-URL counts changed — expected {allowed}, saw {seen}"
    )


def test_phone_layout_makes_windows_full_screen_instead_of_floating():
    """Windows carry inline pixel geometry, so the override must be !important.

    Without it the sheet rule loses to the inline style and the window stays
    720px wide on a 360px screen.
    """
    block = STYLES[STYLES.index("@media (max-width: 820px)") :]
    block = block[: block.index("@media (max-width: 380px)")]
    assert "position: fixed !important" in block
    assert "width: 100vw !important" in block
    assert "overflow-x: hidden" in block, "page can still scroll sideways"
    # Touch targets: the 14px window-chrome dots must be grown.
    assert "width: 44px !important" in block and "height: 44px !important" in block
    assert "min-height: 44px" in block


def test_worker_view_exists_and_has_a_dock_entry():
    assert 'id="win-worker"' in HTML
    assert 'data-win="win-worker"' in HTML
    assert "openWorker" in _defined_functions()


def test_worker_view_reads_only_endpoints_that_already_exist():
    """No new backend endpoint may be invented to feed the phone view."""
    block = SCRIPT[SCRIPT.index("async function workerRefresh") :]
    block = block[: block.index("/* ------------------------------------------------ installable app")]
    called = set(re.findall(r"psFetch\('(/api/[^']*)'", block))
    assert called <= {"/api/settings", "/api/devices", "/api/jobs/"}, (
        f"worker view calls endpoints outside the existing set: {called}"
    )


def test_worker_view_says_unknown_rather_than_inventing_a_reading():
    """Thermal has no web API at all; it must never render a number."""
    block = SCRIPT[SCRIPT.index("async function workerRefresh") :]
    block = block[: block.index("/* ------------------------------------------------ installable app")]
    assert "dashCard('Thermal', 'unknown'" in block
    assert "'unknown'" in block
    # Battery is read through the browser API, and absence is reported.
    assert "navigator.getBattery" in SCRIPT
    assert "does not expose the Battery Status API" in block
