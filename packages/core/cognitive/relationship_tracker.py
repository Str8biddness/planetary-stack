"""
Module 4: Relationship Tracker
"The NPC remembers YOU across sessions"

Tracks the NPC's relationship with each player as numeric scores:
trust, fondness, respect, debt. Scores unlock/lock response tiers.

Cost: ~0.05ms per query, 16 bytes per relationship
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class Relationship:
    """Per-player relationship scores."""
    trust: float = 50.0       # 0-100: does the NPC believe the player?
    fondness: float = 50.0    # 0-100: does the NPC like the player?
    respect: float = 50.0     # 0-100: does the NPC take the player seriously?
    debt: float = 0.0         # -100 to 100: NPC owes player (positive) or vice versa
    interactions: int = 0
    first_met: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    nickname: Optional[str] = None  # Earned at high fondness
    titles: List[str] = field(default_factory=list)  # Earned through deeds

    def clamp(self):
        """Keep scores in valid ranges."""
        self.trust = max(0, min(100, self.trust))
        self.fondness = max(0, min(100, self.fondness))
        self.respect = max(0, min(100, self.respect))
        self.debt = max(-100, min(100, self.debt))


# Relationship events and their score impacts
@dataclass
class RelationshipEvent:
    """A named event that modifies relationship scores."""
    name: str
    trust_delta: float = 0
    fondness_delta: float = 0
    respect_delta: float = 0
    debt_delta: float = 0


# Default events — game systems call these by name
DEFAULT_EVENTS: Dict[str, RelationshipEvent] = {
    # Positive
    "quest_completed":     RelationshipEvent("quest_completed", trust_delta=20, fondness_delta=10, respect_delta=15, debt_delta=30),
    "quest_failed":        RelationshipEvent("quest_failed", trust_delta=-10, fondness_delta=-5, respect_delta=-10, debt_delta=-20),
    "purchase":            RelationshipEvent("purchase", trust_delta=2, fondness_delta=5, debt_delta=-5),
    "large_purchase":      RelationshipEvent("large_purchase", trust_delta=5, fondness_delta=10, respect_delta=5, debt_delta=-15),
    "gave_gift":           RelationshipEvent("gave_gift", fondness_delta=15, trust_delta=5, debt_delta=10),
    "saved_life":          RelationshipEvent("saved_life", trust_delta=30, fondness_delta=25, respect_delta=20, debt_delta=50),
    "shared_secret":       RelationshipEvent("shared_secret", trust_delta=10, fondness_delta=5),
    "defended_npc":        RelationshipEvent("defended_npc", trust_delta=15, fondness_delta=20, respect_delta=10, debt_delta=20),
    "good_conversation":   RelationshipEvent("good_conversation", fondness_delta=3, trust_delta=2),
    "returned_item":       RelationshipEvent("returned_item", trust_delta=15, fondness_delta=5, respect_delta=10),

    # Negative
    "threatened":          RelationshipEvent("threatened", trust_delta=-30, fondness_delta=-20, respect_delta=5),
    "lied":                RelationshipEvent("lied", trust_delta=-25, fondness_delta=-15, respect_delta=-10),
    "stole":               RelationshipEvent("stole", trust_delta=-40, fondness_delta=-30, respect_delta=-20, debt_delta=-30),
    "insulted":            RelationshipEvent("insulted", fondness_delta=-15, trust_delta=-5, respect_delta=-5),
    "haggled_hard":        RelationshipEvent("haggled_hard", fondness_delta=-5, respect_delta=5),
    "broke_promise":       RelationshipEvent("broke_promise", trust_delta=-35, fondness_delta=-20, respect_delta=-15),
    "attacked":            RelationshipEvent("attacked", trust_delta=-50, fondness_delta=-50, respect_delta=-10, debt_delta=-50),
    "ignored_request":     RelationshipEvent("ignored_request", fondness_delta=-5, trust_delta=-5),
}


# Response tiers based on relationship levels
class ResponseTier:
    """Defines what content/behavior is unlocked at each relationship level."""

    @staticmethod
    def get_tier(rel: Relationship) -> Dict[str, bool]:
        """Return a dict of unlocked capabilities based on scores."""
        return {
            # Trust-gated
            "shares_rumors":        rel.trust > 30,
            "offers_quests":        rel.trust > 40,
            "shares_secrets":       rel.trust > 60,
            "trusts_with_credit":   rel.trust > 75,
            "reveals_hidden_stock": rel.trust > 80,

            # Fondness-gated
            "uses_friendly_tone":   rel.fondness > 40,
            "uses_nickname":        rel.fondness > 70 and rel.nickname is not None,
            "gives_free_items":     rel.fondness > 80,
            "shares_personal_stories": rel.fondness > 60,

            # Respect-gated
            "better_prices":        rel.respect > 50,
            "honest_appraisals":    rel.respect > 40,
            "serious_conversation": rel.respect > 60,
            "defers_to_player":     rel.respect > 80,

            # Debt-gated
            "npc_owes_favor":       rel.debt > 30,
            "npc_offers_help":      rel.debt > 50,
            "player_owes_npc":      rel.debt < -30,

            # Negative gates
            "refuses_service":      rel.trust < 10 or rel.fondness < 10,
            "hostile":              rel.trust < 5 and rel.fondness < 15,
            "warns_away":           rel.trust < 20 and rel.respect < 20,
        }


class RelationshipTracker:
    """
    Module 4 of the Cognitive Engine.
    Tracks NPC-player relationships with persistent scores.
    """

    def __init__(
        self,
        npc_id: str,
        custom_events: Optional[Dict[str, RelationshipEvent]] = None,
        persist_path: Optional[str] = None,
    ):
        self.npc_id = npc_id
        self._events = {**DEFAULT_EVENTS, **(custom_events or {})}
        self._relationships: Dict[str, Relationship] = {}
        self._persist_path = Path(persist_path) if persist_path else None

        # Load persisted relationships
        if self._persist_path and self._persist_path.exists():
            self._load()

    def _get_rel(self, player_id: str) -> Relationship:
        if player_id not in self._relationships:
            self._relationships[player_id] = Relationship()
        return self._relationships[player_id]

    def process(self, player_id: str, keywords: set) -> Dict:
        """
        Process player keywords for implicit relationship signals.
        Also returns current relationship info for other modules.

        Returns:
        {
            "trust": float,
            "fondness": float,
            "respect": float,
            "debt": float,
            "tier": dict of unlocked capabilities,
            "interactions": int,
            "is_first_meeting": bool,
        }
        """
        rel = self._get_rel(player_id)
        rel.interactions += 1
        rel.last_seen = time.time()

        # Implicit signals from conversation keywords
        positive_words = {"thank", "thanks", "appreciate", "great", "love",
                          "wonderful", "perfect", "amazing", "friend",
                          "honest", "respect", "nice", "admire", "kind",
                          "impressive", "brilliant", "incredible", "generous"}
        negative_words = {"terrible", "awful", "cheat", "liar", "steal",
                          "overpriced", "scam", "ripoff", "hate", "worst"}
        threat_words = {"kill", "attack", "destroy", "burn", "die",
                        "hurt", "weapon", "fight", "regret"}

        positive = len(keywords & positive_words)
        negative = len(keywords & negative_words)
        threatening = len(keywords & threat_words)

        if positive > 0:
            self.apply_event(player_id, "good_conversation")
        if negative > 0:
            self.apply_event(player_id, "insulted")
        if threatening > 0:
            self.apply_event(player_id, "threatened")

        tier = ResponseTier.get_tier(rel)

        return {
            "trust": rel.trust,
            "fondness": rel.fondness,
            "respect": rel.respect,
            "debt": rel.debt,
            "tier": tier,
            "interactions": rel.interactions,
            "is_first_meeting": rel.interactions <= 1,
            "nickname": rel.nickname,
        }

    def apply_event(self, player_id: str, event_name: str) -> Optional[Relationship]:
        """Apply a named relationship event."""
        event = self._events.get(event_name)
        if not event:
            return None

        rel = self._get_rel(player_id)
        rel.trust += event.trust_delta
        rel.fondness += event.fondness_delta
        rel.respect += event.respect_delta
        rel.debt += event.debt_delta
        rel.clamp()

        # Auto-assign nickname at high fondness
        if rel.fondness > 70 and rel.nickname is None:
            rel.nickname = "friend"  # Default; character config can override

        # Persist after events
        if self._persist_path:
            self._save()

        return rel

    def get_relationship(self, player_id: str) -> Relationship:
        """Get relationship for debugging."""
        return self._get_rel(player_id)

    def set_nickname(self, player_id: str, nickname: str):
        """Set a custom nickname for a player."""
        self._get_rel(player_id).nickname = nickname

    def add_title(self, player_id: str, title: str):
        """Award a title to a player."""
        rel = self._get_rel(player_id)
        if title not in rel.titles:
            rel.titles.append(title)

    def _save(self):
        """Persist relationships to disk."""
        if not self._persist_path:
            return
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        for pid, rel in self._relationships.items():
            data[pid] = asdict(rel)
        self._persist_path.write_text(json.dumps(data, indent=2))

    def _load(self):
        """Load relationships from disk."""
        if not self._persist_path or not self._persist_path.exists():
            return
        try:
            data = json.loads(self._persist_path.read_text())
            for pid, rel_data in data.items():
                self._relationships[pid] = Relationship(**rel_data)
        except (json.JSONDecodeError, TypeError):
            pass
