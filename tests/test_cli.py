from pathlib import Path
from types import SimpleNamespace

from synthesus_knowledge_cloud.__main__ import main
from synthesus_knowledge_cloud.manifest import DEFAULT_SOURCE_ROOTS, build_manifest, write_manifest
from synthesus_knowledge_cloud.provenance import capture_provenance, stamp_manifest
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


def test_manifest_validate_rejects_production_manifest_without_source_manifest(tmp_path):
    data = tmp_path / "artifacts"
    data.mkdir()
    (data / "sample.txt").write_text("hello", encoding="utf-8")
    manifest = build_manifest(data, ["."], kind="synthesus-knowledge-artifacts")
    write_manifest(manifest, data / "manifest.json")

    assert main(["validate", "--root", str(data)]) == 1


def test_manifest_validate_accepts_stamped_source_manifest_provenance(tmp_path):
    repo = tmp_path
    sources = repo / "sources"
    artifacts = repo / "artifacts"
    manifests = repo / "manifests"
    sources.mkdir()
    artifacts.mkdir()
    manifests.mkdir()
    (sources / "sample.yaml").write_text("id: sample\n", encoding="utf-8")
    (artifacts / "sample.txt").write_text("hello", encoding="utf-8")
    source_manifest = build_manifest(repo, ["sources"], kind="synthesus-knowledge-source-plane")
    write_manifest(source_manifest, manifests / "source_manifest.json")
    manifest = build_manifest(artifacts, ["."], kind="synthesus-knowledge-artifacts")
    provenance = capture_provenance(repo, artifact_root=artifacts, profile="public-base")
    write_manifest(stamp_manifest(manifest, provenance), artifacts / "manifest.json")

    assert main(["validate", "--root", str(artifacts)]) == 0


def test_source_manifest_default_roots_cover_validator_and_docs_without_pycache(tmp_path):
    root = tmp_path
    (root / "sources").mkdir()
    (root / "synthesus_knowledge_cloud" / "__pycache__").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "sources" / "sample.yaml").write_text("id: sample\n", encoding="utf-8")
    (root / "synthesus_knowledge_cloud" / "source_planes.py").write_text("x = 1\n", encoding="utf-8")
    (root / "synthesus_knowledge_cloud" / "__pycache__" / "source_planes.cpython-312.pyc").write_bytes(b"cache")
    (root / "docs" / "SOURCES.md").write_text("# Sources\n", encoding="utf-8")

    manifest = build_manifest(root, DEFAULT_SOURCE_ROOTS, kind="synthesus-knowledge-source-plane")
    paths = {item["path"] for item in manifest["artifacts"]}

    assert "synthesus_knowledge_cloud/source_planes.py" in paths
    assert "docs/SOURCES.md" in paths
    assert "synthesus_knowledge_cloud/__pycache__/source_planes.cpython-312.pyc" not in paths


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
                "    rebuild_command: synthesus-kc build profiles/public-base.yaml",
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
                "    rebuild_command: synthesus-kc build profiles/public-base.yaml",
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


def test_source_planes_rejects_duplicate_pending_dataset_ids(tmp_path):
    root = tmp_path
    sources = root / "sources"
    sources.mkdir()
    (sources / "datasets.yaml").write_text('version: "1"\nname: datasets\n', encoding="utf-8")
    manifest = "\n".join(
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
            "  - id: duplicate_dataset",
            "    repo: owner/dataset",
            "    rebuild_command: synthesus-kc build profiles/public-base.yaml",
            "    license:",
            '      spdx: "MIT"',
            "      notes: Redistributable test fixture.",
            "loader: pipelines/ingest/huggingface_loader.py::load_dataset",
            "",
        ]
    )
    (sources / "a.yaml").write_text(manifest, encoding="utf-8")
    (sources / "b.yaml").write_text(manifest.replace("planned_source", "other_source"), encoding="utf-8")

    result = validate_source_planes(root)

    assert not result.ok
    assert (
        "duplicate pending source id: duplicate_dataset in sources/b.yaml[0] "
        "already declared in sources/a.yaml[0]"
    ) in result.errors


def test_source_planes_rejects_duplicate_source_manifest_ids(tmp_path):
    root = tmp_path
    sources = root / "sources"
    sources.mkdir()
    (sources / "datasets.yaml").write_text('version: "1"\nname: datasets\n', encoding="utf-8")
    manifest = "\n".join(
        [
            'version: "1"',
            "id: duplicate_source",
            "name: Source A",
            "source_type: github_tsv",
            "license:",
            '  spdx: "MIT"',
            "  notes: Redistributable test fixture.",
            "repository: https://example.com/repo",
            "loader: pipelines/ingest/example.py::load",
            "",
        ]
    )
    (sources / "a.yaml").write_text(manifest, encoding="utf-8")
    (sources / "b.yaml").write_text(manifest.replace("Source A", "Source B"), encoding="utf-8")

    result = validate_source_planes(root)

    assert not result.ok
    assert (
        "duplicate source manifest id: duplicate_source in sources/b.yaml "
        "already declared in sources/a.yaml"
    ) in result.errors


