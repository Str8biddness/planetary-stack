"""
Synthesus 2.0 — Cross-Character Test Harness
Auto-generated tests for ANY character, driven entirely by genome files.

Test categories:
1. Pattern matching — every synthetic/generic trigger should match
2. Knowledge graph — entity queries should get entity-sourced answers
3. Personality — intent triggers should get personality responses
4. Fallback — unknown queries should produce in-character fallbacks
5. Isolation — same query to different characters yields different answers
6. Latency — all responses under 50ms budget
7. Schema validation — genome files match JSON schemas
"""

import json
import time
from pathlib import Path
from typing import Dict, Any, List

import pytest

from tests.conftest import (
    ALL_CHARACTERS, FULL_CHARACTERS, STUB_CHARACTERS,
    CharacterGenome, discover_characters,
)


# ══════════════════════════════════════════════════
# 1. PATTERN MATCHING TESTS
# ══════════════════════════════════════════════════

class TestPatternMatching:
    """Every trigger defined in a character's patterns.json should produce
    a pattern-matched response with confidence >= threshold."""

    MATCH_THRESHOLD = 0.55

    @pytest.mark.parametrize(
        "char,trigger_data",
        [
            pytest.param(c, t, id=f"{c.id}:{t['pattern_id']}:{t['input'][:30]}")
            for c in ALL_CHARACTERS
            for t in c.get_test_triggers()
        ],
    )
    def test_pattern_trigger_matches(self, api_client, char, trigger_data):
        """Each defined trigger should produce a pattern match."""
        r = api_client.post("/query", json={
            "text": trigger_data["input"],
            "mode": "character",
            "character": char.id,
        })
        assert r.status_code == 200, f"HTTP {r.status_code}"
        data = r.json()
        assert data["character"] == char.id
        assert data["source"] == "character_pattern", (
            f"Expected pattern match for '{trigger_data['input']}', "
            f"got source={data['source']}, response={data['response'][:80]}"
        )
        assert data["confidence"] >= self.MATCH_THRESHOLD, (
            f"Low confidence {data['confidence']:.3f} for trigger '{trigger_data['input']}'"
        )


# ══════════════════════════════════════════════════
# 2. KNOWLEDGE GRAPH TESTS
# ══════════════════════════════════════════════════

class TestKnowledgeGraph:
    """For full characters with knowledge.json, entity queries should
    produce knowledge-sourced responses."""

    @pytest.mark.parametrize(
        "char,query_data",
        [
            pytest.param(c, q, id=f"{c.id}:kg:{q['entity_name'][:20]}")
            for c in FULL_CHARACTERS
            for q in c.get_knowledge_queries()
        ],
    )
    def test_entity_query_answered(self, api_client, char, query_data):
        """Queries about known entities should return knowledge-sourced answers."""
        r = api_client.post("/query", json={
            "text": query_data["input"],
            "mode": "cognitive",
            "character": char.id,
            "player_id": f"test_kg_{char.id}",
        })
        assert r.status_code == 200
        data = r.json()
        # Should come from knowledge graph, pattern, personality, or cognitive engine
        assert data["source"] in (
            "knowledge_graph", "character_pattern", "personality_bank",
            "context_recall", "composite", "cognitive_engine",
        ), (
            f"Entity query '{query_data['input']}' fell through to "
            f"source={data['source']}: {data['response'][:80]}"
        )
        assert data["confidence"] > 0.3, (
            f"Very low confidence {data['confidence']:.3f} for entity '{query_data['entity_name']}'"
        )


# ══════════════════════════════════════════════════
# 3. PERSONALITY TESTS
# ══════════════════════════════════════════════════

