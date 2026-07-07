"""
Tests for Module 11: Social Fabric — Multi-NPC Interaction System

Tests cover:
- NPC registration and lookup
- Faction creation, membership, relations
- Disposition tracking (NPC-to-NPC feelings)
- Gossip creation and propagation
- NPC-to-NPC messaging
- Group conversations
- Interaction generation
- World tick
- Edge cases and capacity limits
"""

import time
import pytest
from cognitive.social_fabric import (
    SocialFabric,
    Faction,
    FactionRelation,
    GossipItem,
    GossipPriority,
    NPCMessage,
    GroupConversation,
    ConversationRole,
    NPCProfile,
)


@pytest.fixture
def fabric():
    """Fresh SocialFabric for each test."""
    return SocialFabric(max_gossip=100, max_groups=20)


@pytest.fixture
def populated_fabric(fabric):
    """Fabric with NPCs, factions, and gossip pre-loaded."""
    # Create factions
    merchants = fabric.create_faction("Merchants Guild", faction_id="merchants",
                                       values={"greed": 0.7, "honor": 0.4})
    guards = fabric.create_faction("Town Guard", faction_id="guards",
                                    values={"honor": 0.9, "greed": 0.1})
    thieves = fabric.create_faction("Thieves Ring", faction_id="thieves",
                                     values={"greed": 0.9, "honor": 0.1})

    # Set faction relations
    fabric.set_faction_relation("merchants", "guards", FactionRelation.FRIENDLY)
    fabric.set_faction_relation("guards", "thieves", FactionRelation.HOSTILE)
    fabric.set_faction_relation("merchants", "thieves", FactionRelation.RIVAL)

    # Register NPCs
    fabric.register_npc("vendor_tom", "Tom the Vendor",
                        faction_ids={"merchants"}, location="market",
                        social_tags={"merchant", "vendor"},
                        personality_traits={"chattiness": 0.8, "greed": 0.6})
    fabric.register_npc("guard_anna", "Anna the Guard",
                        faction_ids={"guards"}, location="market",
                        social_tags={"guard", "patrol"},
                        personality_traits={"discipline": 0.9, "chattiness": 0.3})
    fabric.register_npc("thief_shadow", "Shadow",
                        faction_ids={"thieves"}, location="alley",
                        social_tags={"thief", "rogue"},
                        personality_traits={"stealth": 0.9, "chattiness": 0.2})
    fabric.register_npc("bartender_joe", "Joe the Bartender",
                        faction_ids=set(), location="tavern",
                        social_tags={"bartender", "civilian"},
                        personality_traits={"chattiness": 0.9, "greed": 0.3})
    fabric.register_npc("vendor_lisa", "Lisa the Jeweler",
                        faction_ids={"merchants"}, location="market",
                        social_tags={"merchant", "jeweler"},
                        personality_traits={"chattiness": 0.5, "greed": 0.7})

    return fabric


# ══════════════════════════════════════
# NPC Registration Tests
# ══════════════════════════════════════

