from __future__ import annotations

from pathlib import Path

from tools import validate_knowledge_cold_start


def test_default_root_finds_sibling_knowledge_cloud(
    monkeypatch,
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "synthesus" / "runtime"
    runtime_root.mkdir(parents=True)
    companion_artifacts = tmp_path / "synthesus-knowledge-cloud" / "artifacts"
    companion_artifacts.mkdir(parents=True)

    monkeypatch.delenv("SYNTHESUS_KNOWLEDGE_ROOT", raising=False)
    monkeypatch.setattr(validate_knowledge_cold_start, "ROOT", runtime_root)

    assert validate_knowledge_cold_start._default_root() == companion_artifacts


def test_default_root_honors_environment_override(
    monkeypatch,
    tmp_path: Path,
) -> None:
    configured_root = tmp_path / "knowledge"
    monkeypatch.setenv("SYNTHESUS_KNOWLEDGE_ROOT", str(configured_root))

    assert validate_knowledge_cold_start._default_root() == configured_root
