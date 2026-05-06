"""
Synthesus 2.0 — Negotiation Engine Tests
Tests the shopping state machine independently (no server needed).
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cognitive.negotiation_engine import (
    NegotiationEngine, NegotiationState, HaggleResult,
    ItemListing, detect_haggle_intent,
)


# ── Test Inventory ──

SWORD = ItemListing(item_id="sword_01", name="Iron Sword", base_price=100, category="weapon")
POTION = ItemListing(item_id="potion_01", name="Health Potion", base_price=15, category="potion")
SHIELD = ItemListing(item_id="shield_01", name="Steel Shield", base_price=80, category="armor")
SECRET = ItemListing(
    item_id="secret_01", name="Starfire Essence", base_price=500,
    category="rare", restricted=True, trust_required=70,
)

TEST_INVENTORY = [SWORD, POTION, SHIELD, SECRET]


@pytest.fixture
def engine():
    return NegotiationEngine(
        npc_id="garen",
        npc_name="Garen Ironfoot",
        inventory=TEST_INVENTORY,
        merchant_style="fair",
    )


# ══════════════════════════════════════════════════
# 1. INTENT DETECTION
# ══════════════════════════════════════════════════

class TestIntentDetection:
    def test_browse_intent(self):
        intent, _ = detect_haggle_intent("Show me your wares")
        assert intent == "browse"

    def test_inquire_intent(self):
        intent, _ = detect_haggle_intent("How much is that sword?")
        assert intent == "inquire"

    def test_buy_intent(self):
        intent, _ = detect_haggle_intent("I want to buy a sword")
        assert intent == "buy"

    def test_haggle_intent(self):
        intent, _ = detect_haggle_intent("Can you lower the price?")
        assert intent == "haggle"

    def test_offer_with_amount(self):
        intent, amount = detect_haggle_intent("I'll pay 50 gold")
        assert intent == "offer"
        assert amount == 50

    def test_accept_intent(self):
        intent, _ = detect_haggle_intent("Deal! I'll take it")
        assert intent == "accept"

    def test_walkaway_intent(self):
        intent, _ = detect_haggle_intent("Forget it, too rich for my blood")
        assert intent == "walkaway"

    def test_sell_intent(self):
        intent, _ = detect_haggle_intent("I want to sell you something")
        assert intent == "sell"

    def test_no_intent(self):
        intent, _ = detect_haggle_intent("Tell me about yourself")
        assert intent == "none"

    def test_amount_extraction(self):
        _, amount = detect_haggle_intent("Would you take 75 gold?")
        assert amount == 75


# ══════════════════════════════════════════════════
# 2. STATE TRANSITIONS
# ══════════════════════════════════════════════════

class TestStateTransitions:
    def test_idle_to_browsing(self, engine):
        result = engine.process("Show me your wares", "player1")
        assert result["handled"]
        assert result["state"] == "browsing"

    def test_idle_to_inquiring(self, engine):
        result = engine.process("How much is the Iron Sword?", "player1")
        assert result["handled"]
        assert result["state"] == "inquiring"
        assert result["item"] == "Iron Sword"
        assert result["price"] > 0

    def test_inquire_then_buy(self, engine):
        engine.process("How much is the Iron Sword?", "player1")
        result = engine.process("I want to buy it", "player1")
        assert result["handled"]
        assert result["state"] == "negotiating"

    def test_direct_buy(self, engine):
        result = engine.process("I want to buy a Health Potion", "player1")
        assert result["handled"]
        assert result["state"] == "negotiating"
        assert result["item"] == "Health Potion"

    def test_haggle_flow(self, engine):
        engine.process("I want to buy the Iron Sword", "player1")
        result = engine.process("That's too expensive, how about 70 gold?", "player1")
        assert result["handled"]
        assert result["haggle_result"] in ("counter", "accepted", "final_offer")

    def test_accept_deal(self, engine):
        engine.process("I want to buy a Health Potion", "player1")
        result = engine.process("Deal, I'll take it", "player1")
        assert result["state"] == "deal"
        assert result["transaction"]
        assert result["transaction"]["item"] == "Health Potion"

    def test_walkaway(self, engine):
        engine.process("I want to buy the Iron Sword", "player1")
        result = engine.process("Forget it, never mind", "player1")
        assert result["state"] == "walkaway"


# ══════════════════════════════════════════════════
# 3. HAGGLING MECHANICS
# ══════════════════════════════════════════════════

class TestHagglingMechanics:
    def test_insulting_offer_rejected(self, engine):
        engine.process("Buy Iron Sword", "player1")
        result = engine.process("I'll give you 10 gold", "player1")
        assert result["haggle_result"] == "insulted"

    def test_fair_offer_countered(self, engine):
        engine.process("Buy Iron Sword", "player1")
        result = engine.process("How about 80 gold?", "player1")
        assert result["haggle_result"] in ("counter", "accepted")
        if result["haggle_result"] == "counter":
            assert result["price"] < 100  # Counter should be lower than asking

    def test_full_price_accepted(self, engine):
        engine.process("Buy Iron Sword", "player1")
        asking = engine._get_session("player1").asking_price
        result = engine.process(f"I'll pay {asking} gold", "player1")
        assert result["haggle_result"] == "accepted"

    def test_max_haggle_rounds(self, engine):
        engine.process("Buy Iron Sword", "player1")
        for i in range(4):
            result = engine.process("Can you go lower?", "player1")
        # After max rounds, should get final offer
        assert result["haggle_result"] == "final_offer"

    def test_trust_affects_price(self, engine):
        price_low_trust = engine._calculate_asking_price(SWORD, trust=30)
        price_high_trust = engine._calculate_asking_price(SWORD, trust=80)
        assert price_high_trust < price_low_trust


# ══════════════════════════════════════════════════
# 4. RESTRICTED ITEMS
# ══════════════════════════════════════════════════

class TestRestrictedItems:
    def test_restricted_item_low_trust(self, engine):
        result = engine.process("Buy Starfire Essence", "player1", trust=40)
        assert result["response"] == "trust_too_low"

    def test_restricted_item_high_trust(self, engine):
        result = engine.process("Buy Starfire Essence", "player1", trust=80)
        assert result["state"] == "negotiating"
        assert result["item"] == "Starfire Essence"


# ══════════════════════════════════════════════════
# 5. MERCHANT STYLES
# ══════════════════════════════════════════════════

class TestMerchantStyles:
    def test_shrewd_higher_prices(self):
        shrewd = NegotiationEngine("npc", "NPC", TEST_INVENTORY, merchant_style="shrewd")
        fair = NegotiationEngine("npc", "NPC", TEST_INVENTORY, merchant_style="fair")
        shrewd_price = shrewd._calculate_asking_price(SWORD)
        fair_price = fair._calculate_asking_price(SWORD)
        assert shrewd_price > fair_price

    def test_generous_lower_prices(self):
        generous = NegotiationEngine("npc", "NPC", TEST_INVENTORY, merchant_style="generous")
        fair = NegotiationEngine("npc", "NPC", TEST_INVENTORY, merchant_style="fair")
        gen_price = generous._calculate_asking_price(SWORD)
        fair_price = fair._calculate_asking_price(SWORD)
        assert gen_price < fair_price


# ══════════════════════════════════════════════════
# 6. SESSION MANAGEMENT
# ══════════════════════════════════════════════════

class TestSessionManagement:
    def test_separate_player_sessions(self, engine):
        engine.process("Buy Iron Sword", "player1")
        engine.process("Buy Health Potion", "player2")
        s1 = engine.get_session_info("player1")
        s2 = engine.get_session_info("player2")
        assert s1["item"] == "Iron Sword"
        assert s2["item"] == "Health Potion"

    def test_session_stats(self, engine):
        engine.process("Buy Iron Sword", "player1")
        engine.process("Deal", "player1")
        stats = engine.get_stats()
        assert stats["total_transactions"] == 1
        assert stats["active_sessions"] >= 1

    def test_nonexistent_player_session(self, engine):
        info = engine.get_session_info("nobody")
        assert info["state"] == "idle"
        assert info["active"] is False
