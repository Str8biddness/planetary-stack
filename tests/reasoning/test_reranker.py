from packages.reasoning.reranker import CrossEncoderReranker


def test_reranker_lexical_fallback_prioritizes_relevant_chunk():
    reranker = CrossEncoderReranker(config={"stop_words": {"the", "is", "a"}})
    reranker._load_attempted = True
    reranker._model = None

    results = reranker.rerank(
        "npc memory quota isolation",
        [
            "weather and tavern dialogue",
            "kernel enforced npc memory quota and strict isolation",
            "generic character greeting",
        ],
        top_k=2,
    )

    assert results[0]["chunk"] == "kernel enforced npc memory quota and strict isolation"
    assert results[0]["score"] > results[1]["score"]
    assert results[0]["index"] == 1
