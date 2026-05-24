"""
Module 3: Response Compositor
"Building responses from parts instead of lookup"

Instead of returning a single static template, assembles responses from
modular PARTS based on context. This is the key to making 30 patterns
feel like 300.

When a DialogueRanker is available, generates multiple candidate responses
and ranks them by relevance, personality fit, flow, and variety.

Cost: ~0.2ms per query (string assembly), ~0.5ms with ranking
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .emotion_state_machine import EmotionState

logger = logging.getLogger(__name__)


@dataclass
class CompositeResponse:
    """A response built from modular parts."""
    opener: List[str] = field(default_factory=list)   # Random opener lines
    body: str = ""                                      # Core content
    detail: List[str] = field(default_factory=list)    # Optional detail expansions
    closer: List[str] = field(default_factory=list)    # Random closer lines
    context_inserts: Dict[str, str] = field(default_factory=dict)
    emotion_variants: Dict[str, str] = field(default_factory=dict)


class ResponseCompositor:
    """
    Module 3 of the Cognitive Engine.
    Assembles varied, context-aware responses from modular parts.
    Optionally uses DialogueRanker to pick the best candidate.
    """

    def __init__(self, dialogue_ranker=None):
        self._rng = random.Random()
        self._dialogue_ranker = dialogue_ranker
        # Track what we've said recently to avoid repetition
        self._recent_openers: Dict[str, List[str]] = {}  # player_id → last N openers used
        self._recent_closers: Dict[str, List[str]] = {}
        self._recent_responses: Dict[str, List[str]] = {}  # player_id → last N full responses
        self._max_recent = 3

    def compose(
        self,
        pattern: Dict[str, Any],
        context: Dict[str, Any],
        emotion: EmotionState = EmotionState.NEUTRAL,
        player_id: str = "default",
    ) -> str:
        """
        Compose a response from a pattern dict + conversation context.

        The pattern can be in two formats:
        1. Classic: {"response_template": "static string"}
        2. Composite: {"response_parts": {opener: [...], body: "...", closer: [...]},
                       "context_inserts": {...}, "emotion_variants": {...}}

        Args:
            pattern: The matched pattern dict
            context: The conversation context from ConversationTracker
            emotion: Current emotion state from EmotionStateMachine
            player_id: For tracking recent outputs per player

        Returns:
            The assembled response string
        """
        # Check for emotion variant override first
        emotion_variants = pattern.get("emotion_variants", {})
        emotion_key = emotion.value
        if emotion_key in emotion_variants and emotion != EmotionState.NEUTRAL:
            return emotion_variants[emotion_key]

        # If DialogueRanker is available and pattern has parts, use ranked composition
        if self._dialogue_ranker and "response_parts" in pattern:
            ranked = self._compose_ranked(pattern, context, player_id)
            if ranked:
                return ranked

        # Check if this pattern uses composite format
        if "response_parts" in pattern:
            return self._compose_from_parts(pattern, context, player_id)

        # Classic format: apply context inserts to static template
        template = pattern.get("response_template", "")
        return self._apply_context_inserts(template, pattern, context)

    def _compose_from_parts(
        self,
        pattern: Dict[str, Any],
        context: Dict[str, Any],
        player_id: str,
    ) -> str:
        """Build a response from modular parts."""
        parts = pattern["response_parts"]
        context_inserts = pattern.get("context_inserts", {})

        segments: List[str] = []

        # 1. Context-dependent prefix inserts
        for condition, insert_text in context_inserts.items():
            if self._check_condition(condition, context):
                segments.append(insert_text)

        # 2. Opener (random, avoiding recent repeats)
        openers = parts.get("opener", [])
        if openers:
            opener = self._pick_avoiding_recent(
                openers, self._recent_openers.get(player_id, [])
            )
            segments.append(opener)
            self._track_recent(player_id, opener, self._recent_openers)

        # 3. Body (core content, always included)
        body = parts.get("body", "")
        if body:
            segments.append(body)

        # 4. Detail (optional, 50% chance or if player asked a follow-up)
        details = parts.get("detail", [])
        if details:
            is_followup = context.get("turn_count", 0) > 1
            if is_followup or self._rng.random() > 0.5:
                segments.append(self._rng.choice(details))

        # 5. Price / stats (always if present)
        price = parts.get("price", "")
        if price:
            segments.append(price)

        # 6. Closer (random, avoiding recent repeats)
        closers = parts.get("closer", [])
        if closers:
            closer = self._pick_avoiding_recent(
                closers, self._recent_closers.get(player_id, [])
            )
            segments.append(closer)
            self._track_recent(player_id, closer, self._recent_closers)

        response = " ".join(s.strip() for s in segments if s.strip())

        # Track full response for variety scoring
        self._track_recent(player_id, response, self._recent_responses)

        return response

    def _compose_ranked(
        self,
        pattern: Dict[str, Any],
        context: Dict[str, Any],
        player_id: str,
        n_candidates: int = 3,
    ) -> Optional[str]:
        """
        Generate multiple candidate responses and rank them via DialogueRanker.
        Returns the highest-scored candidate, or None if ranking fails.
        """
        if not self._dialogue_ranker:
            return None

        parts = pattern["response_parts"]
        openers = parts.get("opener", [])
        closers = parts.get("closer", [])
        details = parts.get("detail", [])
        body = parts.get("body", "")

        if not body:
            return None

        # Generate N variant candidates by shuffling openers/closers/details
        candidates = []
        for _ in range(n_candidates):
            segs = []
            if openers:
                segs.append(self._rng.choice(openers))
            segs.append(body)
            if details and self._rng.random() > 0.4:
                segs.append(self._rng.choice(details))
            price = parts.get("price", "")
            if price:
                segs.append(price)
            if closers:
                segs.append(self._rng.choice(closers))
            candidates.append(" ".join(s.strip() for s in segs if s.strip()))

        if not candidates:
            return None

        # Build personality traits from context
        personality = {}
        if context.get("emotion"):
            emo = context["emotion"]
            if hasattr(emo, 'value'):
                emo = emo.value
            personality["friendliness"] = 0.8 if emo in ("friendly", "grateful", "happy") else 0.4

        # Get recent responses for variety scoring
        recent = self._recent_responses.get(player_id, [])

        ranked = self._dialogue_ranker.rank(
            candidates=candidates,
            query=context.get("query", ""),
            personality=personality,
            recent_responses=recent,
        )

        if ranked:
            best = ranked[0][0]
            self._track_recent(player_id, best, self._recent_responses)
            return best

        return None

    def _apply_context_inserts(
        self,
        template: str,
        pattern: Dict[str, Any],
        context: Dict[str, Any],
    ) -> str:
        """Apply context-dependent inserts to a static template."""
        context_inserts = pattern.get("context_inserts", {})
        prefix_parts = []
        suffix_parts = []

        for condition, insert_text in context_inserts.items():
            if self._check_condition(condition, context):
                # Prefix inserts go before the main template
                if condition.startswith("IF_PREFIX_"):
                    prefix_parts.append(insert_text)
                else:
                    suffix_parts.append(insert_text)

        parts = prefix_parts + [template] + suffix_parts
        return " ".join(s.strip() for s in parts if s.strip())

    @staticmethod
    def _check_condition(condition: str, context: Dict[str, Any]) -> bool:
        """Evaluate a context condition string."""
        condition_upper = condition.upper()

        if condition_upper == "IF_RETURNING_CUSTOMER":
            return context.get("is_returning", False)

        if condition_upper == "IF_QUEST_ACTIVE":
            # Check if conversation has been about quests
            topic = context.get("active_topic")
            if hasattr(topic, 'value'):
                return topic.value == "quest"
            return str(topic).lower() == "quest"

        if condition_upper == "IF_TOPIC_CHANGE":
            return context.get("is_topic_change", False)

        if condition_upper.startswith("IF_EMOTION_"):
            emotion_name = condition_upper.replace("IF_EMOTION_", "").lower()
            current_emotion = context.get("emotion", EmotionState.NEUTRAL)
            if hasattr(current_emotion, 'value'):
                return current_emotion.value == emotion_name
            return str(current_emotion).lower() == emotion_name

        if condition_upper.startswith("IF_TRUST_ABOVE_"):
            try:
                threshold = int(condition_upper.replace("IF_TRUST_ABOVE_", ""))
                return context.get("trust", 50) > threshold
            except ValueError:
                return False

        if condition_upper.startswith("IF_FONDNESS_ABOVE_"):
            try:
                threshold = int(condition_upper.replace("IF_FONDNESS_ABOVE_", ""))
                return context.get("fondness", 50) > threshold
            except ValueError:
                return False

        if condition_upper.startswith("IF_WORLD_"):
            flag_name = condition_upper.replace("IF_WORLD_", "")
            world_state = context.get("world_state", {})
            return bool(world_state.get(flag_name, False))

        if condition_upper == "IF_DEEP_CONVERSATION":
            return context.get("conversation_depth", 0) > 3

        return False

    def _pick_avoiding_recent(self, options: List[str], recent: List[str]) -> str:
        """Pick a random option, trying to avoid recently used ones."""
        if len(options) <= 1:
            return options[0] if options else ""

        available = [o for o in options if o not in recent]
        if not available:
            available = options  # All recently used, pick any

        return self._rng.choice(available)

    def _track_recent(self, player_id: str, item: str, tracker: Dict[str, List[str]]):
        """Track a recently used item to avoid repetition."""
        if player_id not in tracker:
            tracker[player_id] = []
        tracker[player_id].append(item)
        if len(tracker[player_id]) > self._max_recent:
            tracker[player_id].pop(0)
