"""
Synthesus 2.0 — Platform AI NPC Tests (Synthesus + Computress)
Tests specific to AIVM's flagship AI NPCs:
  - Genome completeness and schema validation
  - Cross-reference integrity (they reference each other)
  - Personality differentiation (same topics, different voices)
  - Knowledge coverage for AIVM platform topics
  - Hemisphere isolation (different IDs, no collision)
"""

import json
from pathlib import Path
from typing import Dict, Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
CHARACTERS_DIR = ROOT / "characters"

# ──────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────

@pytest.fixture(scope="module")
def synthesus_genome() -> Dict[str, Any]:
    """Load the full Synthesus genome."""
    char_dir = CHARACTERS_DIR / "synthesus"
    return {
        "bio": json.loads((char_dir / "bio.json").read_text()),
        "patterns": json.loads((char_dir / "patterns.json").read_text()),
        "knowledge": json.loads((char_dir / "knowledge.json").read_text()),
        "personality": json.loads((char_dir / "personality.json").read_text()),
    }


@pytest.fixture(scope="module")
def computress_genome() -> Dict[str, Any]:
    """Load the full Computress genome."""
    char_dir = CHARACTERS_DIR / "computress"
    return {
        "bio": json.loads((char_dir / "bio.json").read_text()),
        "patterns": json.loads((char_dir / "patterns.json").read_text()),
        "knowledge": json.loads((char_dir / "knowledge.json").read_text()),
        "personality": json.loads((char_dir / "personality.json").read_text()),
    }


@pytest.fixture(scope="module")
def registry() -> Dict[str, Any]:
    """Load the character registry."""
    return json.loads((CHARACTERS_DIR / "registry.json").read_text())


# ══════════════════════════════════════════════════
# 1. GENOME COMPLETENESS
# ══════════════════════════════════════════════════

class TestGenomeCompleteness:
    """Both platform NPCs must have all four genome files with valid JSON."""

    @pytest.mark.parametrize("char_id", ["synthesus", "computress"])
    @pytest.mark.parametrize("filename", ["bio.json", "patterns.json", "knowledge.json", "personality.json"])
    def test_genome_file_exists(self, char_id, filename):
        path = CHARACTERS_DIR / char_id / filename
        assert path.exists(), f"Missing {filename} for {char_id}"

    @pytest.mark.parametrize("char_id", ["synthesus", "computress"])
    @pytest.mark.parametrize("filename", ["bio.json", "patterns.json", "knowledge.json", "personality.json"])
    def test_genome_file_valid_json(self, char_id, filename):
        path = CHARACTERS_DIR / char_id / filename
        data = json.loads(path.read_text())
        assert isinstance(data, dict), f"{filename} for {char_id} is not a dict"

    @pytest.mark.parametrize("char_id", ["synthesus", "computress"])
    def test_bio_has_required_fields(self, char_id):
        bio = json.loads((CHARACTERS_DIR / char_id / "bio.json").read_text())
        required = ["character_id", "name", "display_name", "version", "hemisphere_id", "type", "status"]
        for field in required:
            assert field in bio, f"Missing '{field}' in {char_id}/bio.json"

    @pytest.mark.parametrize("char_id", ["synthesus", "computress"])
    def test_patterns_has_synthetic_patterns(self, char_id):
        patterns = json.loads((CHARACTERS_DIR / char_id / "patterns.json").read_text())
        synth = patterns.get("synthetic_patterns", [])
        assert len(synth) >= 40, f"{char_id} has only {len(synth)} synthetic patterns (need >= 40)"

    @pytest.mark.parametrize("char_id", ["synthesus", "computress"])
    def test_knowledge_has_entities(self, char_id):
        knowledge = json.loads((CHARACTERS_DIR / char_id / "knowledge.json").read_text())
        entities = knowledge.get("entities", {})
        assert len(entities) >= 10, f"{char_id} has only {len(entities)} knowledge entities (need >= 10)"

    @pytest.mark.parametrize("char_id", ["synthesus", "computress"])
    def test_personality_has_intents(self, char_id):
        personality = json.loads((CHARACTERS_DIR / char_id / "personality.json").read_text())
        responses = personality.get("responses", {})
        assert len(responses) >= 10, f"{char_id} has only {len(responses)} personality intents (need >= 10)"