class TestNPCRegistration:
    def test_register_npc(self, fabric):
        profile = fabric.register_npc("npc_1", "Test NPC", location="town")
        assert profile.character_id == "npc_1"
        assert profile.name == "Test NPC"
        assert profile.location == "town"
        assert fabric.npc_count == 1

    def test_register_multiple_npcs(self, fabric):
        for i in range(10):
            fabric.register_npc(f"npc_{i}", f"NPC {i}")
        assert fabric.npc_count == 10

    def test_get_npc(self, fabric):
        fabric.register_npc("npc_1", "Test NPC")
        profile = fabric.get_npc("npc_1")
        assert profile is not None
        assert profile.name == "Test NPC"

    def test_get_nonexistent_npc(self, fabric):
        assert fabric.get_npc("nonexistent") is None

    def test_unregister_npc(self, fabric):
        fabric.register_npc("npc_1", "Test NPC")
        assert fabric.unregister_npc("npc_1") is True
        assert fabric.npc_count == 0
        assert fabric.get_npc("npc_1") is None

    def test_unregister_nonexistent(self, fabric):
        assert fabric.unregister_npc("nonexistent") is False

    def test_get_npcs_at_location(self, populated_fabric):
        market_npcs = populated_fabric.get_npcs_at_location("market")
        assert len(market_npcs) == 3  # Tom, Anna, Lisa

    def test_get_npcs_by_tag(self, populated_fabric):
        merchants = populated_fabric.get_npcs_by_tag("merchant")
        assert len(merchants) == 2  # Tom and Lisa

    def test_move_npc(self, populated_fabric):
        assert populated_fabric.move_npc("vendor_tom", "tavern") is True
        assert populated_fabric.get_npc("vendor_tom").location == "tavern"

    def test_move_nonexistent_npc(self, fabric):
        assert fabric.move_npc("nonexistent", "tavern") is False

    def test_registered_npcs_list(self, populated_fabric):
        ids = populated_fabric.registered_npcs
        assert "vendor_tom" in ids
        assert "guard_anna" in ids
        assert len(ids) == 5

    def test_register_with_faction(self, fabric):
        faction = fabric.create_faction("Test Faction", faction_id="test_f")
        profile = fabric.register_npc("npc_1", "NPC", faction_ids={"test_f"})
        assert "test_f" in profile.faction_ids
        assert "npc_1" in fabric.get_faction("test_f").members

    def test_unregister_cleans_factions(self, fabric):
        faction = fabric.create_faction("Test Faction", faction_id="test_f")
        fabric.register_npc("npc_1", "NPC", faction_ids={"test_f"})
        fabric.unregister_npc("npc_1")
        assert "npc_1" not in fabric.get_faction("test_f").members


# ══════════════════════════════════════
# Faction System Tests
# ══════════════════════════════════════

class TestFactionSystem:
    def test_create_faction(self, fabric):
        faction = fabric.create_faction("Warriors", description="Sword guys")
        assert faction.name == "Warriors"
        assert faction.size == 0
        assert fabric.faction_count == 1

    def test_create_faction_with_leader(self, fabric):
        fabric.register_npc("leader_1", "Leader")
        faction = fabric.create_faction("Warriors", leader="leader_1")
        assert faction.leader == "leader_1"
        assert "leader_1" in faction.members

    def test_dissolve_faction(self, fabric):
        fabric.create_faction("Warriors", faction_id="warriors")
        fabric.register_npc("npc_1", "NPC", faction_ids={"warriors"})
        assert fabric.dissolve_faction("warriors") is True
        assert fabric.faction_count == 0
        assert "warriors" not in fabric.get_npc("npc_1").faction_ids

    def test_dissolve_nonexistent(self, fabric):
        assert fabric.dissolve_faction("nonexistent") is False

    def test_join_faction(self, fabric):
        fabric.create_faction("Warriors", faction_id="warriors")
        fabric.register_npc("npc_1", "NPC")
        assert fabric.join_faction("npc_1", "warriors") is True
        assert "warriors" in fabric.get_npc("npc_1").faction_ids

    def test_join_nonexistent_faction(self, fabric):
        fabric.register_npc("npc_1", "NPC")
        assert fabric.join_faction("npc_1", "nonexistent") is False

    def test_leave_faction(self, fabric):
        fabric.create_faction("Warriors", faction_id="warriors")
        fabric.register_npc("npc_1", "NPC", faction_ids={"warriors"})
        assert fabric.leave_faction("npc_1", "warriors") is True
        assert "warriors" not in fabric.get_npc("npc_1").faction_ids

    def test_set_faction_relation(self, populated_fabric):
        rel = populated_fabric.get_faction_relation("guards", "thieves")
        assert rel == FactionRelation.HOSTILE

    def test_default_relation_is_neutral(self, fabric):
        fabric.create_faction("A", faction_id="a")
        fabric.create_faction("B", faction_id="b")
        assert fabric.get_faction_relation("a", "b") == FactionRelation.NEUTRAL

    def test_relation_is_bidirectional(self, populated_fabric):
        rel_ab = populated_fabric.get_faction_relation("guards", "thieves")
        rel_ba = populated_fabric.get_faction_relation("thieves", "guards")
        assert rel_ab == rel_ba == FactionRelation.HOSTILE

    def test_are_allies_same_faction(self, populated_fabric):
        assert populated_fabric.are_allies("vendor_tom", "vendor_lisa") is True

    def test_are_hostile(self, populated_fabric):
        assert populated_fabric.are_hostile("guard_anna", "thief_shadow") is True

    def test_not_hostile_same_faction(self, populated_fabric):
        assert populated_fabric.are_hostile("vendor_tom", "vendor_lisa") is False

    def test_get_npc_factions(self, populated_fabric):
        factions = populated_fabric.get_npc_factions("vendor_tom")
        assert len(factions) == 1
        assert factions[0].name == "Merchants Guild"

    def test_faction_values(self, populated_fabric):
        faction = populated_fabric.get_faction("merchants")
        assert faction.values["greed"] == 0.7

    def test_dissolve_cleans_relations(self, fabric):
        fabric.create_faction("A", faction_id="a")
        fabric.create_faction("B", faction_id="b")
        fabric.set_faction_relation("a", "b", FactionRelation.ALLIED)
        fabric.dissolve_faction("a")
        # Relation should be gone
        assert fabric.get_faction_relation("a", "b") == FactionRelation.NEUTRAL

    def test_remove_leader_on_unregister(self, fabric):
        fabric.register_npc("boss", "Boss")
        faction = fabric.create_faction("Team", leader="boss", faction_id="team")
        assert faction.leader == "boss"
        faction.remove_member("boss")
        assert faction.leader is None


