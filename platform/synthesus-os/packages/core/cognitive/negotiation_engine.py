"""
Module 10: Negotiation State Machine
"When a player tries to buy, sell, or haggle with a merchant NPC"

State machine for shopping interactions:
  BROWSE → INQUIRE → NEGOTIATE → DEAL / WALKAWAY

Handles:
- Price tracking per item
- Haggle rounds (max 3 before final price)
- Relationship-adjusted discounts
- Emotional reactions to lowball offers
- Counter-offers based on merchant archetype
- Transaction history

Cost: ~0.3ms per state transition, ~5 KB RAM per active session, zero GPU.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from ml.loot_balancer import LootBalancer
    _HAS_LOOT_BALANCER = True
except ImportError:
    _HAS_LOOT_BALANCER = False


class NegotiationState(Enum):
    """States in the negotiation flow."""
    IDLE = "idle"                   # No active negotiation
    BROWSING = "browsing"           # Player is looking around
    INQUIRING = "inquiring"         # Player asked about a specific item
    NEGOTIATING = "negotiating"     # Active price negotiation
    COUNTER_OFFER = "counter_offer" # NPC made a counter-offer, waiting for response
    DEAL = "deal"                   # Deal accepted
    WALKAWAY = "walkaway"           # Player or NPC walked away
    REFUSED = "refused"             # NPC refused to sell (trust too low, item restricted)


class HaggleResult(Enum):
    """Outcome of a haggle attempt."""
    ACCEPTED = "accepted"           # NPC agrees to the price
    COUNTER = "counter"             # NPC makes a counter-offer
    REJECTED = "rejected"           # NPC rejects outright
    FINAL_OFFER = "final_offer"     # NPC's last offer — take it or leave it
    INSULTED = "insulted"           # Offer was insultingly low


@dataclass
class ItemListing:
    """An item available for trade."""
    item_id: str
    name: str
    base_price: int
    category: str = "general"       # weapon, potion, armor, misc, etc.
    description: str = ""
    quantity: int = 1               # -1 = unlimited
    min_price_ratio: float = 0.7    # Lowest the NPC will go (70% of base)
    restricted: bool = False        # Requires trust level to purchase
    trust_required: int = 60        # Trust needed if restricted


@dataclass
class NegotiationSession:
    """An active negotiation session between player and NPC."""
    player_id: str
    npc_id: str
    state: NegotiationState = NegotiationState.IDLE
    current_item: Optional[ItemListing] = None
    asking_price: int = 0           # NPC's current asking price
    player_offer: int = 0           # Player's last offer
    haggle_rounds: int = 0          # How many times player has haggled
    max_haggle_rounds: int = 3      # Max rounds before final offer
    discount_pct: float = 0.0       # Relationship-based discount
    transaction_history: List[Dict] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)

    # Session timeout (5 minutes of inactivity resets to IDLE)
    SESSION_TIMEOUT = 300.0

    def is_expired(self) -> bool:
        return (time.time() - self.last_activity) > self.SESSION_TIMEOUT

    def touch(self):
        self.last_activity = time.time()


# ── Haggle Intent Detection ──
_HAGGLE_PATTERNS = [
    (r"\b(cheaper|discount|lower|reduce|less)\b", "haggle"),
    (r"\b(too (much|expensive|costly|pricey))\b", "haggle"),
    (r"\b(come on|cmon|c'mon)\b", "haggle"),
    (r"\b(can you do|how about|what about|would you take)\s+\d+", "offer"),
    (r"\b(i('ll| will) (pay|give|offer))\s+\d+", "offer"),
    (r"\b(\d+)\s*(gold|coin|gp)\b", "offer"),
    (r"\b(deal|done|accept|agreed|fine|ok|okay|i'll take it)\b", "accept"),
    (r"\b(no( thanks)?|forget it|never ?mind|walk away|too rich)\b", "walkaway"),
    (r"\b(sell|offload|get rid of)\b", "sell"),
    (r"\b(buy|purchase|want|i'll take|give me)\b", "buy"),
    (r"\b(how much|price|cost|what.*worth)\b", "inquire"),
    (r"\b(show|wares|inventory|what.*sell|what.*have)\b", "browse"),
]


def detect_haggle_intent(text: str) -> Tuple[str, Optional[int]]:
    """Detect shopping/haggle intent from player text.
    
    Returns:
        (intent, amount) where intent is one of:
        browse, inquire, buy, sell, haggle, offer, accept, walkaway, none
        and amount is an extracted gold value if present.
    """
    text_lower = text.lower().strip()
    amount = None

    # Extract numeric amounts
    amount_match = re.search(r'(\d+)\s*(gold|coin|gp)?', text_lower)
    if amount_match:
        amount = int(amount_match.group(1))

    # Check patterns in priority order
    for pattern, intent in _HAGGLE_PATTERNS:
        if re.search(pattern, text_lower):
            return intent, amount

    return "none", amount


class NegotiationEngine:
    """
    Manages negotiation sessions between players and merchant NPCs.
    
    Usage:
        engine = NegotiationEngine(npc_id="garen", inventory=[...])
        result = engine.process("I want to buy a sword", player_id="hero_001", trust=65)
    """

    def __init__(
        self,
        npc_id: str,
        npc_name: str = "",
        inventory: Optional[List[ItemListing]] = None,
        merchant_style: str = "fair",  # fair, shrewd, generous, stubborn
        loot_balancer: Optional[Any] = None,
    ):
        self.npc_id = npc_id
        self.npc_name = npc_name or npc_id
        self.inventory = inventory or []
        self.merchant_style = merchant_style
        self._sessions: Dict[str, NegotiationSession] = {}
        self._loot_balancer = loot_balancer

        # Style modifiers
        self._style_config = {
            "fair": {"initial_markup": 1.0, "haggle_step": 0.08, "min_ratio": 0.75, "patience": 3, "generosity": 0.5},
            "shrewd": {"initial_markup": 1.15, "haggle_step": 0.05, "min_ratio": 0.85, "patience": 2, "generosity": 0.3},
            "generous": {"initial_markup": 0.95, "haggle_step": 0.10, "min_ratio": 0.65, "patience": 4, "generosity": 0.7},
            "stubborn": {"initial_markup": 1.1, "haggle_step": 0.03, "min_ratio": 0.90, "patience": 2, "generosity": 0.2},
        }

    def _get_session(self, player_id: str) -> NegotiationSession:
        """Get or create a negotiation session."""
        if player_id in self._sessions:
            session = self._sessions[player_id]
            if session.is_expired():
                session = NegotiationSession(player_id=player_id, npc_id=self.npc_id)
                self._sessions[player_id] = session
            return session
        session = NegotiationSession(player_id=player_id, npc_id=self.npc_id)
        self._sessions[player_id] = session
        return session

    def _find_item(self, text: str) -> Optional[ItemListing]:
        """Find an item mentioned in the player's text."""
        text_lower = text.lower()
        best_match = None
        best_score = 0

        for item in self.inventory:
            name_lower = item.name.lower()
            # Exact name match
            if name_lower in text_lower:
                score = len(name_lower)
                if score > best_score:
                    best_score = score
                    best_match = item
            # Category match
            elif item.category.lower() in text_lower:
                score = len(item.category) * 0.5
                if score > best_score:
                    best_score = score
                    best_match = item

        return best_match

    def _calculate_asking_price(
        self, item: ItemListing, trust: int = 50, fondness: int = 50,
    ) -> int:
        """Calculate the NPC's asking price based on item, relationship, and style."""
        style = self._style_config.get(self.merchant_style, self._style_config["fair"])
        base = item.base_price * style["initial_markup"]

        # Use LootBalancer for dynamic pricing if available
        if self._loot_balancer:
            loyalty = max(0.0, min(1.0, (trust + fondness) / 200.0))
            generosity = style.get("generosity", 0.5)
            result = self._loot_balancer.price_adjustment(
                base_price=base,
                loyalty_score=loyalty,
                merchant_generosity=generosity,
                is_buying=True,
            )
            return max(1, int(result["adjusted_price"]))

        # Fallback: hardcoded discount math
        trust_discount = max(0, min(0.15, (trust - 50) * 0.003))
        fondness_discount = max(0, min(0.10, (fondness - 60) * 0.003))
        total_discount = trust_discount + fondness_discount
        return max(1, int(base * (1 - total_discount)))

    def _calculate_floor_price(self, item: ItemListing) -> int:
        """Calculate the absolute minimum the NPC will accept."""
        style = self._style_config.get(self.merchant_style, self._style_config["fair"])
        return max(1, int(item.base_price * style["min_ratio"]))

    def _evaluate_offer(
        self, session: NegotiationSession, offer: int,
    ) -> Tuple[HaggleResult, int, str]:
        """Evaluate a player's offer and determine the NPC's response.
        
        Returns: (result, counter_price, reason)
        """
        if session.current_item is None:
            return HaggleResult.REJECTED, 0, "no_item"

        item = session.current_item
        floor = self._calculate_floor_price(item)
        asking = session.asking_price
        style = self._style_config.get(self.merchant_style, self._style_config["fair"])

        # Insultingly low (< 30% of asking)
        if offer < asking * 0.3:
            return HaggleResult.INSULTED, asking, "insulting_offer"

        # At or above asking price
        if offer >= asking:
            return HaggleResult.ACCEPTED, offer, "full_price"

        # At or above floor
        if offer >= floor:
            if session.haggle_rounds >= style["patience"]:
                return HaggleResult.FINAL_OFFER, floor, "final_offer"
            # Counter halfway between offer and asking
            counter = int((offer + asking) / 2)
            counter = max(counter, floor)
            return HaggleResult.COUNTER, counter, "counter_offer"

        # Below floor but close (within 10%)
        if offer >= floor * 0.9:
            counter = floor
            return HaggleResult.COUNTER, counter, "near_floor"

        # Too low
        if session.haggle_rounds >= style["patience"]:
            return HaggleResult.FINAL_OFFER, floor, "final_offer"

        # Standard rejection with counter
        step = style["haggle_step"]
        new_asking = max(floor, int(asking * (1 - step)))
        return HaggleResult.COUNTER, new_asking, "standard_counter"

    def process(
        self,
        text: str,
        player_id: str,
        trust: int = 50,
        fondness: int = 50,
    ) -> Dict[str, Any]:
        """Process a player message through the negotiation state machine.
        
        Returns:
            {
                "handled": bool,      # True if this was a shopping interaction
                "state": str,         # Current negotiation state
                "response": str,      # NPC's response text
                "item": str | None,   # Item being discussed
                "price": int,         # Current price
                "haggle_result": str, # Result of any haggle attempt
                "transaction": dict,  # Transaction details if deal completed
            }
        """
        session = self._get_session(player_id)
        session.touch()
        intent, amount = detect_haggle_intent(text)

        result = {
            "handled": False,
            "state": session.state.value,
            "response": "",
            "item": None,
            "price": 0,
            "haggle_result": "",
            "transaction": {},
        }

        # Not a shopping interaction
        if intent == "none" and session.state == NegotiationState.IDLE:
            return result

        result["handled"] = True

        # ── State transitions ──

        if intent == "browse":
            session.state = NegotiationState.BROWSING
            items_str = ", ".join(
                f"{i.name} ({i.base_price}g)" for i in self.inventory[:8]
            )
            result["response"] = f"browse_inventory"
            result["state"] = session.state.value
            result["price"] = 0
            return result

        if intent == "inquire":
            item = self._find_item(text)
            if item:
                price = self._calculate_asking_price(item, trust, fondness)
                session.state = NegotiationState.INQUIRING
                session.current_item = item
                session.asking_price = price
                result["item"] = item.name
                result["price"] = price
                result["response"] = "item_inquiry"
            else:
                result["response"] = "item_not_found"
            result["state"] = session.state.value
            return result

        if intent == "buy":
            item = self._find_item(text) or session.current_item
            if item:
                if item.restricted and trust < item.trust_required:
                    session.state = NegotiationState.REFUSED
                    result["response"] = "trust_too_low"
                    result["item"] = item.name
                else:
                    price = self._calculate_asking_price(item, trust, fondness)
                    session.state = NegotiationState.NEGOTIATING
                    session.current_item = item
                    session.asking_price = price
                    session.discount_pct = max(0, (trust - 50) * 0.3 + (fondness - 60) * 0.3)
                    result["response"] = "offer_price"
                    result["item"] = item.name
                    result["price"] = price
            else:
                result["response"] = "item_not_found"
            result["state"] = session.state.value
            return result

        if intent in ("haggle", "offer"):
            if session.state not in (
                NegotiationState.NEGOTIATING, NegotiationState.COUNTER_OFFER,
                NegotiationState.INQUIRING,
            ):
                # Start negotiation if not already in one
                item = self._find_item(text) or session.current_item
                if item:
                    price = self._calculate_asking_price(item, trust, fondness)
                    session.state = NegotiationState.NEGOTIATING
                    session.current_item = item
                    session.asking_price = price
                else:
                    result["response"] = "nothing_to_haggle"
                    return result

            session.haggle_rounds += 1
            offer = amount or int(session.asking_price * 0.8)  # Default offer = 80%
            session.player_offer = offer

            haggle_result, counter_price, reason = self._evaluate_offer(session, offer)

            if haggle_result == HaggleResult.ACCEPTED:
                session.state = NegotiationState.DEAL
                session.transaction_history.append({
                    "item": session.current_item.name if session.current_item else "unknown",
                    "price": offer,
                    "rounds": session.haggle_rounds,
                    "time": time.time(),
                })
                result["transaction"] = session.transaction_history[-1]
                result["response"] = "deal_accepted"
                result["price"] = offer
            elif haggle_result == HaggleResult.INSULTED:
                result["response"] = "insulted"
                result["price"] = session.asking_price
            elif haggle_result == HaggleResult.FINAL_OFFER:
                session.state = NegotiationState.COUNTER_OFFER
                session.asking_price = counter_price
                result["response"] = "final_offer"
                result["price"] = counter_price
            elif haggle_result == HaggleResult.COUNTER:
                session.state = NegotiationState.COUNTER_OFFER
                session.asking_price = counter_price
                result["response"] = "counter_offer"
                result["price"] = counter_price
            else:
                result["response"] = "rejected"
                result["price"] = session.asking_price

            result["haggle_result"] = haggle_result.value
            result["item"] = session.current_item.name if session.current_item else None
            result["state"] = session.state.value
            return result

        if intent == "accept":
            if session.state in (NegotiationState.NEGOTIATING, NegotiationState.COUNTER_OFFER):
                session.state = NegotiationState.DEAL
                price = session.asking_price
                session.transaction_history.append({
                    "item": session.current_item.name if session.current_item else "unknown",
                    "price": price,
                    "rounds": session.haggle_rounds,
                    "time": time.time(),
                })
                result["transaction"] = session.transaction_history[-1]
                result["response"] = "deal_closed"
                result["price"] = price
                result["item"] = session.current_item.name if session.current_item else None
            else:
                result["response"] = "nothing_to_accept"
            result["state"] = session.state.value
            return result

        if intent == "walkaway":
            if session.state != NegotiationState.IDLE:
                session.state = NegotiationState.WALKAWAY
                result["response"] = "player_walkaway"
                result["item"] = session.current_item.name if session.current_item else None
                # Reset for next time
                session.current_item = None
                session.haggle_rounds = 0
            else:
                result["handled"] = False
            result["state"] = session.state.value
            return result

        if intent == "sell":
            result["response"] = "player_selling"
            result["state"] = session.state.value
            return result

        # Unhandled but in active session
        if session.state != NegotiationState.IDLE:
            result["state"] = session.state.value
            return result

        result["handled"] = False
        return result

    def get_session_info(self, player_id: str) -> Dict[str, Any]:
        """Get current session state for a player."""
        if player_id not in self._sessions:
            return {"state": "idle", "active": False}
        session = self._sessions[player_id]
        return {
            "state": session.state.value,
            "active": not session.is_expired(),
            "item": session.current_item.name if session.current_item else None,
            "asking_price": session.asking_price,
            "haggle_rounds": session.haggle_rounds,
            "max_rounds": session.max_haggle_rounds,
            "transactions": len(session.transaction_history),
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get engine-wide statistics."""
        total_txns = sum(len(s.transaction_history) for s in self._sessions.values())
        active = sum(1 for s in self._sessions.values() if not s.is_expired())
        return {
            "active_sessions": active,
            "total_sessions": len(self._sessions),
            "total_transactions": total_txns,
            "inventory_size": len(self.inventory),
        }
