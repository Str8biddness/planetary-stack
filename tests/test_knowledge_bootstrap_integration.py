from pathlib import Path

import core.knowledge_cloud as knowledge_cloud_module
import core.rag_pipeline as rag_pipeline_module


def test_knowledge_cloud_bootstraps_from_repo_data_root(tmp_path: Path, monkeypatch):
    calls: list[Path] = []

    def fake_bootstrap(local_root, **kwargs):
        calls.append(Path(local_root))
        return {"downloaded": ["faiss.index"]}

    monkeypatch.setattr(knowledge_cloud_module, "bootstrap_knowledge_cache", fake_bootstrap)

    cloud = knowledge_cloud_module.KnowledgeCloud(data_dir=tmp_path / "data" / "knowledge_cloud")

    assert calls == [tmp_path / "data"]
    assert cloud.data_dir == tmp_path / "data" / "knowledge_cloud"


def test_rag_pipeline_bootstraps_from_repo_data_root(tmp_path: Path, monkeypatch):
    calls: list[Path] = []

    def fake_bootstrap(local_root, **kwargs):
        calls.append(Path(local_root))
        return {"downloaded": ["faiss.index"]}

    monkeypatch.setattr(rag_pipeline_module, "bootstrap_knowledge_cache", fake_bootstrap)

    pipe = rag_pipeline_module.RAGPipeline(
        index_path=str(tmp_path / "data" / "faiss.index"),
        metadata_path=str(tmp_path / "data" / "faiss_metadata.json"),
    )

    assert calls == [tmp_path / "data"]
    assert pipe.index_path == tmp_path / "data" / "faiss.index"