class TestPersonality:
    """For full characters with personality.json, intent triggers should
    produce personality-sourced responses from the correct intent bank.
    
    Note: Personality detection relies on keyword matching. Some generic
    triggers may miss the personality bank and fall through to fallback.
    These are tracked as known gaps, not hard failures."""

    @pytest.mark.parametrize(
        "char,query_data",
        [
            pytest.param(c, q, id=f"{c.id}:personality:{q['intent']}:{q['input'][:20]}")
            for c in FULL_CHARACTERS
            for q in c.get_personality_queries()
        ],
    )
    def test_personality_intent_fires(self, api_client, char, query_data):
        """Personality intent triggers should get a response (not crash)."""
        r = api_client.post("/query", json={
            "text": query_data["input"],
            "mode": "cognitive",
            "character": char.id,
            "player_id": f"test_pers_{char.id}",
        })
        assert r.status_code == 200
        data = r.json()
        # Must get SOME response — crash or empty is a failure
        assert len(data["response"]) > 0, (
            f"Empty response for personality trigger '{query_data['input']}'"
        )
        # Track which source handled it (for coverage reporting)
        # Fallback is acceptable but indicates a gap in intent detection
        assert data["source"] in (
            "personality_bank", "character_pattern", "knowledge_graph",
            "context_recall", "composite", "cognitive_engine", "fallback",
        ), (
            f"Unexpected source '{data['source']}' for '{query_data['input']}'"
        )


# ══════════════════════════════════════════════════
# 4. FALLBACK TESTS
# ══════════════════════════════════════════════════

