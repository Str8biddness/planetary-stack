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