# ══════════════════════════════════════
# Disposition Tests
# ══════════════════════════════════════

class TestDisposition:
    def test_default_disposition(self, populated_fabric):
        disp = populated_fabric.get_disposition("vendor_tom", "bartender_joe")
        # No faction relationship, no personal override = near 0
        assert -0.1 <= disp <= 0.1

    def test_set_disposition(self, populated_fabric):
        populated_fabric.set_disposition("vendor_tom", "bartender_joe", 0.8)
        raw = populated_fabric.get_npc("vendor_tom").disposition["bartender_joe"]
        assert raw == 0.8

    def test_adjust_disposition(self, populated_fabric):
        populated_fabric.set_disposition("vendor_tom", "bartender_joe", 0.5)
        new_val = populated_fabric.adjust_disposition("vendor_tom", "bartender_joe", -0.2)
        assert abs(new_val - 0.3) < 0.01

    def test_disposition_clamped(self, populated_fabric):
        populated_fabric.set_disposition("vendor_tom", "bartender_joe", 0.9)
        populated_fabric.adjust_disposition("vendor_tom", "bartender_joe", 0.5)
        raw = populated_fabric.get_npc("vendor_tom").disposition["bartender_joe"]
        assert raw == 1.0

    def test_disposition_clamp_negative(self, populated_fabric):
        populated_fabric.set_disposition("vendor_tom", "bartender_joe", -0.9)
        populated_fabric.adjust_disposition("vendor_tom", "bartender_joe", -0.5)
        raw = populated_fabric.get_npc("vendor_tom").disposition["bartender_joe"]
        assert raw == -1.0

    def test_faction_bonus_allies(self, populated_fabric):
        # Tom and Lisa are both in Merchants — should get ally bonus
        disp = populated_fabric.get_disposition("vendor_tom", "vendor_lisa")
        assert disp > 0  # Ally bonus pushes above zero

    def test_faction_penalty_hostile(self, populated_fabric):
        # Guard Anna vs Thief Shadow — hostile factions
        disp = populated_fabric.get_disposition("guard_anna", "thief_shadow")
        assert disp < 0  # Hostility penalty

    def test_set_disposition_nonexistent(self, fabric):
        assert fabric.set_disposition("fake_a", "fake_b", 0.5) is False

    def test_adjust_disposition_nonexistent(self, fabric):
        result = fabric.adjust_disposition("fake_a", "fake_b", 0.1)
        assert result == 0.0


