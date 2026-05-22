from pathlib import Path

from synthesus_knowledge_cloud.__main__ import main
from synthesus_knowledge_cloud.manifest import build_manifest, write_manifest
from synthesus_knowledge_cloud.profiles import load_profile, summarize_profile
from synthesus_knowledge_cloud.source_planes import validate_source_planes


def test_manifest_build_and_validate(tmp_path):
    root = tmp_path
    data = root / "artifacts"
    data.mkdir()
    (data / "sample.txt").write_text("hello", encoding="utf-8")
    manifest = build_manifest(data, ["."], kind="test")
    write_manifest(manifest, data / "manifest.json")
    assert main(["validate", "--root", str(data)]) == 0


def test_profiles_load():
    profile = load_profile(Path("profiles/public-base.yaml"))
    summary = summarize_profile(profile)
    assert "profile=public-base" in summary
    assert "max_entries=250000" in summary


def test_source_planes_current_repo():
    result = validate_source_planes(".")
    assert result.ok, result.errors
    assert result.character_pattern_banks >= 1
