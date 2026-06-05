from pathlib import Path
from types import SimpleNamespace

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


def test_manifest_validate_rejects_faiss_embedder_dim_mismatch(tmp_path, monkeypatch):
    data = tmp_path / "artifacts"
    (data / "models").mkdir(parents=True)
    (data / "faiss.index").write_bytes(b"fake-index")
    (data / "faiss_metadata.json").write_text("[{}, {}]", encoding="utf-8")
    (data / "models" / "swarm_embedder.pkl").write_bytes(b"fake-model")
    manifest = build_manifest(data, ["."], kind="test")
    write_manifest(manifest, data / "manifest.json")

    fake_faiss = SimpleNamespace(read_index=lambda _path: SimpleNamespace(ntotal=2, d=384))
    fake_joblib = SimpleNamespace(load=lambda _path: {"dim": 128})
    monkeypatch.setitem(__import__("sys").modules, "faiss", fake_faiss)
    monkeypatch.setitem(__import__("sys").modules, "joblib", fake_joblib)

    assert main(["validate", "--root", str(data)]) == 1


def test_manifest_validate_rejects_duplicate_artifact_paths(tmp_path):
    data = tmp_path / "artifacts"
    data.mkdir()
    sample = data / "sample.txt"
    sample.write_text("hello", encoding="utf-8")
    manifest = build_manifest(data, ["."], kind="test")
    manifest["artifacts"].append(dict(manifest["artifacts"][0]))
    write_manifest(manifest, data / "manifest.json")

    assert main(["validate", "--root", str(data)]) == 1


def test_profiles_load():
    profile = load_profile(Path("profiles/public-base.yaml"))
    summary = summarize_profile(profile)
    assert "profile=public-base" in summary
    assert "max_entries=250000" in summary


def test_source_planes_current_repo():
    result = validate_source_planes(".")
    assert result.ok, result.errors
    assert result.character_pattern_banks >= 1


def test_source_planes_rejects_source_manifest_without_license_notes(tmp_path):
    root = tmp_path
    sources = root / "sources"
    sources.mkdir()
    (sources / "datasets.yaml").write_text('version: "1"\nname: datasets\n', encoding="utf-8")
    (sources / "bad.yaml").write_text(
        "\n".join(
            [
                'version: "1"',
                "id: bad_source",
                "name: Bad Source",
                "source_type: github_tsv",
                "license:",
                '  spdx: "MIT"',
                "repository: https://example.com/repo",
                "loader: pipelines/ingest/example.py::load",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = validate_source_planes(root)

    assert not result.ok
    assert "source manifest missing license.notes: sources/bad.yaml" in result.errors


def test_source_planes_rejects_pending_dataset_without_spdx(tmp_path):
    root = tmp_path
    sources = root / "sources"
    sources.mkdir()
    (sources / "datasets.yaml").write_text('version: "1"\nname: datasets\n', encoding="utf-8")
    (sources / "planned.yaml").write_text(
        "\n".join(
            [
                'version: "1"',
                "id: planned_source",
                "name: Planned Source",
                "source_type: huggingface_datasets",
                "license:",
                '  spdx: "MIXED"',
                "  notes: Per-dataset licenses are required.",
                "default_enabled: false",
                "pending:",
                "  - id: weak_dataset",
                "    repo: weak/dataset",
                "    license:",
                "      notes: Missing SPDX should fail.",
                "loader: pipelines/ingest/huggingface_loader.py::load_dataset",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = validate_source_planes(root)

    assert not result.ok
    assert "pending source entry missing license.spdx: sources/planned.yaml[0]" in result.errors


def test_source_planes_rejects_pending_dataset_without_license_notes(tmp_path):
    root = tmp_path
    sources = root / "sources"
    sources.mkdir()
    (sources / "datasets.yaml").write_text('version: "1"\nname: datasets\n', encoding="utf-8")
    (sources / "planned.yaml").write_text(
        "\n".join(
            [
                'version: "1"',
                "id: planned_source",
                "name: Planned Source",
                "source_type: kaggle_api",
                "license:",
                '  spdx: "MIXED"',
                "  notes: Per-dataset licenses are required.",
                "default_enabled: false",
                "pending:",
                "  - id: weak_dataset",
                "    repo: weak/dataset",
                "    license:",
                '      spdx: "MIT"',
                "loader: pipelines/ingest/kaggle_loader.py::load_dataset",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = validate_source_planes(root)

    assert not result.ok
    assert "pending source entry missing license.notes: sources/planned.yaml[0]" in result.errors