# ══════════════════════════════════════
# Gossip Propagation Tests
# ══════════════════════════════════════

class TestGossipPropagation:
    def test_create_gossip(self, populated_fabric):
        gossip = populated_fabric.create_gossip(
            "vendor_tom", "The king is coming to town!",
            priority=GossipPriority.IMPORTANT,
            tags={"royalty", "event"},
        )
        assert gossip.content == "The king is coming to town!"
        assert gossip.source_npc == "vendor_tom"
        assert "vendor_tom" in gossip.heard_by
        assert populated_fabric.gossip_count == 1

    def test_spread_gossip(self, populated_fabric):
        gossip = populated_fabric.create_gossip("vendor_tom", "Big news!")
        result = populated_fabric.spread_gossip(
            gossip.gossip_id, "vendor_tom", "guard_anna"
        )
        assert result is not None
        assert result["hops"] == 1
        assert "guard_anna" in gossip.heard_by

    def test_cannot_spread_unknown_gossip(self, populated_fabric):
        gossip = populated_fabric.create_gossip("vendor_tom", "Secret!")
        # Anna doesn't know this gossip, so she can't spread it
        result = populated_fabric.spread_gossip(
            gossip.gossip_id, "guard_anna", "bartender_joe"
        )
        assert result is None

    def test_cannot_spread_to_same_npc(self, populated_fabric):
        gossip = populated_fabric.create_gossip("vendor_tom", "Info!")
        populated_fabric.spread_gossip(gossip.gossip_id, "vendor_tom", "guard_anna")
        # Try to tell Anna again
        result = populated_fabric.spread_gossip(
            gossip.gossip_id, "vendor_tom", "guard_anna"
        )
        assert result is None  # Already knows

    def test_gossip_fidelity_decay(self, populated_fabric):
        gossip = populated_fabric.create_gossip(
            "vendor_tom", "Original fact", truth_value=1.0, decay_per_hop=0.2
        )
        assert gossip.current_fidelity == 1.0
        populated_fabric.spread_gossip(gossip.gossip_id, "vendor_tom", "guard_anna")
        assert abs(gossip.current_fidelity - 0.8) < 0.01
        populated_fabric.spread_gossip(gossip.gossip_id, "guard_anna", "bartender_joe")
        assert abs(gossip.current_fidelity - 0.6) < 0.01

    def test_gossip_becomes_stale(self, populated_fabric):
        gossip = populated_fabric.create_gossip(
            "vendor_tom", "Ancient rumor", truth_value=0.5, decay_per_hop=0.2
        )
        # 3 hops: 0.5 - 0.6 = -0.1 → clamped to 0
        for i in range(3):
            target = f"temp_npc_{i}"
            populated_fabric.register_npc(target, f"Temp {i}", location="market")
            last_teller = "vendor_tom" if i == 0 else f"temp_npc_{i-1}"
            populated_fabric.spread_gossip(gossip.gossip_id, last_teller, target)
        assert gossip.is_stale is True

    def test_propagate_at_location(self, populated_fabric):
        gossip = populated_fabric.create_gossip(
            "vendor_tom", "Market news!", priority=GossipPriority.IMPORTANT
        )
        # Tom is at market with Anna and Lisa
        events = populated_fabric.propagate_gossip_at_location("market")
        assert len(events) >= 1  # At least Anna or Lisa should hear it

    def test_hostile_npcs_dont_share(self, populated_fabric):
        # Move Shadow to market, set extreme negative disposition
        populated_fabric.move_npc("thief_shadow", "market")
        populated_fabric.set_disposition("vendor_tom", "thief_shadow", -0.8)
        gossip = populated_fabric.create_gossip("vendor_tom", "Guard patrol routes")
        # Tom shouldn't share with Shadow (hostile faction + low disposition)
        events = populated_fabric.propagate_gossip_at_location("market")
        shadow_heard = any(e["to_npc"] == "thief_shadow" and e["from_npc"] == "vendor_tom"
                         for e in events)
        assert shadow_heard is False

    def test_get_npc_gossip(self, populated_fabric):
        g1 = populated_fabric.create_gossip("vendor_tom", "Gossip 1")
        g2 = populated_fabric.create_gossip("vendor_tom", "Gossip 2")
        gossip_list = populated_fabric.get_npc_gossip("vendor_tom")
        assert len(gossip_list) == 2

    def test_get_gossip_about(self, populated_fabric):
        populated_fabric.create_gossip("vendor_tom", "Anna was promoted", subject="guard_anna")
        populated_fabric.create_gossip("vendor_tom", "Nice weather", subject="weather")
        about_anna = populated_fabric.get_gossip_about("guard_anna")
        assert len(about_anna) == 1
        assert about_anna[0].subject == "guard_anna"

    def test_gossip_capacity_eviction(self, fabric):
        fabric_small = SocialFabric(max_gossip=5)
        fabric_small.register_npc("npc_1", "NPC")
        for i in range(7):
            fabric_small.create_gossip("npc_1", f"Gossip {i}")
        assert fabric_small.gossip_count <= 5

    def test_gossip_tags(self, populated_fabric):
        gossip = populated_fabric.create_gossip(
            "vendor_tom", "Trade routes unsafe",
            tags={"trade", "danger"}
        )
        assert "trade" in gossip.tags
        assert "danger" in gossip.tags


