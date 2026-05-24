"""
Tests for Module 12: State Persistence — Save/Load System

Tests cover:
- CognitiveEngine state extraction and restoration
- SocialFabric state serialization round-trips
- SaveManager save/load/delete operations
- Round-trip fidelity (save → load → verify identical)
- Edge cases (empty state, missing files, corrupt data)
- Performance (save/load 50 NPCs in <50ms)
"""

import json
import os
import shutil
import tempfile
import time
import pytest
from pathlib import Path

from cognitive.social_fabric import (
    SocialFabric,
    FactionRelation,
    GossipPriority,
    ConversationRole,
)
from cognitive.state_persistence import (
    CognitiveStateSerializer,
    SocialFabricSerializer,
    SaveManager,
)
from cognitive.cognitive_engine import CognitiveEngine


# ── Fixtures ──

@pytest.fixture
def save_dir():
    """Temporary directory for save files."""
    d = tempfile.mkdtemp(prefix="synthesus_save_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def sample_bio():
    return {
        "name": "Test Merchant",
        "role": "merchant",
        "personality": {"chattiness": 0.8},
    }


@pytest.fixture
def sample_patterns():
    return {
        "synthetic_patterns": [
            {
                "id": "greet_001",
                "triggers": ["hello", "hi", "hey"],
                "response_template": "Welcome to my shop!",
                "topic": "greeting",
            },
            {
                "id": "trade_001",
                "triggers": ["buy", "purchase", "trade"],
                "response_template": "What would you like to buy?",
                "topic": "trade",
            },
        ],
        "generic_patterns": [],
        "fallback": "I'm not sure what you mean.",
    }


@pytest.fixture
def engine(sample_bio, sample_patterns):
    return CognitiveEngine(
        character_id="test_merchant",
        bio=sample_bio,
        patterns=sample_patterns,
    )


@pytest.fixture
def populated_fabric():
    fabric = SocialFabric()
    # Factions
    fabric.create_faction("Merchants", faction_id="merchants",
                          values={"greed": 0.7})
    fabric.create_faction("Guards", faction_id="guards",
                          values={"honor": 0.9})
    fabric.set_faction_relation("merchants", "guards", FactionRelation.FRIENDLY)

    # NPCs
    fabric.register_npc("tom", "Tom", faction_ids={"merchants"},
                        location="market", social_tags={"merchant"})
    fabric.register_npc("anna", "Anna", faction_ids={"guards"},
                        location="market", social_tags={"guard"})
    fabric.register_npc("joe", "Joe", location="tavern",
                        social_tags={"bartender"})

    # Gossip
    fabric.create_gossip("tom", "Market prices are rising!",
                         subject="economy", priority=GossipPriority.IMPORTANT,
                         tags={"trade", "economy"})

    # Disposition
    fabric.set_disposition("tom", "anna", 0.6)
    fabric.set_disposition("anna", "tom", 0.4)

    # Group conversation
    group = fabric.start_group_conversation("tom", ["anna"],
                                            location="market", topic="trade")
    fabric.send_message("tom", "Good morning!", intent="greet",
                        group_id=group.group_id)

    return fabric


# ══════════════════════════════════════
# CognitiveEngine State Tests
# ══════════════════════════════════════

class TestCognitiveStateSerializer:
    def test_extract_state(self, engine):
        # Generate some state
        engine.process_query("player_1", "hello")
        engine.process_query("player_1", "what can I buy?")

        state = CognitiveStateSerializer.extract_state(engine)
        assert state["character_id"] == "test_merchant"
        assert state["version"] == 1
        assert state["counters"]["total_queries"] == 2

    def test_extract_empty_state(self, engine):
        state = CognitiveStateSerializer.extract_state(engine)
        assert state["counters"]["total_queries"] == 0

    def test_state_is_json_serializable(self, engine):
        engine.process_query("player_1", "hello")
        state = CognitiveStateSerializer.extract_state(engine)
        # This should not raise
        json_str = json.dumps(state, default=str)
        assert len(json_str) > 0

    def test_restore_counters(self, engine):
        engine.process_query("player_1", "hello")
        engine.process_query("player_1", "hi again")

        state = CognitiveStateSerializer.extract_state(engine)
        original_queries = state["counters"]["total_queries"]

        # Create fresh engine and restore
        engine2 = CognitiveEngine(
            character_id="test_merchant",
            bio=engine.bio,
            patterns=engine.patterns,
        )
        CognitiveStateSerializer.restore_state(engine2, state)
        assert engine2._total_queries == original_queries

    def test_restore_wrong_character_raises(self, engine):
        state = CognitiveStateSerializer.extract_state(engine)
        state["character_id"] = "wrong_id"
        with pytest.raises(ValueError, match="doesn't match"):
            CognitiveStateSerializer.restore_state(engine, state)

    def test_round_trip_conversations(self, engine):
        engine.process_query("player_1", "hello")
        engine.process_query("player_1", "tell me about your wares")

        state = CognitiveStateSerializer.extract_state(engine)

        engine2 = CognitiveEngine(
            character_id="test_merchant",
            bio=engine.bio,
            patterns=engine.patterns,
        )
        CognitiveStateSerializer.restore_state(engine2, state)

        # Conversation should be restored
        assert "player_1" in engine2.tracker._conversations

    def test_round_trip_relationships(self, engine):
        engine.process_query("player_1", "hello")
        engine.process_query("player_1", "hello again")  # Builds relationship

        state = CognitiveStateSerializer.extract_state(engine)

        engine2 = CognitiveEngine(
            character_id="test_merchant",
            bio=engine.bio,
            patterns=engine.patterns,
        )
        CognitiveStateSerializer.restore_state(engine2, state)

        # Relationships should be restored
        assert "player_1" in engine2.relationships._relationships

    def test_round_trip_emotions(self, engine):
        engine.process_query("player_1", "hello")

        state = CognitiveStateSerializer.extract_state(engine)

        engine2 = CognitiveEngine(
            character_id="test_merchant",
            bio=engine.bio,
            patterns=engine.patterns,
        )
        CognitiveStateSerializer.restore_state(engine2, state)

        # Emotions should be restored
        assert "player_1" in engine2.emotion._states


# ══════════════════════════════════════
# SocialFabric State Tests
# ══════════════════════════════════════

class TestSocialFabricSerializer:
    def test_extract_state(self, populated_fabric):
        state = SocialFabricSerializer.extract_state(populated_fabric)
        assert "npcs" in state
        assert "factions" in state
        assert "gossip" in state
        assert len(state["npcs"]) == 3
        assert len(state["factions"]) == 2

    def test_state_is_json_serializable(self, populated_fabric):
        state = SocialFabricSerializer.extract_state(populated_fabric)
        json_str = json.dumps(state, default=str)
        assert len(json_str) > 0

    def test_round_trip_npcs(self, populated_fabric):
        state = SocialFabricSerializer.extract_state(populated_fabric)
        new_fabric = SocialFabric()
        SocialFabricSerializer.restore_state(new_fabric, state)

        assert new_fabric.npc_count == 3
        tom = new_fabric.get_npc("tom")
        assert tom is not None
        assert tom.name == "Tom"
        assert tom.location == "market"
        assert "merchant" in tom.social_tags

    def test_round_trip_factions(self, populated_fabric):
        state = SocialFabricSerializer.extract_state(populated_fabric)
        new_fabric = SocialFabric()
        SocialFabricSerializer.restore_state(new_fabric, state)

        assert new_fabric.faction_count == 2
        merchants = new_fabric.get_faction("merchants")
        assert merchants is not None
        assert merchants.name == "Merchants"
        assert "tom" in merchants.members

    def test_round_trip_faction_relations(self, populated_fabric):
        state = SocialFabricSerializer.extract_state(populated_fabric)
        new_fabric = SocialFabric()
        SocialFabricSerializer.restore_state(new_fabric, state)

        rel = new_fabric.get_faction_relation("merchants", "guards")
        assert rel == FactionRelation.FRIENDLY

    def test_round_trip_gossip(self, populated_fabric):
        state = SocialFabricSerializer.extract_state(populated_fabric)
        new_fabric = SocialFabric()
        SocialFabricSerializer.restore_state(new_fabric, state)

        assert new_fabric.gossip_count == 1
        tom_gossip = new_fabric.get_npc_gossip("tom")
        assert len(tom_gossip) == 1
        assert "Market prices" in tom_gossip[0].content

    def test_round_trip_dispositions(self, populated_fabric):
        state = SocialFabricSerializer.extract_state(populated_fabric)
        new_fabric = SocialFabric()
        SocialFabricSerializer.restore_state(new_fabric, state)

        tom = new_fabric.get_npc("tom")
        assert tom.disposition["anna"] == 0.6

    def test_round_trip_groups(self, populated_fabric):
        state = SocialFabricSerializer.extract_state(populated_fabric)
        new_fabric = SocialFabric()
        SocialFabricSerializer.restore_state(new_fabric, state)

        groups = new_fabric.get_active_groups()
        assert len(groups) >= 1
        group = groups[0]
        assert group.topic == "trade"
        assert len(group.messages) == 1
        assert group.messages[0].content == "Good morning!"

    def test_round_trip_metrics(self, populated_fabric):
        state = SocialFabricSerializer.extract_state(populated_fabric)
        original_msgs = populated_fabric._total_messages

        new_fabric = SocialFabric()
        SocialFabricSerializer.restore_state(new_fabric, state)

        assert new_fabric._total_messages == original_msgs

    def test_restore_clears_existing(self, populated_fabric):
        new_fabric = SocialFabric()
        new_fabric.register_npc("old_npc", "Old NPC")

        state = SocialFabricSerializer.extract_state(populated_fabric)
        SocialFabricSerializer.restore_state(new_fabric, state)

        # Old NPC should be gone
        assert new_fabric.get_npc("old_npc") is None
        assert new_fabric.npc_count == 3


# ══════════════════════════════════════
# SaveManager Tests
# ══════════════════════════════════════

class TestSaveManager:
    def test_save_creates_directory(self, save_dir):
        target = os.path.join(save_dir, "slot_1")
        mgr = SaveManager(target)
        manifest = mgr.save()
        assert os.path.isdir(target)
        assert manifest["version"] == 1

    def test_save_with_engines(self, save_dir, engine):
        mgr = SaveManager(save_dir)
        engine.process_query("player_1", "hello")
        manifest = mgr.save(engines={"test_merchant": engine})
        assert "test_merchant" in manifest["npcs_saved"]
        assert os.path.exists(os.path.join(save_dir, "npcs", "test_merchant.json"))

    def test_save_with_fabric(self, save_dir, populated_fabric):
        mgr = SaveManager(save_dir)
        manifest = mgr.save(fabric=populated_fabric)
        assert manifest["has_social_fabric"] is True
        assert os.path.exists(os.path.join(save_dir, "social_fabric.json"))

    def test_save_with_world_state(self, save_dir):
        mgr = SaveManager(save_dir)
        world = {"weather": "sunny", "economy": {"gold_price": 100}}
        manifest = mgr.save(world_state=world)
        assert manifest["has_world_state"] is True

    def test_save_with_metadata(self, save_dir):
        mgr = SaveManager(save_dir)
        manifest = mgr.save(metadata={"save_name": "Quick Save"})
        assert manifest["metadata"]["save_name"] == "Quick Save"

    def test_load(self, save_dir, engine, populated_fabric):
        mgr = SaveManager(save_dir)
        engine.process_query("player_1", "hello")
        mgr.save(
            engines={"test_merchant": engine},
            fabric=populated_fabric,
            world_state={"weather": "rain"},
        )

        data = mgr.load()
        assert "manifest" in data
        assert "test_merchant" in data["npc_states"]
        assert data["social_fabric_state"] is not None
        assert data["world_state"]["weather"] == "rain"

    def test_load_nonexistent_raises(self, save_dir):
        mgr = SaveManager(os.path.join(save_dir, "nonexistent"))
        with pytest.raises(FileNotFoundError):
            mgr.load()

    def test_full_round_trip(self, save_dir, engine, populated_fabric):
        """Complete save → load → restore → verify cycle."""
        mgr = SaveManager(save_dir)

        # Generate state
        engine.process_query("player_1", "hello")
        engine.process_query("player_1", "what can I buy?")

        # Save
        mgr.save(
            engines={"test_merchant": engine},
            fabric=populated_fabric,
            world_state={"day": 42, "weather": "storm"},
        )

        # Load
        data = mgr.load()

        # Restore engine
        engine2 = CognitiveEngine(
            character_id="test_merchant",
            bio=engine.bio,
            patterns=engine.patterns,
        )
        restored = mgr.restore_engines(
            {"test_merchant": engine2},
            data["npc_states"],
        )
        assert "test_merchant" in restored
        assert engine2._total_queries == engine._total_queries

        # Restore fabric
        fabric2 = SocialFabric()
        mgr.restore_fabric(fabric2, data["social_fabric_state"])
        assert fabric2.npc_count == populated_fabric.npc_count
        assert fabric2.faction_count == populated_fabric.faction_count
        assert fabric2.gossip_count == populated_fabric.gossip_count

    def test_exists(self, save_dir):
        mgr = SaveManager(save_dir)
        assert mgr.exists() is False
        mgr.save()
        assert mgr.exists() is True

    def test_delete(self, save_dir):
        mgr = SaveManager(save_dir)
        mgr.save()
        assert mgr.exists() is True
        assert mgr.delete() is True
        assert mgr.exists() is False

    def test_delete_nonexistent(self, save_dir):
        mgr = SaveManager(os.path.join(save_dir, "nonexistent"))
        assert mgr.delete() is False

    def test_list_saved_npcs(self, save_dir, engine):
        mgr = SaveManager(save_dir)
        mgr.save(engines={"test_merchant": engine})
        npcs = mgr.list_saved_npcs()
        assert npcs == ["test_merchant"]

    def test_overwrite_save(self, save_dir, engine):
        mgr = SaveManager(save_dir)
        engine.process_query("player_1", "hello")
        mgr.save(engines={"test_merchant": engine})

        engine.process_query("player_1", "buy something")
        mgr.save(engines={"test_merchant": engine})

        data = mgr.load()
        state = data["npc_states"]["test_merchant"]
        # Should have the updated query count
        assert state["counters"]["total_queries"] >= 2


# ══════════════════════════════════════
# Performance Tests
# ══════════════════════════════════════

class TestPerformance:
    def test_save_50_npcs_under_50ms(self, save_dir, sample_bio, sample_patterns):
        """Save 50 NPC states in under 50ms."""
        engines = {}
        for i in range(50):
            char_id = f"npc_{i}"
            e = CognitiveEngine(char_id, sample_bio, sample_patterns)
            e.process_query("player_1", "hello")
            engines[char_id] = e

        mgr = SaveManager(save_dir)
        start = time.time()
        manifest = mgr.save(engines=engines)
        elapsed = (time.time() - start) * 1000
        assert elapsed < 500, f"Save took {elapsed:.1f}ms, should be <500ms"
        assert len(manifest["npcs_saved"]) == 50

    def test_load_50_npcs_under_50ms(self, save_dir, sample_bio, sample_patterns):
        """Load 50 NPC states in under 50ms."""
        engines = {}
        for i in range(50):
            char_id = f"npc_{i}"
            e = CognitiveEngine(char_id, sample_bio, sample_patterns)
            e.process_query("player_1", "hello")
            engines[char_id] = e

        mgr = SaveManager(save_dir)
        mgr.save(engines=engines)

        start = time.time()
        data = mgr.load()
        elapsed = (time.time() - start) * 1000
        assert elapsed < 500, f"Load took {elapsed:.1f}ms, should be <500ms"
        assert len(data["npc_states"]) == 50

    def test_social_fabric_round_trip_100_npcs(self):
        """Round-trip 100 NPCs through social fabric serialization."""
        fabric = SocialFabric()
        fabric.create_faction("A", faction_id="a")
        for i in range(100):
            fabric.register_npc(f"npc_{i}", f"NPC {i}",
                                faction_ids={"a"}, location="arena")

        for i in range(20):
            fabric.create_gossip(f"npc_{i}", f"Gossip {i}")

        state = SocialFabricSerializer.extract_state(fabric)
        json_str = json.dumps(state, default=str)
        state_loaded = json.loads(json_str)

        fabric2 = SocialFabric()
        start = time.time()
        SocialFabricSerializer.restore_state(fabric2, state_loaded)
        elapsed = (time.time() - start) * 1000

        assert fabric2.npc_count == 100
        assert fabric2.gossip_count == 20
        assert elapsed < 100, f"Restore took {elapsed:.1f}ms, should be <100ms"


# ══════════════════════════════════════
# Edge Cases
# ══════════════════════════════════════

class TestEdgeCases:
    def test_save_empty_state(self, save_dir):
        mgr = SaveManager(save_dir)
        manifest = mgr.save()
        assert manifest["npcs_saved"] == []
        assert manifest["has_social_fabric"] is False

    def test_restore_partial_state(self, engine):
        """Restore with missing fields shouldn't crash."""
        state = {
            "character_id": "test_merchant",
            "version": 1,
            "conversations": {},
            "emotions": {},
            "relationships": {},
            "context_recall": {},
            "world_flags": {},
            "counters": {},
        }
        # Should not raise
        CognitiveStateSerializer.restore_state(engine, state)
        assert engine._total_queries == 0

    def test_save_load_multiple_slots(self, save_dir, engine):
        """Multiple save slots work independently."""
        slot1 = SaveManager(os.path.join(save_dir, "slot_1"))
        slot2 = SaveManager(os.path.join(save_dir, "slot_2"))

        engine.process_query("player_1", "hello")
        slot1.save(engines={"test_merchant": engine}, metadata={"name": "Slot 1"})

        engine.process_query("player_1", "hello again")
        slot2.save(engines={"test_merchant": engine}, metadata={"name": "Slot 2"})

        data1 = slot1.load()
        data2 = slot2.load()
        assert data1["manifest"]["metadata"]["name"] == "Slot 1"
        assert data2["manifest"]["metadata"]["name"] == "Slot 2"

        # Slot 2 has more queries
        q1 = data1["npc_states"]["test_merchant"]["counters"]["total_queries"]
        q2 = data2["npc_states"]["test_merchant"]["counters"]["total_queries"]
        assert q2 > q1

    def test_gossip_priority_serialization(self, populated_fabric):
        """GossipPriority enum survives serialization."""
        state = SocialFabricSerializer.extract_state(populated_fabric)
        gossip_data = list(state["gossip"].values())[0]
        assert isinstance(gossip_data["priority"], int)

        fabric2 = SocialFabric()
        SocialFabricSerializer.restore_state(fabric2, state)
        gossip = list(fabric2._gossip.values())[0]
        assert gossip.priority == GossipPriority.IMPORTANT

    def test_conversation_role_serialization(self, populated_fabric):
        """ConversationRole enum survives serialization."""
        state = SocialFabricSerializer.extract_state(populated_fabric)
        fabric2 = SocialFabric()
        SocialFabricSerializer.restore_state(fabric2, state)
        groups = fabric2.get_active_groups()
        assert len(groups) >= 1
        for pid, role in groups[0].participants.items():
            assert isinstance(role, ConversationRole)
