"""
Module 5: World State Reactor
"The NPC knows what's happening in the world"

Subscribes to a global world state bus. When world events happen,
NPCs update their available response pool and emotional baseline.

Cost: ~0.1ms per query (flag lookup), 0 extra RAM (shared flags)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

from .emotion_state_machine import EmotionState


@dataclass
class WorldFlag:
    """A single world state flag."""
    name: str
    value: Any
    set_at: float = field(default_factory=time.time)
    set_by: str = "system"  # who/what set this flag


@dataclass
class WorldReaction:
    """How an NPC reacts to a specific world state."""
    flag_name: str
    flag_value: Any
    emotion_override: Optional[EmotionState] = None  # Force emotion when flag is set
    pattern_overrides: Dict[str, str] = field(default_factory=dict)  # pattern_id → new response
    disabled_patterns: Set[str] = field(default_factory=set)  # pattern IDs to disable
    enabled_patterns: Set[str] = field(default_factory=set)   # pattern IDs to enable (normally inactive)
    greeting_override: Optional[str] = None  # Replace default greeting


class WorldStateReactor:
    """
    Module 5 of the Cognitive Engine.
    Global world state bus that NPCs subscribe to for context-aware behavior.
    """

    # Shared across ALL NPCs — singleton world state
    _global_state: Dict[str, WorldFlag] = {}

    def __init__(self, reactions: Optional[List[WorldReaction]] = None):
        """
        Args:
            reactions: NPC-specific reactions to world state flags.
        """
        self._reactions = reactions or []
        self._reaction_map: Dict[str, List[WorldReaction]] = {}
        for r in self._reactions:
            self._reaction_map.setdefault(r.flag_name, []).append(r)

    # ------------------------------------------------------------------
    # Class-level methods: shared world state
    # ------------------------------------------------------------------

    @classmethod
    def set_flag(cls, name: str, value: Any, set_by: str = "system") -> None:
        """Set a global world state flag. Affects all NPCs."""
        cls._global_state[name] = WorldFlag(
            name=name, value=value, set_at=time.time(), set_by=set_by
        )

    @classmethod
    def get_flag(cls, name: str, default: Any = None) -> Any:
        """Get a world state flag value."""
        flag = cls._global_state.get(name)
        return flag.value if flag else default

    @classmethod
    def clear_flag(cls, name: str) -> None:
        """Remove a world state flag."""
        cls._global_state.pop(name, None)

    @classmethod
    def get_all_flags(cls) -> Dict[str, Any]:
        """Get all current world state flags as {name: value}."""
        return {k: v.value for k, v in cls._global_state.items()}

    @classmethod
    def reset_world(cls) -> None:
        """Clear all world state (for testing)."""
        cls._global_state.clear()

    # ------------------------------------------------------------------
    # Instance methods: NPC-specific reactions
    # ------------------------------------------------------------------

    def process(self) -> Dict:
        """
        Check current world state against NPC's reactions.

        Returns:
        {
            "active_flags": dict of current world state,
            "emotion_override": EmotionState or None,
            "disabled_patterns": set of pattern IDs to skip,
            "enabled_patterns": set of pattern IDs to activate,
            "pattern_overrides": dict of pattern_id → new response text,
            "greeting_override": str or None,
            "world_state": dict (for other modules to check conditions),
        }
        """
        active_flags = self.get_all_flags()
        emotion_override = None
        disabled_patterns: Set[str] = set()
        enabled_patterns: Set[str] = set()
        pattern_overrides: Dict[str, str] = {}
        greeting_override = None

        # Check each reaction against current flags
        for flag_name, reactions in self._reaction_map.items():
            current_value = active_flags.get(flag_name)
            for reaction in reactions:
                if current_value == reaction.flag_value:
                    # This reaction is active
                    if reaction.emotion_override is not None:
                        emotion_override = reaction.emotion_override
                    disabled_patterns |= reaction.disabled_patterns
                    enabled_patterns |= reaction.enabled_patterns
                    pattern_overrides.update(reaction.pattern_overrides)
                    if reaction.greeting_override:
                        greeting_override = reaction.greeting_override

        return {
            "active_flags": active_flags,
            "emotion_override": emotion_override,
            "disabled_patterns": disabled_patterns,
            "enabled_patterns": enabled_patterns,
            "pattern_overrides": pattern_overrides,
            "greeting_override": greeting_override,
            "world_state": active_flags,  # Alias for condition checking
        }

    def add_reaction(self, reaction: WorldReaction) -> None:
        """Add a new reaction at runtime."""
        self._reactions.append(reaction)
        self._reaction_map.setdefault(reaction.flag_name, []).append(reaction)

    def is_flag_set(self, name: str, value: Any = True) -> bool:
        """Quick check if a specific flag has a specific value."""
        return self.get_flag(name) == value
