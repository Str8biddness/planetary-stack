"""
Module 2: Emotion State Machine
"How is the NPC feeling right now?"

Tracks the NPC's emotional state as a finite state machine.
States drift back toward baseline over time.
Each state modifies response DELIVERY, not content.

Cost: ~0.05ms per query, 1 byte per NPC (current state enum)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple


class EmotionState(Enum):
    NEUTRAL = "neutral"
    FRIENDLY = "friendly"
    EXCITED = "excited"
    SUSPICIOUS = "suspicious"
    ANGRY = "angry"
    AFRAID = "afraid"
    SAD = "sad"
    AMUSED = "amused"


@dataclass
class EmotionTransition:
    """A trigger that causes an emotion state change."""
    from_state: EmotionState
    to_state: EmotionState
    trigger_words: Set[str]
    weight: float = 1.0  # How strongly this triggers (for competing transitions)


# Default transition table — can be overridden per character
_DEFAULT_TRANSITIONS: List[EmotionTransition] = [
    # From NEUTRAL
    EmotionTransition(EmotionState.NEUTRAL, EmotionState.FRIENDLY,
                      {"thank", "thanks", "friend", "appreciate", "kind", "please",
                       "nice", "great", "wonderful", "love", "help"}),
    EmotionTransition(EmotionState.NEUTRAL, EmotionState.SUSPICIOUS,
                      {"steal", "rob", "lie", "cheat", "trick", "threaten",
                       "suspicious", "sneak", "secret", "hidden",
                       "liar", "fraud", "scam", "thief", "hate",
                       "terrible", "worst", "pathetic", "useless"}),
    EmotionTransition(EmotionState.NEUTRAL, EmotionState.EXCITED,
                      {"amazing", "incredible", "treasure", "rare", "legendary",
                       "quest", "adventure", "gold", "fortune", "reward"}),
    EmotionTransition(EmotionState.NEUTRAL, EmotionState.SAD,
                      {"dead", "died", "lost", "gone", "sorry", "tragic",
                       "mourn", "grief", "miss", "funeral"}),
    EmotionTransition(EmotionState.NEUTRAL, EmotionState.AMUSED,
                      {"joke", "funny", "laugh", "haha", "silly", "ridiculous",
                       "fool", "humor"}),

    # From FRIENDLY
    EmotionTransition(EmotionState.FRIENDLY, EmotionState.EXCITED,
                      {"amazing", "incredible", "treasure", "deal", "best",
                       "reward", "quest"}),
    EmotionTransition(EmotionState.FRIENDLY, EmotionState.SUSPICIOUS,
                      {"steal", "rob", "lie", "cheat", "threaten",
                       "liar", "fraud", "scam", "thief", "cheat",
                       "hate", "terrible", "worst", "pathetic", "useless"}, weight=1.5),
    EmotionTransition(EmotionState.FRIENDLY, EmotionState.NEUTRAL,
                      {"haggle", "discount", "cheaper", "expensive", "overpriced"}),

    # From SUSPICIOUS
    EmotionTransition(EmotionState.SUSPICIOUS, EmotionState.AFRAID,
                      {"kill", "die", "attack", "weapon", "fight", "destroy",
                       "burn", "hurt", "pain", "death", "murder"}, weight=1.5),
    EmotionTransition(EmotionState.SUSPICIOUS, EmotionState.NEUTRAL,
                      {"sorry", "apologize", "mistake", "peace", "friend",
                       "mean", "joking", "kidding", "calm"}),
    EmotionTransition(EmotionState.SUSPICIOUS, EmotionState.ANGRY,
                      {"again", "insist", "force", "demand", "threaten",
                       "refuse", "won't"}, weight=1.2),

    # From AFRAID
    EmotionTransition(EmotionState.AFRAID, EmotionState.NEUTRAL,
                      {"sorry", "apologize", "peace", "calm", "safe",
                       "protect", "help", "friend", "okay"}),
    EmotionTransition(EmotionState.AFRAID, EmotionState.ANGRY,
                      {"coward", "pathetic", "weak", "scared", "baby"}),

    # From ANGRY
    EmotionTransition(EmotionState.ANGRY, EmotionState.NEUTRAL,
                      {"sorry", "apologize", "peace", "forgive", "calm",
                       "wrong", "mistake"}, weight=0.7),
    EmotionTransition(EmotionState.ANGRY, EmotionState.AFRAID,
                      {"kill", "die", "weapon", "blade", "sword"}, weight=0.8),

    # From EXCITED
    EmotionTransition(EmotionState.EXCITED, EmotionState.FRIENDLY,
                      {"thank", "thanks", "deal", "agree", "yes"}),
    EmotionTransition(EmotionState.EXCITED, EmotionState.SUSPICIOUS,
                      {"lie", "fake", "cheat", "scam", "too good"}),

    # From SAD
    EmotionTransition(EmotionState.SAD, EmotionState.FRIENDLY,
                      {"help", "comfort", "understand", "care", "together"}),
    EmotionTransition(EmotionState.SAD, EmotionState.NEUTRAL,
                      {"anyway", "moving", "okay", "fine", "alright"}),

    # From AMUSED
    EmotionTransition(EmotionState.AMUSED, EmotionState.FRIENDLY,
                      {"friend", "like", "good", "fun"}),
    EmotionTransition(EmotionState.AMUSED, EmotionState.SUSPICIOUS,
                      {"steal", "rob", "trick"}),
]

# Emotional decay: how long (seconds) before drifting back toward baseline
_DECAY_RATES = {
    EmotionState.NEUTRAL: 0,        # Baseline, no decay
    EmotionState.FRIENDLY: 120,     # 2 minutes
    EmotionState.EXCITED: 60,       # 1 minute
    EmotionState.SUSPICIOUS: 90,    # 1.5 minutes
    EmotionState.ANGRY: 180,        # 3 minutes (anger lingers)
    EmotionState.AFRAID: 60,        # 1 minute
    EmotionState.SAD: 150,          # 2.5 minutes
    EmotionState.AMUSED: 45,        # 45 seconds
}

# Decay path: each state drifts toward this state before reaching NEUTRAL
_DECAY_PATH = {
    EmotionState.EXCITED: EmotionState.FRIENDLY,
    EmotionState.AFRAID: EmotionState.SUSPICIOUS,
    EmotionState.ANGRY: EmotionState.SUSPICIOUS,
    EmotionState.AMUSED: EmotionState.FRIENDLY,
    EmotionState.FRIENDLY: EmotionState.NEUTRAL,
    EmotionState.SUSPICIOUS: EmotionState.NEUTRAL,
    EmotionState.SAD: EmotionState.NEUTRAL,
}


@dataclass
class NPCEmotionState:
    """Per-NPC emotion tracking."""
    current: EmotionState = EmotionState.NEUTRAL
    baseline: EmotionState = EmotionState.NEUTRAL  # Character default
    intensity: float = 0.5  # 0.0 = barely, 1.0 = overwhelmingly
    last_transition: float = field(default_factory=time.time)
    transition_count: int = 0


class EmotionStateMachine:
    """
    Module 2 of the Cognitive Engine.
    Tracks emotional state per NPC-player pair and modifies response delivery.
    """

    def __init__(
        self,
        baseline: EmotionState = EmotionState.NEUTRAL,
        custom_transitions: Optional[List[EmotionTransition]] = None,
    ):
        self._baseline = baseline
        self._transitions = custom_transitions or _DEFAULT_TRANSITIONS
        self._states: Dict[str, NPCEmotionState] = {}

        # Build lookup: from_state → list of transitions
        self._transition_map: Dict[EmotionState, List[EmotionTransition]] = {}
        for t in self._transitions:
            self._transition_map.setdefault(t.from_state, []).append(t)

    def _get_state(self, player_id: str) -> NPCEmotionState:
        if player_id not in self._states:
            self._states[player_id] = NPCEmotionState(baseline=self._baseline)
        return self._states[player_id]

    def _apply_decay(self, state: NPCEmotionState) -> None:
        """Drift emotion toward baseline over time."""
        if state.current == state.baseline:
            return

        decay_time = _DECAY_RATES.get(state.current, 60)
        elapsed = time.time() - state.last_transition

        if elapsed > decay_time:
            # Move one step toward baseline
            next_state = _DECAY_PATH.get(state.current, EmotionState.NEUTRAL)
            state.current = next_state
            state.intensity = max(0.3, state.intensity - 0.2)
            state.last_transition = time.time()

    def process(self, player_id: str, keywords: Set[str]) -> Dict:
        """
        Process player keywords and update emotion state.

        Returns:
        {
            "emotion": EmotionState,
            "previous_emotion": EmotionState,
            "intensity": float,
            "changed": bool,
        }
        """
        state = self._get_state(player_id)
        previous = state.current

        # Apply time-based decay first
        self._apply_decay(state)

        # Check for transitions from current state
        transitions = self._transition_map.get(state.current, [])
        best_transition = None
        best_score = 0.0

        for t in transitions:
            overlap = len(keywords & t.trigger_words)
            if overlap > 0:
                score = overlap * t.weight
                if score > best_score:
                    best_score = score
                    best_transition = t

        # Apply transition if found
        changed = False
        if best_transition and best_score >= 1.0:
            state.current = best_transition.to_state
            state.intensity = min(1.0, 0.5 + best_score * 0.1)
            state.last_transition = time.time()
            state.transition_count += 1
            changed = True

        return {
            "emotion": state.current,
            "previous_emotion": previous,
            "intensity": state.intensity,
            "changed": changed,
        }

    def set_baseline(self, player_id: str, baseline: EmotionState) -> None:
        """Override the baseline emotion (e.g., during world events)."""
        state = self._get_state(player_id)
        state.baseline = baseline
        # If current is NEUTRAL, shift to new baseline
        if state.current == EmotionState.NEUTRAL:
            state.current = baseline

    def force_state(self, player_id: str, emotion: EmotionState, intensity: float = 0.7) -> None:
        """Force an emotion state (e.g., world event: town under attack → AFRAID)."""
        state = self._get_state(player_id)
        state.current = emotion
        state.intensity = intensity
        state.last_transition = time.time()

    def get_emotion(self, player_id: str) -> EmotionState:
        """Get current emotion for a player."""
        state = self._get_state(player_id)
        self._apply_decay(state)
        return state.current

    def get_state(self, player_id: str) -> NPCEmotionState:
        """Get raw state for debugging."""
        return self._get_state(player_id)
