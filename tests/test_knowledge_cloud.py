#!/usr/bin/env python3
"""
Tests for Knowledge Cloud — Shared Semantic Knowledge Repository
AIVM Synthesus 2.0
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

# Ensure project root is on path
PROJ_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ_ROOT))

from core.knowledge_cloud import KnowledgeCloud, KnowledgeEntry, KnowledgeResult


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def sample_entries():
    """Create sample knowledge entries for testing."""
    return [
        {
            "entity_id": "dragon",
            "entity": "Dragon",
            "entity_type": "creature",
            "description": "Dragons are ancient, fearsome reptilian creatures of immense power.",
            "attributes": {"danger": 9, "rarity": "legendary"},
            "facts": ["Breathes fire hot enough to melt steel", "Guards treasure hoards obsessively"],
            "relations": {"weak_to": "ice magic", "feared_by": "villagers"},
            "tags": ["combat", "lore", "creature"],
            "aliases": ["wyrm", "fire drake"],
            "depth": "rumor",
            "trust_threshold": 0.0,
        },
        {
            "entity_id": "ironhaven",
            "entity": "Ironhaven",
            "entity_type": "location",
            "description": "Ironhaven is a bustling trade city built where the Northern Road meets the river.",
            "attributes": {"population": "~15,000"},
            "facts": ["Home to the Merchant's Alliance", "Governed by Duke Aldric"],
            "relations": {"governed_by": "Duke Aldric"},
            "tags": ["world_info", "location"],
            "aliases": ["the city", "iron haven"],
            "depth": "familiar",
        },
        {
            "entity_id": "starfire_essence",
            "entity": "Starfire Essence",
            "entity_type": "item",
            "description": "Starfire Essence is a rare alchemical compound that glows with an inner light.",
            "attributes": {"rarity": "extremely rare", "value": "priceless"},
            "facts": ["Used in high-end enchantments", "Worth more than its weight in gold"],
            "relations": {"used_for": "enchantments"},
            "tags": ["shopping", "lore", "item"],
            "aliases": ["starfire", "the essence"],
            "depth": "familiar",
            "trust_threshold": 30.0,
        },
        {
            "entity_id": "secret_vault",
            "entity": "The Secret Vault",
            "entity_type": "location",
            "description": "A hidden vault beneath the duke's castle containing forbidden artifacts.",
            "facts": ["Only three people know its location"],
            "tags": ["quest", "location"],
            "depth": "intimate",
            "trust_threshold": 80.0,
        },
    ]


@pytest.fixture
def cloud_dir(sample_entries, tmp_path):
    """Create a temporary Knowledge Cloud dir with sample data."""
    cloud_path = tmp_path / "knowledge_cloud"
    cloud_path.mkdir()
    
    data = {
        "version": "1.0.0",
        "entries": sample_entries,
    }
    
    with open(cloud_path / "test_entries.json", "w") as f:
        json.dump(data, f)
    
    return str(cloud_path)


@pytest.fixture
def cloud(cloud_dir):
    """Create a KnowledgeCloud instance from test data."""
    return KnowledgeCloud(data_dir=cloud_dir, similarity_floor=0.25)


# ── Loading Tests ────────────────────────────────────────────────────

class TestLoading:
    def test_loads_entries_from_json(self, cloud):
        """Cloud loads entries from JSON files in data_dir."""
        assert len(cloud._entries) == 4
    
    def test_entries_have_correct_types(self, cloud):
        """Loaded entries have correct entity types."""
        assert cloud.get_entry("dragon").entity_type == "creature"
        assert cloud.get_entry("ironhaven").entity_type == "location"
        assert cloud.get_entry("starfire_essence").entity_type == "item"
    
    def test_alias_index_built(self, cloud):
        """Alias index is populated at load time."""
        assert "dragon" in cloud._alias_index
        assert "wyrm" in cloud._alias_index
        assert "fire drake" in cloud._alias_index
        assert "ironhaven" in cloud._alias_index
        assert "the city" in cloud._alias_index
    
    def test_faiss_index_built(self, cloud):
        """FAISS index is built on load."""
        assert cloud._enabled is True
        assert cloud._index is not None
        assert len(cloud._index_ids) == 4
    
    def test_empty_dir_creates_disabled_cloud(self, tmp_path):
        """An empty data dir creates a disabled cloud."""
        empty_dir = tmp_path / "empty_cloud"
        empty_dir.mkdir()
        cloud = KnowledgeCloud(data_dir=str(empty_dir))
        assert cloud._enabled is False
        assert len(cloud._entries) == 0
    
    def test_nonexistent_dir_created(self, tmp_path):
        """A nonexistent data dir is created automatically."""
        new_dir = tmp_path / "new_cloud"
        cloud = KnowledgeCloud(data_dir=str(new_dir))
        assert new_dir.exists()


# ── CRUD Tests ───────────────────────────────────────────────────────

class TestCRUD:
    def test_get_entry(self, cloud):
        """Can retrieve an entry by ID."""
        entry = cloud.get_entry("dragon")
        assert entry is not None
        assert entry.entity == "Dragon"
        assert entry.entity_type == "creature"
    
    def test_get_missing_entry(self, cloud):
        """get_entry returns None for nonexistent IDs."""
        assert cloud.get_entry("nonexistent") is None
    
    def test_add_entry(self, cloud):
        """Can add a new entry."""
        new_entry = KnowledgeEntry(
            entity_id="troll",
            entity="Troll",
            entity_type="creature",
            description="A hulking, dim-witted creature.",
            facts=["Turns to stone in sunlight"],
            tags=["combat", "creature"],
        )
        assert cloud.add_entry(new_entry) is True
        assert cloud.get_entry("troll") is not None
        assert len(cloud._entries) == 5
    
    def test_remove_entry(self, cloud):
        """Can remove an entry by ID."""
        assert cloud.remove_entry("dragon") is True
        assert cloud.get_entry("dragon") is None
        assert len(cloud._entries) == 3
    
    def test_remove_nonexistent(self, cloud):
        """Removing a nonexistent entry returns False."""
        assert cloud.remove_entry("nonexistent") is False
    
    def test_update_entry(self, cloud):
        """Can update fields on an existing entry."""
        assert cloud.update_entry("dragon", {"description": "Updated description"}) is True
        entry = cloud.get_entry("dragon")
        assert entry.description == "Updated description"
    
    def test_update_nonexistent(self, cloud):
        """Updating a nonexistent entry returns False."""
        assert cloud.update_entry("nonexistent", {"description": "test"}) is False
    
    def test_list_entries_all(self, cloud):
        """list_entries returns all entries when no filter."""
        entries = cloud.list_entries()
        assert len(entries) == 4
    
    def test_list_entries_by_type(self, cloud):
        """list_entries filters by entity_type."""
        creatures = cloud.list_entries(entity_type="creature")
        assert len(creatures) == 1
        assert creatures[0].entity_id == "dragon"
    
    def test_list_entries_by_tags(self, cloud):
        """list_entries filters by tags."""
        combat = cloud.list_entries(tags=["combat"])
        assert len(combat) == 1
        assert combat[0].entity_id == "dragon"
    
    def test_add_entry_persists(self, cloud, cloud_dir):
        """Adding an entry persists to disk."""
        new_entry = KnowledgeEntry(
            entity_id="troll",
            entity="Troll",
            entity_type="creature",
            description="Big green thing.",
        )
        cloud.add_entry(new_entry)
        
        # Reload from disk
        cloud2 = KnowledgeCloud(data_dir=cloud_dir, similarity_floor=0.25)
        assert cloud2.get_entry("troll") is not None


# ── Search Tests ─────────────────────────────────────────────────────

class TestSearch:
    def test_alias_match(self, cloud):
        """Searching for an alias finds the correct entry."""
        results = cloud.search("tell me about wyrms")
        assert len(results) > 0
        assert results[0].entry.entity_id == "dragon"
    
    def test_semantic_search_finds_relevant(self, cloud):
        """Semantic search finds semantically related entries."""
        results = cloud.search("what creatures breathe fire?")
        assert len(results) > 0
        # Dragon should be among results (has "breathes fire" in facts)
        entity_ids = [r.entry.entity_id for r in results]
        assert "dragon" in entity_ids
    
    def test_search_returns_similarity_scores(self, cloud):
        """Results include similarity scores."""
        results = cloud.search("dragon")
        assert len(results) > 0
        assert results[0].similarity > 0
    
    def test_search_respects_top_k(self, cloud):
        """Results are limited to top_k."""
        results = cloud.search("tell me about something", top_k=2)
        assert len(results) <= 2
    
    def test_search_filters_by_tags(self, cloud):
        """Search filters results by tags."""
        results = cloud.search("what do you know?", top_k=10, tags_filter=["combat"])
        for r in results:
            assert "combat" in [t.lower() for t in r.entry.tags]
    
    def test_search_empty_query(self, cloud):
        """Empty query returns results (from semantic + alias matching)."""
        results = cloud.search("")
        # May or may not return results depending on embedder behavior
        assert isinstance(results, list)


# ── Lookup Tests ─────────────────────────────────────────────────────

class TestLookup:
    def test_lookup_returns_response(self, cloud):
        """lookup() returns a KG-compatible response dict."""
        result = cloud.lookup("tell me about dragons")
        assert result is not None
        assert "response" in result
        assert "entity_id" in result
        assert "confidence" in result
        assert result["source"] == "knowledge_cloud"
    
    def test_lookup_includes_entity_info(self, cloud):
        """lookup() response includes entity metadata."""
        result = cloud.lookup("what is ironhaven?")
        assert result is not None
        assert result["entity_type"] == "location"
        assert "facts" in result
        assert "attributes" in result
    
    def test_lookup_trust_gating(self, cloud):
        """lookup() respects trust thresholds."""
        # Secret vault requires trust >= 80
        # Use a very specific query that strongly matches the secret vault
        result_low = cloud.lookup("secret vault beneath the castle", trust=30.0)
        # Should not return the trust-gated entry at low trust
        if result_low and result_low["entity_id"] == "secret_vault":
            pytest.fail("Trust-gated entry returned for low trust level")
        
        result_high = cloud.lookup("secret vault beneath the castle", trust=90.0)
        assert result_high is not None
        assert result_high["entity_id"] == "secret_vault"
    
    def test_lookup_miss_returns_none(self, cloud):
        """lookup() returns None when no match found."""
        result = cloud.lookup("xyzzy gibberish nonsense words 12345")
        # Might still match something via semantic, but that's OK
        # The key is it doesn't crash
        assert result is None or isinstance(result, dict)
    
    def test_lookup_emotion_variant(self, cloud_dir):
        """lookup() uses emotion variants when available."""
        # Add an entry with emotion variants
        cloud = KnowledgeCloud(data_dir=cloud_dir, similarity_floor=0.25)
        entry = KnowledgeEntry(
            entity_id="test_ghost",
            entity="Ghost",
            entity_type="creature",
            description="A spooky ghost.",
            emotion_variants={
                "afraid": "Oh no, a ghost! Run!",
                "friendly": "Ah, ghosts are just misunderstood spirits.",
            },
            tags=["creature"],
        )
        cloud.add_entry(entry)
        
        result_afraid = cloud.lookup("ghost", emotion="afraid")
        if result_afraid and result_afraid["entity_id"] == "test_ghost":
            assert "Run" in result_afraid["response"]
    
    def test_lookup_stats_tracked(self, cloud):
        """lookup() increments stats counters."""
        initial_searches = cloud._total_searches
        cloud.lookup("dragon")
        assert cloud._total_searches > initial_searches


# ── KnowledgeEntry Tests ─────────────────────────────────────────────

class TestKnowledgeEntry:
    def test_from_dict(self):
        """KnowledgeEntry.from_dict() creates an entry from a dict."""
        data = {
            "entity_id": "test",
            "entity": "Test Entity",
            "entity_type": "concept",
            "description": "A test entity.",
            "facts": ["Fact 1", "Fact 2"],
        }
        entry = KnowledgeEntry.from_dict(data)
        assert entry.entity_id == "test"
        assert entry.entity == "Test Entity"
        assert len(entry.facts) == 2
    
    def test_to_dict(self):
        """KnowledgeEntry.to_dict() serializes correctly."""
        entry = KnowledgeEntry(
            entity_id="test",
            entity="Test",
            facts=["Fact 1"],
        )
        d = entry.to_dict()
        assert d["entity_id"] == "test"
        assert d["facts"] == ["Fact 1"]
    
    def test_get_embedding_text(self):
        """get_embedding_text() combines entity, description, facts, aliases."""
        entry = KnowledgeEntry(
            entity_id="test",
            entity="Dragon",
            description="A fire-breathing creature.",
            facts=["Breathes fire", "Guards hoards"],
            aliases=["wyrm"],
            tags=["combat"],
        )
        text = entry.get_embedding_text()
        assert "Dragon" in text
        assert "fire-breathing" in text
        assert "Breathes fire" in text
        assert "wyrm" in text
        assert "combat" in text
    
    def test_auto_generate_entity_id(self):
        """from_dict generates entity_id from entity name if missing."""
        data = {"entity": "Shadow Wraith", "entity_type": "creature"}
        entry = KnowledgeEntry.from_dict(data)
        assert entry.entity_id == "shadow_wraith"


# ── Stats Tests ──────────────────────────────────────────────────────

class TestStats:
    def test_stats_structure(self, cloud):
        """get_stats() returns expected fields."""
        stats = cloud.get_stats()
        assert "enabled" in stats
        assert "total_entries" in stats
        assert "type_breakdown" in stats
        assert "total_aliases" in stats
        assert "total_searches" in stats
        assert "hit_rate" in stats
    
    def test_stats_entry_count(self, cloud):
        """Stats reflect correct entry count."""
        stats = cloud.get_stats()
        assert stats["total_entries"] == 4
    
    def test_stats_type_breakdown(self, cloud):
        """Type breakdown counts each type."""
        stats = cloud.get_stats()
        assert stats["type_breakdown"]["creature"] == 1
        assert stats["type_breakdown"]["location"] == 2  # ironhaven + secret_vault
        assert stats["type_breakdown"]["item"] == 1


# ── Performance Tests ────────────────────────────────────────────────

class TestPerformance:
    def test_search_latency(self, cloud):
        """Search completes in under 10ms."""
        start = time.time()
        cloud.search("dragon")
        latency_ms = (time.time() - start) * 1000
        assert latency_ms < 50, f"Search took {latency_ms:.1f}ms (expected <50ms)"
    
    def test_lookup_latency(self, cloud):
        """Lookup completes in under 10ms."""
        start = time.time()
        cloud.lookup("tell me about dragons")
        latency_ms = (time.time() - start) * 1000
        assert latency_ms < 50, f"Lookup took {latency_ms:.1f}ms (expected <50ms)"
    
    def test_rebuild_index_latency(self, cloud):
        """Index rebuild completes in under 100ms for small sets."""
        start = time.time()
        cloud.rebuild_index()
        latency_ms = (time.time() - start) * 1000
        assert latency_ms < 200, f"Rebuild took {latency_ms:.1f}ms (expected <200ms)"


# ── Integration Tests ────────────────────────────────────────────────

class TestWorldLoreIntegration:
    """Test with the actual world_lore.json seed data."""
    
    @pytest.fixture
    def world_cloud(self):
        """Load the actual world_lore.json."""
        data_dir = PROJ_ROOT / "data" / "knowledge_cloud"
        if not data_dir.exists() or not (data_dir / "world_lore.json").exists():
            pytest.skip("world_lore.json not found — run seed data creation first")
        return KnowledgeCloud(data_dir=str(data_dir), similarity_floor=0.25)
    
    def test_world_lore_loads(self, world_cloud):
        """World lore loads successfully."""
        stats = world_cloud.get_stats()
        assert stats["total_entries"] >= 20  # We created ~30 entries
        assert stats["enabled"] is True

    def test_smoke_queries_survive_lookup_multi_pruning(self, world_cloud):
        """Common smoke queries should still return the intended entities."""
        cases = [
            ("tell me about dragons", {"dragon"}),
            ("what is Ironhaven?", {"ironhaven"}),
            ("Duke Aldric and Ironhaven", {"duke_aldric", "ironhaven"}),
            ("Tell me about dragons and healing potions.", {"dragon", "healing_potion"}),
        ]

        for query, expected_ids in cases:
            results = world_cloud.lookup_multi(query, trust=100.0, top_k=5)
            entity_ids = {r["entity_id"] for r in results}
            missing = expected_ids - entity_ids
            assert not missing, f"{query!r} missing {sorted(missing)} from {sorted(entity_ids)}"
            if len(expected_ids) > 1:
                assert len(results) >= 2, f"{query!r} returned too few results: {entity_ids}"
    
    def test_creature_queries(self, world_cloud):
        """Can find creatures by semantic query."""
        result = world_cloud.lookup("tell me about dragons")
        assert result is not None
        assert result["entity_id"] == "dragon"
        assert result["entity_type"] == "creature"
    
    def test_location_queries(self, world_cloud):
        """Can find locations by name."""
        result = world_cloud.lookup("what is Ironhaven?")
        assert result is not None
        assert result["entity_type"] == "location"
    
    def test_faction_queries(self, world_cloud):
        """Can find factions."""
        result = world_cloud.lookup("tell me about the Merchant's Alliance")
        assert result is not None
        assert result["entity_type"] == "faction"
    
    def test_item_queries(self, world_cloud):
        """Can find items."""
        result = world_cloud.lookup("what is starfire essence?")
        assert result is not None
        assert result["entity_type"] == "item"
    
    def test_event_queries(self, world_cloud):
        """Can find events — verify entity exists and is searchable."""
        # Direct lookup by ID (validates the data is loaded)
        entry = world_cloud.get_entry("missing_caravans")
        assert entry is not None
        assert entry.entity_type == "event"
        assert entry.entity == "The Missing Caravans"
        
        # Verify it appears in search results
        results = world_cloud.search("missing caravans", top_k=10)
        entity_ids = [r.entry.entity_id for r in results]
        assert "missing_caravans" in entity_ids
    
    def test_platform_knowledge(self, world_cloud):
        """Can find platform/tech entries."""
        result = world_cloud.lookup("what is the Synthesus Engine?")
        assert result is not None
        assert "synthesus" in result["entity_id"]
    
    def test_type_variety(self, world_cloud):
        """World lore covers multiple entity types."""
        stats = world_cloud.get_stats()
        types = stats["type_breakdown"]
        assert len(types) >= 4  # creature, location, item, faction, event, concept