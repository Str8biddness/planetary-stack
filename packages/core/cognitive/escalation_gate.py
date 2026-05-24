"""
Module 6: Escalation Gate
"When to call the Thinking Layer"

The smart decision-maker that determines whether the NPC can handle
a query locally or needs to escalate to the shared SLM.

Cost: ~0.1ms per query
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Set


@dataclass
class EscalationSignal:
    """A single signal contributing to the escalation decision."""
    name: str
    weight: float
    score: float  # 0.0 = no signal, 1.0 = maximum signal
    reason: str = ""


@dataclass
class EscalationDecision:
    """The final escalation decision."""
    should_escalate: bool
    total_score: float
    threshold: float
    signals: list  # List of EscalationSignal
    fallback_response: Optional[str] = None  # In-character stall if SLM unavailable


# Question words that suggest the player needs reasoning, not lookup
_REASONING_WORDS = {"why", "how", "explain", "reason", "cause", "think",
                    "believe", "opinion", "should", "would", "could",
                    "hypothetically", "imagine", "suppose", "what if"}

# Complex syntax markers
_COMPLEX_MARKERS = {"if", "unless", "suppose", "hypothetically", "would you",
                    "what would", "imagine", "pretend", "let's say"}

# Emotional intensity words
_INTENSITY_WORDS = {"please", "desperate", "beg", "must", "dying", "critical",
                    "urgent", "immediately", "emergency", "help", "save",
                    "furious", "angry", "outraged", "ecstatic", "overjoyed",
                    "terrified", "heartbroken", "devastated"}


class EscalationGate:
    """
    Module 6 of the Cognitive Engine.
    Decides whether a query should be handled locally or escalated to the Thinking Layer.
    """

    # Default stall responses (in-character, buys time)
    DEFAULT_STALLS = [
        "That's... a deep question. Let me think on that.",
        "Hmm. You've given me something to ponder, friend.",
        "Now that's something I'd need to think carefully about.",
        "I... don't have a quick answer for that one.",
        "*strokes chin thoughtfully* Come back to me on that, will you?",
        "That's beyond my usual dealings. Let me consider it.",
    ]

    def __init__(
        self,
        threshold: float = 0.55,
        custom_stalls: Optional[list] = None,
    ):
        self.threshold = threshold
        self._stalls = custom_stalls or self.DEFAULT_STALLS
        self._stall_index = 0

    def evaluate(
        self,
        match_confidence: float,
        keywords: Set[str],
        conversation_depth: int = 0,
        emotion_intensity: float = 0.0,
        query_text: str = "",
    ) -> EscalationDecision:
        """
        Evaluate whether a query should be escalated to the Thinking Layer.

        Args:
            match_confidence: Best pattern match score (0.0-1.0)
            keywords: Content words from the query
            conversation_depth: How many turns into the conversation
            emotion_intensity: Current emotion intensity (0.0-1.0)
            query_text: Raw query text

        Returns:
            EscalationDecision with signals and final verdict
        """
        signals = []

        # Signal 1: Pattern confidence (weight 0.40)
        # Low confidence = strong escalation signal
        conf_signal = max(0, 1.0 - (match_confidence / self.threshold))
        conf_signal = min(1.0, conf_signal)
        signals.append(EscalationSignal(
            name="low_pattern_confidence",
            weight=0.40,
            score=conf_signal,
            reason=f"Match confidence {match_confidence:.2f} vs threshold {self.threshold}"
        ))

        # Signal 2: Novel entities (weight 0.20)
        # Keywords that aren't common conversation words suggest novel territory
        common_words = {"sword", "potion", "buy", "sell", "quest", "price",
                        "gold", "shop", "trade", "weapon", "armor", "item",
                        "hello", "goodbye", "thanks", "help", "tell", "story",
                        "name", "scar", "wife", "caravan", "road", "town",
                        "duke", "mage", "tavern", "guard", "rumor", "news"}
        novel = keywords - common_words
        novel_ratio = len(novel) / max(len(keywords), 1)
        signals.append(EscalationSignal(
            name="novel_entities",
            weight=0.20,
            score=min(1.0, novel_ratio),
            reason=f"Novel words: {novel if novel else 'none'}"
        ))

        # Signal 3: Reasoning questions (weight 0.15)
        reasoning = len(keywords & _REASONING_WORDS)
        reasoning_signal = min(1.0, reasoning / 2.0)
        signals.append(EscalationSignal(
            name="reasoning_question",
            weight=0.15,
            score=reasoning_signal,
            reason=f"Reasoning words found: {keywords & _REASONING_WORDS}"
        ))

        # Signal 4: Conversation depth (weight 0.10)
        depth_signal = min(1.0, conversation_depth / 8.0)
        signals.append(EscalationSignal(
            name="conversation_depth",
            weight=0.10,
            score=depth_signal,
            reason=f"Conversation depth: {conversation_depth} turns"
        ))

        # Signal 5: Emotional intensity (weight 0.10)
        intensity_from_words = len(keywords & _INTENSITY_WORDS) / 3.0
        combined_intensity = max(emotion_intensity, intensity_from_words)
        signals.append(EscalationSignal(
            name="emotional_intensity",
            weight=0.10,
            score=min(1.0, combined_intensity),
            reason=f"Emotion intensity: {combined_intensity:.2f}"
        ))

        # Signal 6: Complex syntax (weight 0.05)
        query_lower = query_text.lower()
        complex_count = sum(1 for m in _COMPLEX_MARKERS if m in query_lower)
        complex_signal = min(1.0, complex_count / 2.0)
        signals.append(EscalationSignal(
            name="complex_syntax",
            weight=0.05,
            score=complex_signal,
            reason=f"Complex markers found: {complex_count}"
        ))

        # Calculate weighted total
        total = sum(s.weight * s.score for s in signals)
        should_escalate = total > self.threshold

        # Get a stall response (in case SLM is unavailable)
        stall = self._stalls[self._stall_index % len(self._stalls)]
        self._stall_index += 1

        return EscalationDecision(
            should_escalate=should_escalate,
            total_score=round(total, 4),
            threshold=self.threshold,
            signals=signals,
            fallback_response=stall if should_escalate else None,
        )
