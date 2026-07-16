import json
from pathlib import Path

import pytest

from pipelines.build.reindex_bundle import rebuild_index, record_to_text
from synthesus_knowledge_cloud.json_stream import count_json_array, iter_json_array


def test_iter_json_array_crosses_small_chunks(tmp_path: Path) -> None:
    values = [{"pattern": "alpha"}, {"response": "beta"}, {"value": [1, 2, 3]}]
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(values), encoding="utf-8")

    assert list(iter_json_array(path, chunk_size=7)) == values
    assert count_json_array(path) == 3


def test_iter_json_array_rejects_non_array(tmp_path: Path) -> None:
    path = tmp_path / "metadata.json"
    path.write_text('{"pattern": "alpha"}', encoding="utf-8")

    with pytest.raises(ValueError, match="top-level JSON array"):
        list(iter_json_array(path))


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        ({"pattern": "question", "response": "answer"}, "question"),
        ({"question": "question", "answer": "answer"}, "question"),
        ({"response": "answer"}, "answer"),
        ({}, " "),
        ("plain", "plain"),
    ],
)
def test_record_to_text_prefers_query_side(record, expected: str) -> None:
    assert record_to_text(record) == expected


def test_rebuild_index_rejects_unknown_index_kind(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="index_kind"):
        rebuild_index(
            tmp_path / "metadata.json",
            tmp_path / "embedder.pkl",
            tmp_path / "faiss.index",
            index_kind="unknown",
        )