# ══════════════════════════════════════
# Messaging Tests
# ══════════════════════════════════════

class TestMessaging:
    def test_send_direct_message(self, populated_fabric):
        msg = populated_fabric.send_message(
            "vendor_tom", "Hello Anna!", intent="greet", target_id="guard_anna"
        )
        assert msg is not None
        assert msg.sender_id == "vendor_tom"
        assert msg.target_id == "guard_anna"
        assert msg.intent == "greet"

    def test_send_message_nonexistent_sender(self, fabric):
        msg = fabric.send_message("fake", "Hello!")
        assert msg is None

    def test_send_message_nonexistent_target(self, populated_fabric):
        msg = populated_fabric.send_message(
            "vendor_tom", "Hello!", target_id="nonexistent"
        )
        assert msg is None

    def test_insult_decreases_disposition(self, populated_fabric):
        populated_fabric.set_disposition("guard_anna", "vendor_tom", 0.5)
        populated_fabric.send_message(
            "vendor_tom", "You're useless!", intent="insult", target_id="guard_anna"
        )
        disp = populated_fabric.get_npc("guard_anna").disposition["vendor_tom"]
        assert disp < 0.5  # Should decrease

    def test_greet_increases_disposition(self, populated_fabric):
        populated_fabric.set_disposition("guard_anna", "vendor_tom", 0.0)
        populated_fabric.send_message(
            "vendor_tom", "Good morning Anna!", intent="greet", target_id="guard_anna"
        )
        disp = populated_fabric.get_npc("guard_anna").disposition["vendor_tom"]
        assert disp > 0.0

    def test_get_recent_messages(self, populated_fabric):
        for i in range(5):
            populated_fabric.send_message("vendor_tom", f"Msg {i}", target_id="guard_anna")
        msgs = populated_fabric.get_recent_messages()
        assert len(msgs) == 5

    def test_get_messages_filtered_by_npc(self, populated_fabric):
        populated_fabric.send_message("vendor_tom", "Hi Anna", target_id="guard_anna")
        populated_fabric.send_message("vendor_tom", "Hi Joe", target_id="bartender_joe")
        msgs = populated_fabric.get_recent_messages(npc_id="guard_anna")
        assert len(msgs) == 1

    def test_message_handler(self, populated_fabric):
        received = []
        populated_fabric.on_message("warn", lambda msg: received.append(msg))
        populated_fabric.send_message(
            "guard_anna", "Thief spotted!", intent="warn", target_id="vendor_tom"
        )
        assert len(received) == 1
        assert received[0].intent == "warn"

    def test_wildcard_handler(self, populated_fabric):
        received = []
        populated_fabric.on_message("*", lambda msg: received.append(msg))
        populated_fabric.send_message("vendor_tom", "Hello!", intent="greet")
        populated_fabric.send_message("vendor_tom", "Buy this!", intent="trade")
        assert len(received) == 2

    def test_message_to_group(self, populated_fabric):
        group = populated_fabric.start_group_conversation(
            "vendor_tom", ["guard_anna", "vendor_lisa"], location="market"
        )
        msg = populated_fabric.send_message(
            "vendor_tom", "Welcome everyone!", group_id=group.group_id
        )
        assert msg is not None
        assert len(group.messages) == 1