def test_source_planes_rejects_pending_id_that_collides_with_source_id(tmp_path):
    root = tmp_path
    sources = root / "sources"
    sources.mkdir()
    (sources / "datasets.yaml").write_text('version: "1"\nname: datasets\n', encoding="utf-8")
    (sources / "admitted.yaml").write_text(
        "\n".join(
            [
                'version: "1"',
                "id: shared_source",
                "name: Admitted Source",
                "source_type: github_tsv",
                "license:",
                '  spdx: "MIT"',
                "  notes: Redistributable admitted test fixture.",
                "repository: https://example.com/repo",
                "loader: pipelines/ingest/example.py::load",
                "",
            ]
        ),
        encoding="utf-8",
    )
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
                "  - id: shared_source",
                "    repo: owner/dataset",
                "    rebuild_command: synthesus-kc build profiles/public-base.yaml",
                "    license:",
                '      spdx: "MIT"',
                "      notes: Redistributable pending test fixture.",
                "loader: pipelines/ingest/huggingface_loader.py::load_dataset",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = validate_source_planes(root)

    assert not result.ok
    assert (
        "source identity collides with pending source id: shared_source in "
        "sources/admitted.yaml already declared as pending in sources/planned.yaml[0]"
    ) in result.errors


def test_source_planes_rejects_unbacked_aggregate_public_source_id(tmp_path):
    root = tmp_path
    sources = root / "sources"
    sources.mkdir()
    (sources / "datasets.yaml").write_text(
        "\n".join(
            [
                'version: "1"',
                "name: datasets",
                "public_sources:",
                "  - id: missing_public_source",
                "    type: github_tsv",
                "    default_enabled: true",
                "    loader: pipelines/ingest/example.py::load",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = validate_source_planes(root)

    assert not result.ok
    assert (
        "aggregate public source id has no source manifest: "
        "missing_public_source in sources/datasets.yaml[0]"
    ) in result.errors


def test_source_planes_rejects_duplicate_aggregate_public_source_ids(tmp_path):
    root = tmp_path
    sources = root / "sources"
    sources.mkdir()
    (sources / "datasets.yaml").write_text(
        "\n".join(
            [
                'version: "1"',
                "name: datasets",
                "public_sources:",
                "  - id: duplicate_public_source",
                "    type: github_tsv",
                "  - id: duplicate_public_source",
                "    type: public_gzip_csv",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = validate_source_planes(root)

    assert not result.ok
    assert (
        "duplicate aggregate public source id: duplicate_public_source in "
        "sources/datasets.yaml[1] already declared in sources/datasets.yaml[0]"
    ) in result.errors


def test_source_planes_rejects_aggregate_public_source_loader_drift(tmp_path):
    root = tmp_path
    sources = root / "sources"
    sources.mkdir()
    (sources / "datasets.yaml").write_text(
        "\n".join(
            [
                'version: "1"',
                "name: datasets",
                "public_sources:",
                "  - id: backed_public_source",
                "    type: github_tsv",
                "    default_enabled: true",
                "    loader: pipelines/ingest/old_loader.py::load",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (sources / "backed.yaml").write_text(
        "\n".join(
            [
                'version: "1"',
                "id: backed_public_source",
                "name: Backed Public Source",
                "source_type: github_tsv",
                "license:",
                '  spdx: "MIT"',
                "  notes: Redistributable test fixture.",
                "repository: https://example.com/repo",
                "loader: pipelines/ingest/current_loader.py::load",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = validate_source_planes(root)

    assert not result.ok
    assert (
        "aggregate public source loader mismatch for backed_public_source in "
        "sources/datasets.yaml[0]: pipelines/ingest/old_loader.py::load != "
        "pipelines/ingest/current_loader.py::load"
    ) in result.errors


def test_source_planes_rejects_aggregate_public_source_type_drift(tmp_path):
    root = tmp_path
    sources = root / "sources"
    sources.mkdir()
    (sources / "datasets.yaml").write_text(
        "\n".join(
            [
                'version: "1"',
                "name: datasets",
                "public_sources:",
                "  - id: backed_public_source",
                "    type: github_tsv",
                "    default_enabled: true",
                "    loader: pipelines/ingest/current_loader.py::load",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (sources / "backed.yaml").write_text(
        "\n".join(
            [
                'version: "1"',
                "id: backed_public_source",
                "name: Backed Public Source",
                "source_type: public_gzip_csv",
                "license:",
                '  spdx: "MIT"',
                "  notes: Redistributable test fixture.",
                "repository: https://example.com/repo",
                "loader: pipelines/ingest/current_loader.py::load",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = validate_source_planes(root)

    assert not result.ok
    assert (
        "aggregate public source type mismatch for backed_public_source in "
        "sources/datasets.yaml[0]: github_tsv != public_gzip_csv"
    ) in result.errors


def test_source_planes_rejects_aggregate_public_source_default_enabled_drift(tmp_path):
    root = tmp_path
    sources = root / "sources"
    sources.mkdir()
    (sources / "datasets.yaml").write_text(
        "\n".join(
            [
                'version: "1"',
                "name: datasets",
                "public_sources:",
                "  - id: backed_public_source",
                "    type: github_tsv",
                "    default_enabled: false",
                "    loader: pipelines/ingest/current_loader.py::load",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (sources / "backed.yaml").write_text(
        "\n".join(
            [
                'version: "1"',
                "id: backed_public_source",
                "name: Backed Public Source",
                "source_type: github_tsv",
                "license:",
                '  spdx: "MIT"',
                "  notes: Redistributable test fixture.",
                "repository: https://example.com/repo",
                "loader: pipelines/ingest/current_loader.py::load",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = validate_source_planes(root)

    assert not result.ok
    assert (
        "aggregate public source default_enabled mismatch for backed_public_source in "
        "sources/datasets.yaml[0]: False != True"
    ) in result.errors


def test_source_planes_rejects_aggregate_public_source_license_drift(tmp_path):
    root = tmp_path
    sources = root / "sources"
    sources.mkdir()
    (sources / "datasets.yaml").write_text(
        "\n".join(
            [
                'version: "1"',
                "name: datasets",
                "public_sources:",
                "  - id: backed_public_source",
                "    type: github_tsv",
                "    default_enabled: true",
                "    loader: pipelines/ingest/current_loader.py::load",
                "    license:",
                '      spdx: "Apache-2.0"',
                "      notes: Stale catalog license.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (sources / "backed.yaml").write_text(
        "\n".join(
            [
                'version: "1"',
                "id: backed_public_source",
                "name: Backed Public Source",
                "source_type: github_tsv",
                "license:",
                '  spdx: "MIT"',
                "  notes: Redistributable test fixture.",
                "repository: https://example.com/repo",
                "loader: pipelines/ingest/current_loader.py::load",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = validate_source_planes(root)

    assert not result.ok
    assert (
        "aggregate public source license.spdx mismatch for backed_public_source in "
        "sources/datasets.yaml[0]: Apache-2.0 != MIT"
    ) in result.errors
    assert (
        "aggregate public source license.notes mismatch for backed_public_source in "
        "sources/datasets.yaml[0]: Stale catalog license. != Redistributable test fixture."
    ) in result.errors


def test_source_planes_rejects_aggregate_public_source_upstream_drift(tmp_path):
    root = tmp_path
    sources = root / "sources"
    sources.mkdir()
    (sources / "datasets.yaml").write_text(
        "\n".join(
            [
                'version: "1"',
                "name: datasets",
                "public_sources:",
                "  - id: backed_public_source",
                "    type: github_tsv",
                "    default_enabled: true",
                "    loader: pipelines/ingest/current_loader.py::load",
                "    upstream:",
                "      repository: https://example.com/old-repo",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (sources / "backed.yaml").write_text(
        "\n".join(
            [
                'version: "1"',
                "id: backed_public_source",
                "name: Backed Public Source",
                "source_type: github_tsv",
                "license:",
                '  spdx: "MIT"',
                "  notes: Redistributable test fixture.",
                "repository: https://example.com/current-repo",
                "loader: pipelines/ingest/current_loader.py::load",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = validate_source_planes(root)

    assert not result.ok
    assert (
        "aggregate public source upstream locator mismatch for backed_public_source "
        "in sources/datasets.yaml[0].upstream.repository: "
        "https://example.com/old-repo not declared in source manifest"
    ) in result.errors


def test_source_planes_rejects_pending_dataset_without_rebuild_command(tmp_path):
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
                '      spdx: "MIT"',
                "      notes: Redistributable test fixture.",
                "loader: pipelines/ingest/huggingface_loader.py::load_dataset",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = validate_source_planes(root)

    assert not result.ok
    assert "pending source entry missing rebuild_command: sources/planned.yaml[0]" in result.errors


def test_source_planes_rejects_pending_dataset_without_upstream_locator(tmp_path):
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
                "    rebuild_command: synthesus-kc build profiles/public-base.yaml",
                "    license:",
                '      spdx: "MIT"',
                "      notes: Redistributable test fixture.",
                "loader: pipelines/ingest/huggingface_loader.py::load_dataset",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = validate_source_planes(root)

    assert not result.ok
    assert "pending source entry missing upstream locator: sources/planned.yaml[0]" in result.errors
