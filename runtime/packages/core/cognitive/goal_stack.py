"""
Module 14: Goal Stack — Autonomous NPC Objectives
AIVM Synthesus 2.0

NPCs pursue goals autonomously. Instead of only reacting to player input,
an NPC can decide to mention its shop sale, steer a conversation toward a
quest it wants completed, or warn about a world event.

Goal Types:
  MENTION  — Inject text into response opener (e.g., "By the way, I'm having a sale...")
  STEER    — Redirect conversation topic (e.g., "Speaking of which, I've been needing help...")
  WARN     — Override response with urgent warning (e.g., "Wait — I just heard news...")

Goals are evaluated every query. Each goal has:
  - Priority (0-1): higher-priority goals fire first
  - Trigger conditions: world_flag checks that must pass
  - Cooldown: minimum turns between mentions
  - Max mentions: after this many, the goal retires

Cost: <0.1ms per query (pure dict lookups), zero GPU.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class GoalType(Enum):
    """How the goal injects into the response."""
    MENTION = "mention"   # Prepend to response
    STEER = "steer"       # Redirect conversation topic
    WARN = "warn"         # Override full response


@dataclass
class Goal:
    """A single autonomous NPC goal."""
    goal_id: str
    description: str
    goal_type: GoalType = GoalType.MENTION
    priority: float = 0.5          # 0-1, higher fires first
    response_injection: str = ""    # Text to inject/prepend/override
    trigger_conditions: Dict[str, Any] = field(default_factory=dict)
    cooldown_turns: int = 5         # Min turns between mentions
    max_mentions: int = 3           # After this many, auto-retire
    current_mentions: int = 0
    last_mentioned_turn: int = -999
    created_at: float = field(default_factory=time.time)
    active: bool = True

    def is_ready(self, current_turn: int) -> bool:
        """Check if this goal can fire on this turn."""
        if not self.active:
            return False
        if self.current_mentions >= self.max_mentions:
            return False
        if (current_turn - self.last_mentioned_turn) < self.cooldown_turns:
            return False
        return True

    def conditions_met(self, world_flags: Dict[str, Any]) -> bool:
        """Check if all trigger conditions are satisfied."""
        if not self.trigger_conditions:
            return True  # No conditions = always eligible

        for flag_key, expected_value in self.trigger_conditions.items():
            actual = world_flags.get(flag_key)
            if actual is None:
                return False
            # Support simple equality and thresholds
            if isinstance(expected_value, dict):
                op = expected_value.get("op", "eq")
                value = expected_value.get("value")
                if op == "gt" and not (actual > value):
                    return False
                elif op == "lt" and not (actual < value):
                    return False
                elif op == "gte" and not (actual >= value):
                    return False
                elif op == "lte" and not (actual <= value):
                    return False
                elif op == "eq" and actual != value:
                    return False
                elif op == "neq" and actual == value:
                    return False
            else:
                if actual != expected_value:
                    return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "description": self.description,
            "goal_type": self.goal_type.value,
            "priority": self.priority,
            "response_injection": self.response_injection,
            "trigger_conditions": self.trigger_conditions,
            "cooldown_turns": self.cooldown_turns,
            "max_mentions": self.max_mentions,
            "current_mentions": self.current_mentions,
            "last_mentioned_turn": self.last_mentioned_turn,
            "active": self.active,
        }


class GoalStack:
    """
    Manages autonomous NPC goals and evaluates which (if any) should
    inject into the current response.

    Usage:
        stack = GoalStack()
        stack.add_goal(Goal(
            goal_id="sale_announcement",
            description="Mention the shop sale",
            goal_type=GoalType.MENTION,
            priority=0.7,
            response_injection="Oh, before I forget — everything's 20% off today!",
            cooldown_turns=10,
            max_mentions=3,
        ))

        # During query processing:
        goal = stack.evaluate(current_turn=5, world_flags=flags)
        if goal:
            response = f"{goal.response_injection} {original_response}"
            stack.mark_mentioned(goal.goal_id, current_turn=5)
    """

    def __init__(self):
        self._goals: Dict[str, Goal] = {}
        self._total_evaluations: int = 0
        self._total_fires: int = 0

    def add_goal(self, goal: Goal) -> None:
        """Register a new goal."""
        self._goals[goal.goal_id] = goal
        logger.debug(f"GoalStack: added goal '{goal.goal_id}' (priority={goal.priority})")

    def remove_goal(self, goal_id: str) -> bool:
        """Remove a goal (completed or cancelled)."""
        if goal_id in self._goals:
            del self._goals[goal_id]
            return True
        return False

    def deactivate_goal(self, goal_id: str) -> None:
        """Deactivate a goal without removing it."""
        if goal_id in self._goals:
            self._goals[goal_id].active = False

    def evaluate(
        self,
        current_turn: int,
        world_flags: Optional[Dict[str, Any]] = None,
    ) -> Optional[Goal]:
        """
        Evaluate all goals and return the highest-priority one whose
        conditions are met and cooldown has elapsed.

        Returns None if no goal should fire.
        """
        self._total_evaluations += 1
        world_flags = world_flags or {}

        candidates = []
        for goal in self._goals.values():
            if goal.is_ready(current_turn) and goal.conditions_met(world_flags):
                candidates.append(goal)

        if not candidates:
            return None

        # Sort by priority descending
        candidates.sort(key=lambda g: g.priority, reverse=True)
        return candidates[0]

    def mark_mentioned(self, goal_id: str, current_turn: int) -> None:
        """Record that a goal was injected into a response."""
        if goal_id in self._goals:
            goal = self._goals[goal_id]
            goal.current_mentions += 1
            goal.last_mentioned_turn = current_turn
            self._total_fires += 1

            # Auto-retire if max mentions reached
            if goal.current_mentions >= goal.max_mentions:
                goal.active = False
                logger.info(f"GoalStack: goal '{goal_id}' retired (max mentions reached)")

    def get_active_goals(self) -> List[Goal]:
        """Return all currently active goals."""
        return [g for g in self._goals.values() if g.active]

    def get_all_goals(self) -> List[Goal]:
        """Return all goals (active + inactive)."""
        return list(self._goals.values())

    def load_from_config(self, goals_config: List[Dict[str, Any]]) -> None:
        """Load goals from a character's bio.json goals config."""
        for cfg in goals_config:
            goal_type_str = cfg.get("goal_type", "mention")
            try:
                goal_type = GoalType(goal_type_str)
            except ValueError:
                goal_type = GoalType.MENTION

            goal = Goal(
                goal_id=cfg.get("goal_id", f"goal_{len(self._goals)}"),
                description=cfg.get("description", ""),
                goal_type=goal_type,
                priority=cfg.get("priority", 0.5),
                response_injection=cfg.get("response_injection", ""),
                trigger_conditions=cfg.get("trigger_conditions", {}),
                cooldown_turns=cfg.get("cooldown_turns", 5),
                max_mentions=cfg.get("max_mentions", 3),
            )
            self.add_goal(goal)

    def get_stats(self) -> Dict[str, Any]:
        """Return goal stack statistics."""
        return {
            "total_goals": len(self._goals),
            "active_goals": len(self.get_active_goals()),
            "total_evaluations": self._total_evaluations,
            "total_fires": self._total_fires,
            "goals": [g.to_dict() for g in self._goals.values()],
        }
