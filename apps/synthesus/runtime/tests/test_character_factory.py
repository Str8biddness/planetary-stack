"""
Synthesus 2.0 — Character Factory Tests
Tests auto-generation of complete character genomes.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from character_factory_v2 import CharacterFactory, CharacterSpec, _ARCHETYPE_TEMPLATES


@pytest.fixture
def factory(tmp_path):
    return CharacterFactory(characters_dir=str(tmp_path / "characters"))


class TestCharacterGeneration:
    def test_generate_merchant(self, factory, tmp_path):
        spec = CharacterSpec(
            name="Borgin Steelhand",
            archetype="merchant",
            setting="medieval_fantasy",
            location="Ironhaven",
            backstory="A grizzled merchant who's seen it all.",
        )
        result = factory.generate(spec, output_dir=str(tmp_path / "borgin"))
        assert result["id"] == "borgin"
        assert all(os.path.exists(p) for p in result["files"].values())
        assert result["stats"]["patterns"] > 5
        assert result["stats"]["entities"] > 0
        assert result["stats"]["personality_intents"] >= 10

    def test_generate_guard(self, factory, tmp_path):
        spec = CharacterSpec(name="Theron Ashguard", archetype="guard", location="Westgate")
        result = factory.generate(spec, output_dir=str(tmp_path / "theron"))
        assert result["stats"]["patterns"] > 3

    def test_generate_innkeeper(self, factory, tmp_path):
        spec = CharacterSpec(name="Elda Brightwater", archetype="innkeeper")
        result = factory.generate(spec, output_dir=str(tmp_path / "elda"))
        bio = json.load(open(result["files"]["bio"]))
        assert bio["archetype"] == "innkeeper"
        assert "Elda" in bio["name"]

    def test_generate_scholar(self, factory, tmp_path):
        spec = CharacterSpec(name="Professor Grimald", archetype="scholar", specialty="ancient runes")
        result = factory.generate(spec, output_dir=str(tmp_path / "grimald"))
        assert result["stats"]["patterns"] > 3

    def test_generate_healer(self, factory, tmp_path):
        spec = CharacterSpec(name="Sister Mirella", archetype="healer")
        result = factory.generate(spec, output_dir=str(tmp_path / "mirella"))
        assert result["stats"]["personality_intents"] >= 10

    def test_generate_blacksmith(self, factory, tmp_path):
        spec = CharacterSpec(name="Volkar Ironbrow", archetype="blacksmith")
        result = factory.generate(spec, output_dir=str(tmp_path / "volkar"))
        assert result["stats"]["patterns"] > 5


class TestBioGeneration:
    def test_bio_has_required_fields(self, factory, tmp_path):
        spec = CharacterSpec(name="Test NPC", archetype="merchant")
        result = factory.generate(spec, output_dir=str(tmp_path / "test"))
        bio = json.load(open(result["files"]["bio"]))
        assert "id" in bio
        assert "name" in bio
        assert "archetype" in bio
        assert "role" in bio
        assert "pattern_domains" in bio
        assert isinstance(bio["pattern_domains"], list)

    def test_bio_includes_safety_rules(self, factory, tmp_path):
        spec = CharacterSpec(
            name="Safe NPC",
            archetype="healer",
            safety_rules=["Never provide medical advice", "Always suggest professional help"],
        )
        result = factory.generate(spec, output_dir=str(tmp_path / "safe"))
        bio = json.load(open(result["files"]["bio"]))
        assert "safety_rules" in bio
        assert len(bio["safety_rules"]) == 2


class TestPatternsGeneration:
    def test_patterns_have_greeting(self, factory, tmp_path):
        spec = CharacterSpec(name="Test", archetype="merchant")
        result = factory.generate(spec, output_dir=str(tmp_path / "test"))
        patterns = json.load(open(result["files"]["patterns"]))
        syn = patterns["synthetic_patterns"]
        greeting_pats = [p for p in syn if "greeting" in p["id"]]
        assert len(greeting_pats) > 0

    def test_patterns_have_identity(self, factory, tmp_path):
        spec = CharacterSpec(name="Test", archetype="merchant")
        result = factory.generate(spec, output_dir=str(tmp_path / "test"))
        patterns = json.load(open(result["files"]["patterns"]))
        syn = patterns["synthetic_patterns"]
        identity_pats = [p for p in syn if "identity" in p["id"]]
        assert len(identity_pats) > 0

    def test_merchant_has_shop_patterns(self, factory, tmp_path):
        spec = CharacterSpec(name="Test", archetype="merchant")
        result = factory.generate(spec, output_dir=str(tmp_path / "test"))
        patterns = json.load(open(result["files"]["patterns"]))
        syn = patterns["synthetic_patterns"]
        shop_pats = [p for p in syn if p.get("domain") == "shop"]
        assert len(shop_pats) >= 3

    def test_patterns_have_fallback(self, factory, tmp_path):
        spec = CharacterSpec(name="Test", archetype="guard")
        result = factory.generate(spec, output_dir=str(tmp_path / "test"))
        patterns = json.load(open(result["files"]["patterns"]))
        assert "fallback" in patterns
        assert len(patterns["fallback"]) > 0

    def test_custom_patterns_included(self, factory, tmp_path):
        custom = [{
            "id": "custom_test",
            "trigger": ["custom trigger"],
            "response_template": "Custom response",
            "confidence": 0.9,
        }]
        spec = CharacterSpec(name="Test", archetype="merchant", custom_patterns=custom)
        result = factory.generate(spec, output_dir=str(tmp_path / "test"))
        patterns = json.load(open(result["files"]["patterns"]))
        ids = [p["id"] for p in patterns["synthetic_patterns"]]
        assert "custom_test" in ids


class TestKnowledgeGeneration:
    def test_self_entity_created(self, factory, tmp_path):
        spec = CharacterSpec(name="Test NPC", archetype="merchant")
        result = factory.generate(spec, output_dir=str(tmp_path / "test"))
        knowledge = json.load(open(result["files"]["knowledge"]))
        entities = knowledge["entities"]
        assert "test" in entities
        assert entities["test"]["entity_type"] == "self"

    def test_location_entity_created(self, factory, tmp_path):
        spec = CharacterSpec(name="Test", archetype="merchant", location="Goldport")
        result = factory.generate(spec, output_dir=str(tmp_path / "test"))
        knowledge = json.load(open(result["files"]["knowledge"]))
        assert "goldport" in knowledge["entities"]

    def test_custom_entities_included(self, factory, tmp_path):
        spec = CharacterSpec(
            name="Test", archetype="merchant",
            knowledge_entities=["Dragon's Tooth Ale", "The Old Bridge"],
        )
        result = factory.generate(spec, output_dir=str(tmp_path / "test"))
        knowledge = json.load(open(result["files"]["knowledge"]))
        assert result["stats"]["entities"] >= 3  # self + 2 custom


class TestPersonalityGeneration:
    def test_has_all_intents(self, factory, tmp_path):
        spec = CharacterSpec(name="Test", archetype="merchant")
        result = factory.generate(spec, output_dir=str(tmp_path / "test"))
        personality = json.load(open(result["files"]["personality"]))
        responses = personality["responses"]
        expected_intents = {"song", "joke", "favorite", "personal", "philosophical",
                          "creative_request", "rumor", "advice", "opinion",
                          "compliment_response", "insult_response"}
        assert set(responses.keys()) == expected_intents


class TestRegistryUpdate:
    def test_registry_created(self, factory, tmp_path):
        spec = CharacterSpec(name="Test", archetype="merchant")
        factory.generate(spec, output_dir=str(tmp_path / "test"))
        registry_path = Path(factory.characters_dir) / "registry.json"
        assert registry_path.exists()
        registry = json.load(open(registry_path))
        assert "test" in registry["characters"]

    def test_multiple_characters_in_registry(self, factory, tmp_path):
        for name, arch in [("Alice", "merchant"), ("Bob", "guard"), ("Carol", "healer")]:
            spec = CharacterSpec(name=name, archetype=arch)
            factory.generate(spec, output_dir=str(tmp_path / name.lower()))
        registry = json.load(open(Path(factory.characters_dir) / "registry.json"))
        assert len(registry["characters"]) == 3


class TestAllArchetypes:
    """Test that all defined archetypes can generate valid characters."""
    @pytest.mark.parametrize("archetype", list(_ARCHETYPE_TEMPLATES.keys()))
    def test_archetype_generates(self, factory, tmp_path, archetype):
        spec = CharacterSpec(name=f"Test {archetype.title()}", archetype=archetype)
        result = factory.generate(spec, output_dir=str(tmp_path / archetype))
        assert result["stats"]["patterns"] > 0
        assert result["stats"]["personality_intents"] >= 10
        # Validate all files are valid JSON
        for key, path in result["files"].items():
            with open(path) as f:
                data = json.load(f)
            assert isinstance(data, dict), f"{key} is not a dict"