# ══════════════════════════════════════════════════
# 2. CROSS-REFERENCE INTEGRITY
# ══════════════════════════════════════════════════

class TestCrossReferenceIntegrity:
    """Synthesus and Computress must correctly reference each other."""

    def test_synthesus_references_computress(self, synthesus_genome):
        """Synthesus's knowledge should mention Computress."""
        entities = synthesus_genome["knowledge"]["entities"]
        assert "computress" in entities, "Synthesus knowledge missing 'computress' entity"
        comp_entity = entities["computress"]
        assert "counterpart" in comp_entity["description"].lower() or \
               "female" in comp_entity["description"].lower(), \
               "Synthesus's computress entity should describe her as counterpart"

    def test_computress_references_synthesus(self, computress_genome):
        """Computress's knowledge should mention Synthesus."""
        entities = computress_genome["knowledge"]["entities"]
        assert "synthesus_npc" in entities, "Computress knowledge missing 'synthesus_npc' entity"
        synth_entity = entities["synthesus_npc"]
        assert "counterpart" in synth_entity["description"].lower() or \
               "male" in synth_entity["description"].lower(), \
               "Computress's synthesus entity should describe him as counterpart"

    def test_synthesus_bio_references_computress(self, synthesus_genome):
        """Synthesus bio should have relationship_to_computress."""
        bio = synthesus_genome["bio"]
        assert "relationship_to_computress" in bio, \
            "Synthesus bio missing 'relationship_to_computress'"

    def test_computress_bio_references_synthesus(self, computress_genome):
        """Computress bio should have relationship_to_synthesus."""
        bio = computress_genome["bio"]
        assert "relationship_to_synthesus" in bio, \
            "Computress bio missing 'relationship_to_synthesus'"

    def test_both_reference_aivm(self, synthesus_genome, computress_genome):
        """Both characters must have AIVM in their knowledge."""
        assert "aivm" in synthesus_genome["knowledge"]["entities"]
        assert "aivm" in computress_genome["knowledge"]["entities"]


# ══════════════════════════════════════════════════
# 3. PERSONALITY DIFFERENTIATION
# ══════════════════════════════════════════════════

class TestPersonalityDifferentiation:
    """Same topics, different voices — verify character distinction."""

    def test_different_genders(self, synthesus_genome, computress_genome):
        assert synthesus_genome["bio"]["gender"] == "male"
        assert computress_genome["bio"]["gender"] == "female"

    def test_different_voice_profiles(self, synthesus_genome, computress_genome):
        s_voice = synthesus_genome["bio"]["persona"]["voice_profile"]
        c_voice = computress_genome["bio"]["persona"]["voice_profile"]
        assert s_voice != c_voice, "Platform NPCs should have different voice profiles"

    def test_different_tones(self, synthesus_genome, computress_genome):
        s_tone = synthesus_genome["bio"]["persona"]["tone"]
        c_tone = computress_genome["bio"]["persona"]["tone"]
        assert s_tone != c_tone, "Platform NPCs should have different tones"

    def test_aivm_knowledge_different_perspectives(self, synthesus_genome, computress_genome):
        """Both know about AIVM, but explain from different angles."""
        s_desc = synthesus_genome["knowledge"]["entities"]["aivm"]["description"]
        c_desc = computress_genome["knowledge"]["entities"]["aivm"]["description"]
        assert s_desc != c_desc, "AIVM descriptions should differ between characters"

    def test_personality_responses_differ(self, synthesus_genome, computress_genome):
        """Same intent categories, different response text."""
        shared_intents = set(synthesus_genome["personality"]["responses"].keys()) & \
                         set(computress_genome["personality"]["responses"].keys())
        assert len(shared_intents) >= 8, f"Expected >= 8 shared intent categories, got {len(shared_intents)}"
        for intent in shared_intents:
            s_text = synthesus_genome["personality"]["responses"][intent][0]["text"]
            c_text = computress_genome["personality"]["responses"][intent][0]["text"]
            assert s_text != c_text, f"Intent '{intent}' has identical response text"

    def test_synthesus_more_technical(self, synthesus_genome):
        """Synthesus should use more technical language."""
        s_tone = synthesus_genome["bio"]["persona"]["tone"].lower()
        assert any(w in s_tone for w in ["technical", "precise", "authoritative"]), \
            f"Synthesus tone should be technical/precise, got: {s_tone}"

    def test_computress_more_creative(self, computress_genome):
        """Computress should use more creative/warm language."""
        c_tone = computress_genome["bio"]["persona"]["tone"].lower()
        assert any(w in c_tone for w in ["warm", "engaging", "creative", "approachable"]), \
            f"Computress tone should be warm/engaging, got: {c_tone}"