# ══════════════════════════════════════
# Group Conversation Tests
# ══════════════════════════════════════

class TestGroupConversations:
    def test_start_group(self, populated_fabric):
        group = populated_fabric.start_group_conversation(
            "vendor_tom", ["guard_anna", "vendor_lisa"],
            location="market", topic="trade_law"
        )
        assert group is not None
        assert group.topic == "trade_law"
        assert populated_fabric.active_group_count == 1
        assert "vendor_tom" in group.participants
        assert group.participants["vendor_tom"] == ConversationRole.INITIATOR

    def test_observers_added(self, populated_fabric):
        # Anna is at market but not a participant → should be added as observer
        group = populated_fabric.start_group_conversation(
            "vendor_tom", ["vendor_lisa"], location="market"
        )
        # Anna should be observer
        assert group.participants.get("guard_anna") == ConversationRole.OBSERVER

    def test_end_group(self, populated_fabric):
        group = populated_fabric.start_group_conversation(
            "vendor_tom", ["guard_anna"], location="market"
        )
        assert populated_fabric.end_group_conversation(group.group_id) is True
        assert group.active is False

    def test_end_nonexistent_group(self, fabric):
        assert fabric.end_group_conversation("fake") is False

    def test_participant_ids_exclude_observers(self, populated_fabric):
        group = populated_fabric.start_group_conversation(
            "vendor_tom", ["vendor_lisa"], location="market"
        )
        active = group.participant_ids
        assert "vendor_tom" in active
        assert "vendor_lisa" in active
        # Anna is observer, should NOT be in participant_ids
        assert "guard_anna" not in active

    def test_remove_participant(self, populated_fabric):
        group = populated_fabric.start_group_conversation(
            "vendor_tom", ["guard_anna", "vendor_lisa"], location="market"
        )
        group.remove_participant("guard_anna")
        assert "guard_anna" not in group.participants

    def test_remove_all_deactivates(self, fabric):
        fabric.register_npc("a", "A")
        fabric.register_npc("b", "B")
        group = fabric.start_group_conversation("a", ["b"])
        group.remove_participant("a")
        group.remove_participant("b")
        assert group.active is False

    def test_start_group_nonexistent_initiator(self, fabric):
        group = fabric.start_group_conversation("fake", ["also_fake"])
        assert group is None

    def test_start_group_no_valid_participants(self, fabric):
        fabric.register_npc("a", "A")
        group = fabric.start_group_conversation("a", ["nonexistent"])
        assert group is None

    def test_get_active_groups_by_location(self, populated_fabric):
        populated_fabric.start_group_conversation(
            "vendor_tom", ["guard_anna"], location="market"
        )
        populated_fabric.start_group_conversation(
            "bartender_joe", ["bartender_joe"], location="tavern"
        )
        market_groups = populated_fabric.get_active_groups(location="market")
        assert len(market_groups) == 1

    def test_get_npc_groups(self, populated_fabric):
        populated_fabric.start_group_conversation(
            "vendor_tom", ["guard_anna"], location="market"
        )
        groups = populated_fabric.get_npc_groups("vendor_tom")
        assert len(groups) == 1

    def test_group_capacity(self):
        fabric = SocialFabric(max_groups=2)
        fabric.register_npc("a", "A")
        fabric.register_npc("b", "B")
        g1 = fabric.start_group_conversation("a", ["b"])
        g2 = fabric.start_group_conversation("a", ["b"])
        # At capacity — next one should fail unless we end one
        g3 = fabric.start_group_conversation("a", ["b"])
        assert g3 is None  # No room

    def test_group_message_cap(self, populated_fabric):
        group = populated_fabric.start_group_conversation(
            "vendor_tom", ["guard_anna"], location="market", topic="test"
        )
        group.max_messages = 5
        for i in range(10):
            populated_fabric.send_message(
                "vendor_tom", f"Msg {i}", group_id=group.group_id
            )
        assert len(group.messages) == 5


