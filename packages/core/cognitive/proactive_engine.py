"""
Module 15: Proactive Engine — NPC-Initiated Interactions
AIVM Synthesus 2.0

Enables NPCs to initiate greetings and conversation starters based on
contextual triggers, instead of passively waiting for player input.

Trigger Types:
  TIME_BASED         — "It's been a while since your last visit"
  EVENT_BASED        — "Have you heard? The trade routes were disrupted!"
  RELATIONSHIP_BASED — "I consider you a friend now"
  WORLD_STATE        — "Careful, I hear there's a storm coming"

Triggers are checked at the start of each query. If one fires, its message
becomes a greeting prefix that the NPC delivers before answering the
player's actual question.

Cost: <0.1ms per query (pure dict lookups + time checks), zero GPU.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TriggerType(Enum):
    """Categories of proactive triggers."""
    TIME_BASED = "time_based"
    EVENT_BASED = "event_based"
    RELATIONSHIP_BASED = "relationship_based"
    WORLD_STATE = "world_state"
    LORE_VOLUNTEER = "lore_volunteer"


@dataclass
class ProactiveTrigger:
    """A single proactive conversation trigger."""
    trigger_id: str
    trigger_type: TriggerType
    message: str                              # What the NPC says proactively
    condition: Dict[str, Any] = field(default_factory=dict)
    cooldown_seconds: float = 300.0           # Min seconds between fires
    last_fired: float = 0.0
    fire_count: int = 0
    max_fires: int = -1                       # -1 = unlimited
    active: bool = True
    priority: float = 0.5                     # 0-1, higher wins ties

    def is_ready(self) -> bool:
        """Check if this trigger can fire."""
        if not self.active:
            return False
        if self.max_fires > 0 and self.fire_count >= self.max_fires:
            return False
        if (time.time() - self.last_fired) < self.cooldown_seconds:
            return False
        return True


class ProactiveEngine:
    """
    Checks for proactive triggers at the start of each conversation turn.
    If a trigger fires, it returns a greeting override that the NPC delivers
    before processing the player's actual query.

    Usage:
        engine = ProactiveEngine()
        engine.add_trigger(ProactiveTrigger(
            trigger_id="long_absence",
            trigger_type=TriggerType.TIME_BASED,
            message="Well, well! It's been quite some time. I was starting to wonder if you'd forgotten about me.",
            condition={"min_absence_seconds": 3600},
        ))

        # At start of query processing:
        greeting = engine.check(player_id="hero_001", context={...})
        if greeting:
            response = f"{greeting} {original_response}"
    """

    def __init__(self):
        self._triggers: Dict[str, ProactiveTrigger] = {}
        self._player_last_seen: Dict[str, float] = {}
        self._player_visit_count: Dict[str, int] = {}
        self._notified_events: Dict[str, set] = {}  # player_id → set of event_ids told about
        self._total_checks: int = 0
        self._total_fires: int = 0

    def add_trigger(self, trigger: ProactiveTrigger) -> None:
        """Register a proactive trigger."""
        self._triggers[trigger.trigger_id] = trigger

    def remove_trigger(self, trigger_id: str) -> bool:
        """Remove a trigger."""
        if trigger_id in self._triggers:
            del self._triggers[trigger_id]
            return True
        return False

    def check(
        self,
        player_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        Check all triggers and return a greeting override if any fires.

        Context should include:
          - world_flags: dict of current world state flags
          - relationship: dict with trust/fondness/respect/tier
          - last_interaction_time: float (epoch) of last conversation
          - active_events: list of current world event dicts

        Returns the proactive message string, or None.
        """
        self._total_checks += 1
        context = context or {}

        # Track player visit
        now = time.time()
        last_seen = self._player_last_seen.get(player_id, 0.0)
        self._player_last_seen[player_id] = now
        self._player_visit_count[player_id] = self._player_visit_count.get(player_id, 0) + 1

        if player_id not in self._notified_events:
            self._notified_events[player_id] = set()

        # Evaluate triggers
        candidates = []
        for trigger in self._triggers.values():
            if not trigger.is_ready():
                continue

            fired = self._evaluate_trigger(
                trigger, player_id, last_seen, now, context
            )
            if fired:
                candidates.append(trigger)

        if not candidates:
            return None

        # Pick highest priority
        candidates.sort(key=lambda t: t.priority, reverse=True)
        winner = candidates[0]

        # Mark as fired
        winner.last_fired = now
        winner.fire_count += 1
        self._total_fires += 1

        if winner.max_fires > 0 and winner.fire_count >= winner.max_fires:
            winner.active = False
            logger.info(f"ProactiveEngine: trigger '{winner.trigger_id}' retired (max fires)")

        logger.debug(
            f"ProactiveEngine: fired '{winner.trigger_id}' for player '{player_id}'"
        )
        return winner.message

    def _evaluate_trigger(
        self,
        trigger: ProactiveTrigger,
        player_id: str,
        last_seen: float,
        now: float,
        context: Dict[str, Any],
    ) -> bool:
        """Evaluate whether a specific trigger should fire."""

        if trigger.trigger_type == TriggerType.TIME_BASED:
            return self._check_time_trigger(trigger, last_seen, now)

        elif trigger.trigger_type == TriggerType.EVENT_BASED:
            return self._check_event_trigger(trigger, player_id, context)

        elif trigger.trigger_type == TriggerType.RELATIONSHIP_BASED:
            return self._check_relationship_trigger(trigger, context)

        elif trigger.trigger_type == TriggerType.WORLD_STATE:
            return self._check_world_state_trigger(trigger, context)

        elif trigger.trigger_type == TriggerType.LORE_VOLUNTEER:
            return self._check_lore_volunteer(trigger, player_id, context)

        return False

    def _check_time_trigger(
        self, trigger: ProactiveTrigger, last_seen: float, now: float
    ) -> bool:
        """Fire if player hasn't visited in a while."""
        min_absence = trigger.condition.get("min_absence_seconds", 3600)
        if last_seen == 0.0:
            # First visit ever — check for first_visit trigger
            return trigger.condition.get("first_visit", False)
        absence = now - last_seen
        return absence >= min_absence

    def _check_event_trigger(
        self, trigger: ProactiveTrigger, player_id: str, context: Dict[str, Any]
    ) -> bool:
        """Fire if a world event is active and player hasn't been told."""
        required_flag = trigger.condition.get("world_flag")
        if not required_flag:
            return False

        world_flags = context.get("world_flags", {})
        flag_value = world_flags.get(required_flag)

        if flag_value is None or flag_value is False:
            return False

        # Check if player already knows about this event
        event_key = f"{trigger.trigger_id}:{required_flag}"
        if event_key in self._notified_events.get(player_id, set()):
            return False

        # Mark as notified
        self._notified_events[player_id].add(event_key)
        return True

    def _check_relationship_trigger(
        self, trigger: ProactiveTrigger, context: Dict[str, Any]
    ) -> bool:
        """Fire when relationship reaches a milestone."""
        relationship = context.get("relationship", {})
        required_tier = trigger.condition.get("min_tier")
        required_trust = trigger.condition.get("min_trust")
        required_fondness = trigger.condition.get("min_fondness")

        if required_tier:
            current_tier = relationship.get("tier", "stranger")
            # Support both legacy tiers and new capability-based tiers
            tier_order = [
                "stranger", "acquaintance", "friend", "trusted_ally",
                "shares_rumors", "offers_quests", "shares_secrets",
                "trusts_with_credit", "reveals_hidden_stock"
            ]

            try:
                current_idx = tier_order.index(current_tier) if current_tier in tier_order else 0
                required_idx = tier_order.index(required_tier) if required_tier in tier_order else 999

                if current_idx < required_idx:
                    return False
            except Exception:
                # Fallback to simple equality if something goes wrong
                if current_tier != required_tier:
                    return False

        if required_trust and relationship.get("trust", 0) < required_trust:
            return False

        if required_fondness and relationship.get("fondness", 0) < required_fondness:
            return False

        return True

    def _check_world_state_trigger(
        self, trigger: ProactiveTrigger, context: Dict[str, Any]
    ) -> bool:
        """Fire based on world state flags."""
        world_flags = context.get("world_flags", {})
        for flag_key, expected in trigger.condition.items():
            actual = world_flags.get(flag_key)
            if actual is None:
                return False
            if isinstance(expected, dict):
                op = expected.get("op", "eq")
                value = expected.get("value")
                if op == "gt" and not (actual > value):
                    return False
                elif op == "lt" and not (actual < value):
                    return False
                elif op == "eq" and actual != value:
                    return False
            else:
                if actual != expected:
                    return False
        return True

    def _check_lore_volunteer(
        self, trigger: ProactiveTrigger, player_id: str, context: Dict[str, Any]
    ) -> bool:
        """Fire if there's significant knowledge in the cloud the player hasn't heard."""
        # Significant lore items are passed in the 'active_lore' context list
        active_lore = context.get("active_lore", [])
        if not active_lore:
            return False

        for entry in active_lore:
            # We skip things the player already knows
            event_key = f"lore:{entry.get('entity_id')}"
            if event_key in self._notified_events.get(player_id, set()):
                continue

            # Pick a rumor or significant fact to volunteer
            facts = entry.get("facts", [])
            if not facts:
                continue

            # Update the trigger message with the factual gossip
            # We want to volunteer the LAST (most recent) fact usually
            best_fact = facts[-1]
            trigger.message = f"I've heard whispers that... {best_fact}."

            # Record notification
            self._notified_events[player_id].add(event_key)
            return True

        return False

    def record_player_departure(self, player_id: str) -> None:
        """Explicitly mark when a player leaves (for time-based triggers)."""
        self._player_last_seen[player_id] = time.time()

    def add_default_triggers(self) -> None:
        """Add sensible default triggers that work for any NPC."""
        defaults = [
            ProactiveTrigger(
                trigger_id="long_absence",
                trigger_type=TriggerType.TIME_BASED,
                message="It's been a while! Good to see you again.",
                condition={"min_absence_seconds": 7200},  # 2 hours
                cooldown_seconds=7200,
                priority=0.6,
            ),
            ProactiveTrigger(
                trigger_id="frequent_visitor",
                trigger_type=TriggerType.RELATIONSHIP_BASED,
                message="Ah, one of my regulars! Always a pleasure.",
                condition={"min_tier": "friend"},
                cooldown_seconds=3600,
                priority=0.4,
            ),
            ProactiveTrigger(
                trigger_id="storm_warning",
                trigger_type=TriggerType.EVENT_BASED,
                message="Careful out there — I hear a storm is rolling in.",
                condition={"world_flag": "weather_danger"},
                cooldown_seconds=1800,
                priority=0.7,
            ),
            ProactiveTrigger(
                trigger_id="town_attack",
                trigger_type=TriggerType.EVENT_BASED,
                message="Have you heard? The town is under attack! Stay safe.",
                condition={"world_flag": "TOWN_UNDER_ATTACK"},
                cooldown_seconds=600,
                priority=0.9,
            ),
        ]
        for trigger in defaults:
            self.add_trigger(trigger)

    def load_from_config(self, triggers_config: List[Dict[str, Any]]) -> None:
        """Load triggers from character config."""
        for cfg in triggers_config:
            try:
                trigger_type = TriggerType(cfg.get("trigger_type", "time_based"))
            except ValueError:
                trigger_type = TriggerType.TIME_BASED

            trigger = ProactiveTrigger(
                trigger_id=cfg.get("trigger_id", f"trigger_{len(self._triggers)}"),
                trigger_type=trigger_type,
                message=cfg.get("message", ""),
                condition=cfg.get("condition", {}),
                cooldown_seconds=cfg.get("cooldown_seconds", 300),
                max_fires=cfg.get("max_fires", -1),
                priority=cfg.get("priority", 0.5),
            )
            self.add_trigger(trigger)

    def get_stats(self) -> Dict[str, Any]:
        """Return proactive engine statistics."""
        return {
            "total_triggers": len(self._triggers),
            "active_triggers": len([t for t in self._triggers.values() if t.active]),
            "total_checks": self._total_checks,
            "total_fires": self._total_fires,
            "players_tracked": len(self._player_last_seen),
        }