# ══════════════════════════════════════════════════
# 4. KNOWLEDGE COVERAGE
# ══════════════════════════════════════════════════

class TestKnowledgeCoverage:
    """Both NPCs must cover essential AIVM platform topics."""

    REQUIRED_ENTITIES = ["aivm", "synthesus_engine", "ppbrs", "character_genome", "dual_hemisphere"]

    @pytest.mark.parametrize("char_id", ["synthesus", "computress"])
    @pytest.mark.parametrize("entity", REQUIRED_ENTITIES)
    def test_required_entity_present(self, char_id, entity):
        knowledge = json.loads((CHARACTERS_DIR / char_id / "knowledge.json").read_text())
        entities = knowledge.get("entities", {})
        assert entity in entities, f"{char_id} missing required entity '{entity}'"

    @pytest.mark.parametrize("char_id", ["synthesus", "computress"])
    def test_all_entities_have_descriptions(self, char_id):
        knowledge = json.loads((CHARACTERS_DIR / char_id / "knowledge.json").read_text())
        for entity_key, entity in knowledge["entities"].items():
            assert "description" in entity, f"{char_id}:{entity_key} missing description"
            assert len(entity["description"]) >= 50, \
                f"{char_id}:{entity_key} description too short ({len(entity['description'])} chars)"

    @pytest.mark.parametrize("char_id", ["synthesus", "computress"])
    def test_entities_have_types(self, char_id):
        knowledge = json.loads((CHARACTERS_DIR / char_id / "knowledge.json").read_text())
        valid_types = {"organization", "technology", "concept", "person", "location", "event"}
        for entity_key, entity in knowledge["entities"].items():
            assert "entity_type" in entity, f"{char_id}:{entity_key} missing entity_type"
            assert entity["entity_type"] in valid_types, \
                f"{char_id}:{entity_key} has invalid entity_type '{entity['entity_type']}'"


# ══════════════════════════════════════════════════
# 5. HEMISPHERE ISOLATION
# ══════════════════════════════════════════════════

class TestHemisphereIsolation:
    """Platform NPCs use reserved hemisphere IDs 1 and 2."""

    def test_synthesus_hemisphere_id(self, synthesus_genome):
        assert synthesus_genome["bio"]["hemisphere_id"] == 1

    def test_computress_hemisphere_id(self, computress_genome):
        assert computress_genome["bio"]["hemisphere_id"] == 2

    def test_no_hemisphere_collision(self, registry):
        """All characters in registry must have unique hemisphere IDs."""
        ids = [c["hemisphere_id"] for c in registry["characters"]]
        assert len(ids) == len(set(ids)), f"Hemisphere ID collision detected: {ids}"

    def test_platform_npcs_in_registry(self, registry):
        """Both platform NPCs must appear in the registry."""
        char_ids = [c["character_id"] for c in registry["characters"]]
        assert "synthesus" in char_ids, "Synthesus missing from registry"
        assert "computress" in char_ids, "Computress missing from registry"

    def test_registry_hemisphere_allocation(self, registry):
        """Registry hemisphere_allocation must include platform NPCs."""
        alloc = registry["hemisphere_allocation"]
        assert alloc.get("1") == "synthesus"
        assert alloc.get("2") == "computress"