# ══════════════════════════════════════
# Interaction Generation Tests
# ══════════════════════════════════════

class TestInteractionGeneration:
    def test_generate_friendly_interaction(self, populated_fabric):
        populated_fabric.set_disposition("vendor_tom", "vendor_lisa", 0.6)
        result = populated_fabric.generate_npc_interaction("vendor_tom", "vendor_lisa")
        assert result is not None
        assert result["allied"] is True
        assert result["tone"] in ("warm", "casual")

    def test_generate_hostile_interaction(self, populated_fabric):
        result = populated_fabric.generate_npc_interaction("guard_anna", "thief_shadow")
        assert result is not None
        assert result["hostile"] is True
        assert result["tone"] in ("aggressive", "guarded")

    def test_generate_neutral_interaction(self, populated_fabric):
        result = populated_fabric.generate_npc_interaction("bartender_joe", "guard_anna")
        assert result is not None
        assert result["interaction_type"] in ("neutral_exchange", "friendly_chat")

    def test_interaction_with_trade_topic(self, populated_fabric):
        result = populated_fabric.generate_npc_interaction("vendor_tom", "bartender_joe")
        assert result is not None
        assert "trade" in result["topics"]  # Tom is a merchant

    def test_interaction_nonexistent_npc(self, fabric):
        result = fabric.generate_npc_interaction("fake_a", "fake_b")
        assert result is None

    def test_interaction_with_gossip(self, populated_fabric):
        gossip = populated_fabric.create_gossip("vendor_tom", "Big sale!")
        populated_fabric.spread_gossip(gossip.gossip_id, "vendor_tom", "vendor_lisa")
        result = populated_fabric.generate_npc_interaction("vendor_tom", "vendor_lisa")
        assert result["shared_gossip_count"] >= 1

    def test_interaction_faction_business(self, populated_fabric):
        result = populated_fabric.generate_npc_interaction("vendor_tom", "vendor_lisa")
        assert "faction_business" in result["topics"]


# ══════════════════════════════════════
# World Tick Tests
# ══════════════════════════════════════

