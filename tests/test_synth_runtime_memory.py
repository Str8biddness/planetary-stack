from __future__ import annotations

from types import SimpleNamespace

from core.synth_runtime import SynthRuntime


class FakeMemoryStore:
    def recall_semantic(self, character_id: str, query: str, top_k: int = 5):
        return ["Semantic fact about the query"]

    def recall_episodic(self, character_id: str, query: str, top_k: int = 5):
        return ["Past episode relevant to the query"]

    def recall_procedural(self, character_id: str, query: str, top_k: int = 5):
        return ["Procedure for handling the query"]

    def recall_working(self, character_id: str, query: str, top_k: int = 5):
        return ["Working note for the query"]

    def store_episodic(self, character_id: str, content: str, importance: float = 0.5, tags=None):
        self.last_stored = {
            "character_id": character_id,
            "content": content,
            "importance": importance,
            "tags": tags,
        }


class FakeCore:
    def __init__(self):
        self.calls = []

    def reason(self, query: str, context: str | None = None, session_id: str | None = None):
        self.calls.append({"query": query, "context": context, "session_id": session_id})
        return SimpleNamespace(final_response="final response")


def _runtime_with_fakes() -> tuple[SynthRuntime, FakeCore, FakeMemoryStore]:
    runtime = SynthRuntime.__new__(SynthRuntime)
    runtime.characters_dir = None
    runtime.data_dir = "data"
    runtime.left_model = "left"
    runtime.right_model = "right"
    runtime._cores = {}
    runtime._memory_store = FakeMemoryStore()
    fake_core = FakeCore()
    runtime._get_core = lambda character_id: fake_core
    return runtime, fake_core, runtime._memory_store


def test_build_memory_context_includes_all_layers() -> None:
    runtime, _, _ = _runtime_with_fakes()

    context = runtime._build_memory_context("npc_1", "What should I do next?")

    assert "Semantic memory" in context
    assert "Episodic memory" in context
    assert "Procedural memory" in context
    assert "Working memory" in context


def test_respond_merges_explicit_and_memory_context() -> None:
    runtime, fake_core, memory_store = _runtime_with_fakes()

    result = runtime.respond(
        character_id="npc_1",
        user_input="What should I do next?",
        context="Explicit system context",
        session_id="session-123",
    )

    assert result.final_response == "final response"
    assert fake_core.calls
    call = fake_core.calls[0]
    assert call["query"] == "What should I do next?"
    assert call["session_id"] == "session-123"
    assert "Explicit system context" in call["context"]
    assert "Semantic memory" in call["context"]
    assert "Past episode relevant to the query" in call["context"]
    assert memory_store.last_stored["character_id"] == "npc_1"
    assert "User: What should I do next?" in memory_store.last_stored["content"]