# ══════════════════════════════════════════════════
# 6. PATTERN QUALITY
# ══════════════════════════════════════════════════

class TestPatternQuality:
    """Pattern files should be well-structured and complete."""

    @pytest.mark.parametrize("char_id", ["synthesus", "computress"])
    def test_all_patterns_have_ids(self, char_id):
        patterns = json.loads((CHARACTERS_DIR / char_id / "patterns.json").read_text())
        for pat in patterns.get("synthetic_patterns", []):
            assert "id" in pat, f"{char_id} pattern missing 'id': {pat.get('trigger', ['?'])}"

    @pytest.mark.parametrize("char_id", ["synthesus", "computress"])
    def test_all_patterns_have_triggers(self, char_id):
        patterns = json.loads((CHARACTERS_DIR / char_id / "patterns.json").read_text())
        for pat in patterns.get("synthetic_patterns", []):
            triggers = pat.get("trigger", [])
            assert len(triggers) >= 1, f"{char_id} pattern {pat.get('id', '?')} has no triggers"

    @pytest.mark.parametrize("char_id", ["synthesus", "computress"])
    def test_all_patterns_have_responses(self, char_id):
        patterns = json.loads((CHARACTERS_DIR / char_id / "patterns.json").read_text())
        for pat in patterns.get("synthetic_patterns", []):
            assert "response_template" in pat, \
                f"{char_id} pattern {pat.get('id', '?')} missing response_template"

    @pytest.mark.parametrize("char_id", ["synthesus", "computress"])
    def test_generic_patterns_exist(self, char_id):
        patterns = json.loads((CHARACTERS_DIR / char_id / "patterns.json").read_text())
        generics = patterns.get("generic_patterns", [])
        assert len(generics) >= 2, f"{char_id} has only {len(generics)} generic patterns (need >= 2)"

    @pytest.mark.parametrize("char_id", ["synthesus", "computress"])
    def test_no_duplicate_pattern_ids(self, char_id):
        patterns = json.loads((CHARACTERS_DIR / char_id / "patterns.json").read_text())
        ids = [p["id"] for p in patterns.get("synthetic_patterns", []) if "id" in p]
        dupes = [x for x in ids if ids.count(x) > 1]
        assert len(dupes) == 0, f"{char_id} has duplicate pattern IDs: {set(dupes)}"


# ══════════════════════════════════════════════════
# 7. PERSONALITY COMPLETENESS
# ══════════════════════════════════════════════════

class TestPersonalityCompleteness:
    """Personality files should cover all standard intent categories."""

    REQUIRED_INTENTS = [
        "song", "joke", "favorite", "personal", "philosophical",
        "creative_request", "rumor", "advice", "opinion",
        "compliment_response", "insult_response"
    ]

    @pytest.mark.parametrize("char_id", ["synthesus", "computress"])
    @pytest.mark.parametrize("intent", REQUIRED_INTENTS)
    def test_required_intent_present(self, char_id, intent):
        personality = json.loads((CHARACTERS_DIR / char_id / "personality.json").read_text())
        responses = personality.get("responses", {})
        assert intent in responses, f"{char_id} missing personality intent '{intent}'"

    @pytest.mark.parametrize("char_id", ["synthesus", "computress"])
    def test_all_intents_have_emotion_variants(self, char_id):
        personality = json.loads((CHARACTERS_DIR / char_id / "personality.json").read_text())
        for intent, entries in personality.get("responses", {}).items():
            for i, entry in enumerate(entries):
                assert "emotion_variants" in entry, \
                    f"{char_id} intent '{intent}' entry {i} missing emotion_variants"

    @pytest.mark.parametrize("char_id", ["synthesus", "computress"])
    def test_joke_has_multiple_entries(self, char_id):
        """Jokes should have at least 2 entries for variety."""
        personality = json.loads((CHARACTERS_DIR / char_id / "personality.json").read_text())
        jokes = personality["responses"].get("joke", [])
        assert len(jokes) >= 2, f"{char_id} has only {len(jokes)} joke entries (need >= 2)"
