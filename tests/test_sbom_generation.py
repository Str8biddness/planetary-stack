"""Tests for the SBOM generator (scripts/generate_sbom.py).

These verify that the generator actually runs against the live installed
environment and produces a well-formed CycloneDX-style SBOM plus a
human-readable notice bundle. Output is written into a pytest tmp dir so the
committed artifacts under docs/sbom/ are never touched by the test.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATOR_PATH = REPO_ROOT / "scripts" / "generate_sbom.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location("generate_sbom", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    module = _load_generator()
    out_dir = tmp_path_factory.mktemp("sbom")
    summary = module.generate(out_dir, timestamp="2026-01-01T00:00:00+00:00")
    return module, out_dir, summary


def test_generator_produces_files(generated):
    _module, out_dir, summary = generated
    sbom_path = out_dir / "python-sbom.json"
    notices_path = out_dir / "THIRD_PARTY_NOTICES.md"
    assert sbom_path.is_file()
    assert notices_path.is_file()
    assert summary["component_count"] > 0


def test_sbom_is_valid_json_with_expected_fields(generated):
    _module, out_dir, _summary = generated
    data = json.loads((out_dir / "python-sbom.json").read_text(encoding="utf-8"))
    # Top-level CycloneDX fields.
    assert data["bomFormat"] == "CycloneDX"
    assert isinstance(data["specVersion"], str) and data["specVersion"]
    assert isinstance(data["version"], int)
    assert isinstance(data["metadata"], dict)
    assert isinstance(data["components"], list)
    assert data["components"], "SBOM must enumerate at least one component"


def test_component_count_matches(generated):
    _module, out_dir, summary = generated
    data = json.loads((out_dir / "python-sbom.json").read_text(encoding="utf-8"))
    assert len(data["components"]) == summary["component_count"]


def test_every_component_is_well_formed(generated):
    _module, out_dir, _summary = generated
    data = json.loads((out_dir / "python-sbom.json").read_text(encoding="utf-8"))
    for comp in data["components"]:
        assert comp["type"] == "library"
        assert comp["name"]
        assert comp["version"]
        assert comp["purl"].startswith("pkg:pypi/")
        assert isinstance(comp["licenses"], list) and comp["licenses"]


def test_known_dependencies_present(generated):
    _module, out_dir, _summary = generated
    data = json.loads((out_dir / "python-sbom.json").read_text(encoding="utf-8"))
    names = {comp["name"].lower() for comp in data["components"]}
    # These are declared project dependencies and must be installed.
    assert "pydantic" in names
    assert "cryptography" in names


def test_notices_bundle_lists_deps_and_marks_unknowns(generated):
    module, out_dir, summary = generated
    text = (out_dir / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "Third-Party Notices" in text
    assert "pydantic" in text
    assert "cryptography" in text
    # The unknown count reported in the summary must be reflected honestly.
    if summary["unknown_count"] > 0:
        assert module.UNKNOWN_LICENSE in text


def test_unknown_licenses_are_never_guessed(generated):
    module, out_dir, _summary = generated
    data = json.loads((out_dir / "python-sbom.json").read_text(encoding="utf-8"))
    # Any component whose license could not be detected must carry the exact
    # sentinel, never a fabricated identifier.
    for comp in data["components"]:
        entry = comp["licenses"][0]
        name = entry.get("license", {}).get("name") if "license" in entry else None
        if name == module.UNKNOWN_LICENSE:
            # Its recorded source must indicate detection failure.
            source = {p["name"]: p["value"] for p in comp["properties"]}[
                "planetary:license_source"
            ]
            assert source in {"none", "License (unparsable full text)"}