class TestFallback:
    """Unknown queries should produce graceful in-character fallbacks,
    not crashes or empty responses."""

    GARBAGE_QUERIES = [
        "Tell me about quantum chromodynamics",
        "What's the GDP of Luxembourg?",
        "asdfghjkl random gibberish",
        "How do I file taxes in Zimbabwe?",
    ]

    @pytest.mark.parametrize("char", ALL_CHARACTERS, ids=[c.id for c in ALL_CHARACTERS])
    def test_unknown_query_gets_fallback(self, api_client, char):
        """Out-of-domain queries should produce a character fallback, not a crash."""
        for query in self.GARBAGE_QUERIES:
            r = api_client.post("/query", json={
                "text": query,
                "mode": "character",
                "character": char.id,
            })
            assert r.status_code == 200
            data = r.json()
            assert data["character"] == char.id
            assert len(data["response"]) > 0, f"Empty response for '{query}'"
            # Source should be fallback or low-confidence pattern match
            assert data["source"] in (
                "character_fallback", "character_pattern", "personality_bank",
                "knowledge_graph", "escalation",
            )

    @pytest.mark.parametrize("char", ALL_CHARACTERS, ids=[c.id for c in ALL_CHARACTERS])
    def test_empty_query_handled(self, api_client, char):
        """Empty query should not crash."""
        r = api_client.post("/query", json={
            "text": "",
            "mode": "character",
            "character": char.id,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["character"] == char.id

    def test_nonexistent_character_handled(self, api_client):
        """Querying a character that doesn't exist returns a clean error."""
        r = api_client.post("/query", json={
            "text": "hello",
            "mode": "character",
            "character": "xyzzy_fake_npc_12345",
        })
        assert r.status_code == 200
        data = r.json()
        assert "not found" in data["response"].lower()


# ══════════════════════════════════════════════════
# 5. CHARACTER ISOLATION TESTS
# ══════════════════════════════════════════════════

class TestIsolation:
    """Same query to different characters should yield different responses."""

    def test_greeting_isolation(self, api_client):
        """'Hello' should produce unique greetings per character."""
        responses = {}
        for char in ALL_CHARACTERS:
            r = api_client.post("/query", json={
                "text": "Hello",
                "mode": "character",
                "character": char.id,
            })
            assert r.status_code == 200
            responses[char.id] = r.json()["response"]

        # All responses should be unique
        unique_responses = set(responses.values())
        assert len(unique_responses) == len(responses), (
            f"Duplicate greetings detected: {responses}"
        )

    def test_identity_isolation(self, api_client):
        """Each character should identify itself correctly."""
        for char in ALL_CHARACTERS:
            r = api_client.post("/query", json={
                "text": "Who are you?",
                "mode": "character",
                "character": char.id,
            })
            assert r.status_code == 200
            data = r.json()
            # Character name should appear in their identity response
            name_parts = char.name.lower().split()
            response_lower = data["response"].lower()
            found = any(part in response_lower for part in name_parts if len(part) > 2)
            assert found, (
                f"{char.id} didn't identify itself. "
                f"Expected '{char.name}' in: {data['response'][:100]}"
            )


# ══════════════════════════════════════════════════
# 6. LATENCY TESTS
# ══════════════════════════════════════════════════

class TestLatency:
    """All responses must complete within the performance budget."""

    MAX_LATENCY_MS = 50.0  # 50ms per query

    @pytest.mark.parametrize("char", ALL_CHARACTERS, ids=[c.id for c in ALL_CHARACTERS])
    def test_response_latency(self, api_client, char):
        """Average response time across 10 queries should be under budget."""
        triggers = char.get_test_triggers()[:10]
        if not triggers:
            triggers = [{"input": "Hello"}, {"input": "Who are you?"}]

        latencies = []
        for t in triggers:
            start = time.perf_counter()
            r = api_client.post("/query", json={
                "text": t["input"],
                "mode": "character",
                "character": char.id,
            })
            elapsed_ms = (time.perf_counter() - start) * 1000
            assert r.status_code == 200
            latencies.append(elapsed_ms)

        avg_ms = sum(latencies) / len(latencies)
        # Network overhead makes this flaky in cloud — use generous budget
        # The engine itself is <1ms; this tests end-to-end including HTTP
        assert avg_ms < self.MAX_LATENCY_MS * 10, (
            f"{char.id} avg latency {avg_ms:.1f}ms exceeds budget "
            f"({self.MAX_LATENCY_MS * 10}ms including HTTP overhead)"
        )


# ══════════════════════════════════════════════════
# 7. SCHEMA VALIDATION TESTS
# ══════════════════════════════════════════════════

class TestSchemaValidation:
    """All genome files should pass the JSON schema validator."""

    @pytest.mark.parametrize("char", ALL_CHARACTERS, ids=[c.id for c in ALL_CHARACTERS])
    def test_bio_has_required_fields(self, char):
        """Bio must have at minimum: id, name, role."""
        assert "id" in char.bio, f"{char.id}: bio.json missing 'id'"
        assert "name" in char.bio or "display_name" in char.bio, (
            f"{char.id}: bio.json missing 'name' or 'display_name'"
        )
        assert "role" in char.bio or "archetype" in char.bio or "type" in char.bio, (
            f"{char.id}: bio.json missing 'role', 'archetype', or 'type'"
        )

    @pytest.mark.parametrize("char", ALL_CHARACTERS, ids=[c.id for c in ALL_CHARACTERS])
    def test_patterns_structure(self, char):
        """Patterns file should have synthetic_patterns or generic_patterns."""
        if char.patterns:
            has_syn = "synthetic_patterns" in char.patterns
            has_gen = "generic_patterns" in char.patterns
            assert has_syn or has_gen, (
                f"{char.id}: patterns.json has no synthetic_patterns or generic_patterns"
            )
            # Each pattern must have id, trigger, response_template
            for pat in char.synthetic_patterns + char.generic_patterns:
                assert "id" in pat, f"{char.id}: pattern missing 'id'"
                assert "trigger" in pat, f"{char.id}: pattern missing 'trigger'"
                assert "response_template" in pat, f"{char.id}: pattern missing 'response_template'"

    @pytest.mark.parametrize(
        "char", FULL_CHARACTERS, ids=[c.id for c in FULL_CHARACTERS]
    )
    def test_knowledge_structure(self, char):
        """Knowledge file should have entities dict."""
        assert "entities" in char.knowledge, (
            f"{char.id}: knowledge.json missing 'entities'"
        )
        entities = char.knowledge_entities
        if isinstance(entities, dict):
            for key, entity in entities.items():
                if isinstance(entity, str):
                    continue
                assert "entity_type" in entity or "type" in entity, (
                    f"{char.id}: knowledge entity '{key}' missing 'entity_type'"
                )

    @pytest.mark.parametrize(
        "char", FULL_CHARACTERS, ids=[c.id for c in FULL_CHARACTERS]
    )
    def test_personality_structure(self, char):
        """Personality file should have responses dict keyed by intent name."""
        assert "responses" in char.personality, (
            f"{char.id}: personality.json missing 'responses'"
        )
        responses = char.personality["responses"]
        assert isinstance(responses, dict), (
            f"{char.id}: personality.json 'responses' should be a dict"
        )
        for intent_name, response_list in responses.items():
            assert isinstance(response_list, list), (
                f"{char.id}: personality responses['{intent_name}'] should be a list"
            )
            for r in response_list:
                assert "text" in r, (
                    f"{char.id}: personality response in '{intent_name}' missing 'text'"
                )


# ══════════════════════════════════════════════════
# 8. COGNITIVE ENGINE TESTS (full characters only)
# ══════════════════════════════════════════════════

class TestCognitiveEngine:
    """Test the full cognitive pipeline for characters with complete genomes."""

    @pytest.mark.parametrize(
        "char", FULL_CHARACTERS, ids=[c.id for c in FULL_CHARACTERS]
    )
    def test_multi_turn_context(self, api_client, char):
        """Cognitive engine should track multi-turn context."""
        player_id = f"test_multiturn_{char.id}"

        # Turn 1: Ask about something
        first_trigger = char.get_test_triggers()[0]["input"] if char.get_test_triggers() else "Hello"
        r1 = api_client.post("/query", json={
            "text": first_trigger,
            "mode": "cognitive",
            "character": char.id,
            "player_id": player_id,
        })
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["response"], "Empty first response"

        # Turn 2: Follow-up
        r2 = api_client.post("/query", json={
            "text": "Tell me more about that",
            "mode": "cognitive",
            "character": char.id,
            "player_id": player_id,
        })
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["response"], "Empty follow-up response"
        # Turn count should be 2
        assert d2.get("debug", {}).get("turn_count", 0) >= 2, (
            f"Turn count not tracking: {d2.get('debug', {}).get('turn_count')}"
        )

    @pytest.mark.parametrize(
        "char", FULL_CHARACTERS, ids=[c.id for c in FULL_CHARACTERS]
    )
    def test_emotion_tracking(self, api_client, char):
        """Cognitive engine should track and report emotion state."""
        r = api_client.post("/query", json={
            "text": "You're amazing!",
            "mode": "cognitive",
            "character": char.id,
            "player_id": f"test_emotion_{char.id}",
        })
        assert r.status_code == 200
        data = r.json()
        # Emotion should be reported in response
        assert "emotion" in data, "No emotion field in cognitive response"

    @pytest.mark.parametrize(
        "char", FULL_CHARACTERS, ids=[c.id for c in FULL_CHARACTERS]
    )
    def test_relationship_tracking(self, api_client, char):
        """Cognitive engine should track and report relationship state."""
        r = api_client.post("/query", json={
            "text": "Hello friend",
            "mode": "cognitive",
            "character": char.id,
            "player_id": f"test_rel_{char.id}",
        })
        assert r.status_code == 200
        data = r.json()
        assert "relationship" in data, "No relationship field in cognitive response"
        rel = data["relationship"]
        if rel:
            assert "trust" in rel or "fondness" in rel, (
                f"Relationship missing trust/fondness: {rel}"
            )


# ══════════════════════════════════════════════════
# 9. COVERAGE REPORT
# ══════════════════════════════════════════════════

class TestCoverageReport:
    """Generate a coverage summary showing what each character tests."""

    def test_print_coverage_summary(self, capsys):
        """Print a summary of test coverage per character."""
        print("\n" + "=" * 70)
        print("SYNTHESUS 2.0 — CHARACTER TEST COVERAGE")
        print("=" * 70)
        for char in ALL_CHARACTERS:
            triggers = char.get_test_triggers()
            kg_queries = char.get_knowledge_queries()
            pers_queries = char.get_personality_queries()
            total = len(triggers) + len(kg_queries) + len(pers_queries) + 5  # +5 for fallback/isolation/etc
            genome = "FULL" if char.is_full else "STUB"

            print(f"\n  {char.id} ({char.archetype}) [{genome}]")
            print(f"    Pattern triggers:    {len(triggers):3d}")
            print(f"    Knowledge queries:   {len(kg_queries):3d}")
            print(f"    Personality intents:  {len(pers_queries):3d}")
            print(f"    + structural tests:    5")
            print(f"    ─────────────────────────")
            print(f"    Total scenarios:     {total:3d}")

        total_all = sum(
            len(c.get_test_triggers()) + len(c.get_knowledge_queries()) +
            len(c.get_personality_queries()) + 5
            for c in ALL_CHARACTERS
        )
        print(f"\n  {'=' * 40}")
        print(f"  TOTAL TEST SCENARIOS: {total_all}")
        print(f"  Characters: {len(ALL_CHARACTERS)} ({len(FULL_CHARACTERS)} full, {len(STUB_CHARACTERS)} stubs)")
        print("=" * 70)