class TestWorldTick:
    def test_tick_runs(self, populated_fabric):
        result = populated_fabric.tick()
        assert "gossip_events" in result
        assert "interactions" in result
        assert result["elapsed_ms"] >= 0

    def test_tick_with_gossip(self, populated_fabric):
        populated_fabric.create_gossip(
            "vendor_tom", "Breaking news!",
            priority=GossipPriority.URGENT
        )
        result = populated_fabric.tick()
        # Should spread at market (Tom → Anna or Lisa)
        assert len(result["gossip_events"]) >= 1

    def test_tick_generates_interactions(self, populated_fabric):
        result = populated_fabric.tick()
        # Market has 3 NPCs, should generate at least 1 interaction
        assert len(result["interactions"]) >= 1

    def test_tick_specific_locations(self, populated_fabric):
        result = populated_fabric.tick(locations=["market"])
        assert result["locations_processed"] == 1

    def test_tick_empty_location(self, populated_fabric):
        result = populated_fabric.tick(locations=["empty_place"])
        assert len(result["gossip_events"]) == 0
        assert len(result["interactions"]) == 0

    def test_multiple_ticks(self, populated_fabric):
        populated_fabric.create_gossip("vendor_tom", "News!", priority=GossipPriority.URGENT)
        # First tick: Tom tells others at market
        r1 = populated_fabric.tick()
        # Second tick: those who heard can spread further (if they move)
        r2 = populated_fabric.tick()
        assert r1["elapsed_ms"] >= 0
        assert r2["elapsed_ms"] >= 0


# ══════════════════════════════════════
# Metrics & Reset Tests
# ══════════════════════════════════════

class TestMetrics:
    def test_metrics(self, populated_fabric):
        metrics = populated_fabric.get_metrics()
        assert metrics["registered_npcs"] == 5
        assert metrics["factions"] == 3
        assert metrics["active_gossip"] == 0

    def test_metrics_after_activity(self, populated_fabric):
        populated_fabric.create_gossip("vendor_tom", "News!")
        populated_fabric.send_message("vendor_tom", "Hi", target_id="guard_anna")
        metrics = populated_fabric.get_metrics()
        assert metrics["active_gossip"] == 1
        assert metrics["total_messages"] == 1

    def test_reset(self, populated_fabric):
        populated_fabric.create_gossip("vendor_tom", "News!")
        populated_fabric.reset()
        assert populated_fabric.npc_count == 0
        assert populated_fabric.faction_count == 0
        assert populated_fabric.gossip_count == 0
        metrics = populated_fabric.get_metrics()
        assert metrics["total_messages"] == 0


# ══════════════════════════════════════
# Edge Cases
# ══════════════════════════════════════

class TestEdgeCases:
    def test_npc_in_multiple_factions(self, fabric):
        fabric.create_faction("A", faction_id="a")
        fabric.create_faction("B", faction_id="b")
        fabric.register_npc("spy", "The Spy", faction_ids={"a", "b"})
        assert fabric.get_npc("spy").faction_ids == {"a", "b"}
        factions = fabric.get_npc_factions("spy")
        assert len(factions) == 2

    def test_self_disposition(self, fabric):
        fabric.register_npc("npc_1", "NPC")
        assert fabric.set_disposition("npc_1", "npc_1", 1.0) is True

    def test_gossip_nonexistent_source(self, fabric):
        gossip = fabric.create_gossip("nonexistent", "Phantom gossip")
        # Should still create the gossip, just no NPC tracking
        assert gossip is not None

    def test_concurrent_group_and_messages(self, populated_fabric):
        group = populated_fabric.start_group_conversation(
            "vendor_tom", ["guard_anna", "vendor_lisa"], location="market"
        )
        for i in range(5):
            populated_fabric.send_message(
                "vendor_tom", f"Group msg {i}", group_id=group.group_id
            )
        # Also send direct messages
        populated_fabric.send_message("guard_anna", "Side chat", target_id="vendor_lisa")
        metrics = populated_fabric.get_metrics()
        assert metrics["total_messages"] == 6

    def test_performance_100_npcs(self, fabric):
        """100 NPCs at same location should tick in <50ms."""
        for i in range(100):
            fabric.register_npc(f"npc_{i}", f"NPC {i}", location="arena")
        fabric.create_gossip("npc_0", "Arena event!", priority=GossipPriority.URGENT)
        start = time.time()
        result = fabric.tick()
        elapsed = (time.time() - start) * 1000
        assert elapsed < 50, f"Tick took {elapsed:.1f}ms, should be <50ms"
        assert result["locations_processed"] == 1
