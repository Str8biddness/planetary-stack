"""
Module 9: Context Recall
"You mentioned earlier... / Remember when you said..."

Enables NPCs to reference their own prior statements in conversation.
When a player says "you said the road was dangerous" or "remember
what you told me about Tomás?", this module finds the relevant prior
NPC response and assembles a contextual callback.

Also handles:
- "what did you just say?" (immediate recall)
- "tell me again about..." (repeat with variation)
- Proactive callbacks ("As I mentioned, the road is dangerous...")

Cost: ~0.1ms per query, ~0 extra RAM (uses ConversationTracker data), zero GPU.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
from difflib import SequenceMatcher


@dataclass
class RecalledContext:
    """A piece of recalled conversation context."""
    original_response: str
    turn_number: int
    relevance_score: float
    match_type: str  # "keyword", "entity", "direct_reference", "topic"
    matched_terms: List[str] = field(default_factory=list)


# ── Recall trigger detection ──
_RECALL_TRIGGERS = {
    "remember", "mentioned", "said", "told", "earlier",
    "before", "again", "repeat", "back", "recall",
    "what did you", "you said", "you told", "you mentioned",
    "remind me", "tell me again", "say that again",
}

_CALLBACK_PREFIXES = [
    "As I mentioned,",
    "Like I said before,",
    "You may recall I said",
    "As I told you,",
    "Going back to what I said —",
    "Right, I did mention that.",
    "Yes, I remember saying that.",
    "*nods* I did say that.",
]

_REPEAT_PREFIXES = [
    "Of course. Let me say it again:",
    "Sure, I'll repeat that.",
    "Alright, once more:",
    "Pay attention this time:",
    "Right. What I said was:",
]

_NO_RECALL_RESPONSES = [
    "Hmm, I'm not sure I said that. Could you be more specific?",
    "I don't recall saying that exactly, friend. What are you referring to?",
    "*scratches chin* Are you sure I said that? My memory's good, but not perfect.",
    "I think you might be misremembering. What specifically are you asking about?",
]


class ContextRecall:
    """
    Module 9 of the Cognitive Engine.
    Enables NPCs to reference their own prior statements.
    """

    def __init__(self):
        # Track NPC responses per player for recall
        # player_id → list of (turn_number, response_text, keywords)
        self._response_history: Dict[str, List[Tuple[int, str, Set[str]]]] = {}
        self._turn_counters: Dict[str, int] = {}

    @staticmethod
    def _extract_keywords(text: str) -> Set[str]:
        """Extract content words for matching."""
        stop = {
            "the", "a", "an", "is", "it", "of", "in", "to", "and", "or", "i",
            "me", "my", "you", "your", "do", "does", "did", "can", "could",
            "would", "should", "what", "how", "why", "when", "where", "who",
            "that", "this", "if", "about", "for", "with", "on", "at", "by",
            "from", "up", "out", "so", "be", "been", "am", "are", "was", "were",
            "have", "has", "had", "not", "but", "just", "more", "very", "like",
            "any", "some", "no", "all", "them", "they", "we", "he", "she",
            "don't", "there", "got", "get", "know", "think", "tell",
            "really", "much", "way", "too", "also", "here", "now", "then",
            "going", "want", "need", "make", "let", "go", "come", "see",
            "take", "give", "say", "said", "look", "well", "back", "even",
            "still", "us", "our", "his", "her", "their", "him", "it's", "i'm",
        }
        return set(re.findall(r'[a-z]+', text.lower())) - stop

    def record_response(self, player_id: str, response: str):
        """Record an NPC response for future recall."""
        if player_id not in self._response_history:
            self._response_history[player_id] = []
            self._turn_counters[player_id] = 0

        self._turn_counters[player_id] += 1
        turn = self._turn_counters[player_id]
        keywords = self._extract_keywords(response)

        self._response_history[player_id].append((turn, response, keywords))

        # Keep only last 20 responses per player
        if len(self._response_history[player_id]) > 20:
            self._response_history[player_id] = self._response_history[player_id][-20:]

    def _is_recall_query(self, query: str) -> bool:
        """Detect if the player is trying to recall something the NPC said."""
        q_lower = query.lower()
        for trigger in _RECALL_TRIGGERS:
            if trigger in q_lower:
                return True
        return False

    def _find_best_match(
        self,
        query: str,
        player_id: str,
    ) -> Optional[RecalledContext]:
        """Find the best matching prior NPC response."""
        if player_id not in self._response_history:
            return None

        history = self._response_history[player_id]
        if not history:
            return None

        q_lower = query.lower()
        q_keywords = self._extract_keywords(query)

        # Check for "what did you just say" / immediate recall
        immediate_triggers = {"just said", "say that again", "repeat that",
                              "what did you say", "what did you just say",
                              "say again", "once more", "one more time",
                              "say it again", "repeat what you said"}
        for trigger in immediate_triggers:
            if trigger in q_lower:
                turn, resp, kw = history[-1]
                return RecalledContext(
                    original_response=resp,
                    turn_number=turn,
                    relevance_score=0.90,
                    match_type="direct_reference",
                    matched_terms=["immediate_recall"],
                )

        # Score each prior response
        best_match = None
        best_score = 0.0

        for turn, resp, resp_keywords in history:
            # Keyword overlap
            overlap = q_keywords & resp_keywords
            if not overlap:
                continue

            # Score: overlap ratio * recency bonus
            overlap_ratio = len(overlap) / max(len(q_keywords), 1)
            recency = 1.0 - (0.05 * (self._turn_counters.get(player_id, turn) - turn))
            recency = max(recency, 0.3)  # Floor at 0.3

            score = overlap_ratio * recency

            # Bonus for entity matches (capitalized words in both)
            entity_pattern = r'[A-Z][a-z]{2,}'
            query_entities = set(re.findall(entity_pattern, query))
            resp_entities = set(re.findall(entity_pattern, resp))
            entity_overlap = query_entities & resp_entities
            if entity_overlap:
                score += 0.2 * len(entity_overlap)

            # Bonus for substring match (player quotes the NPC)
            resp_lower = resp.lower()
            # Check if any 3+ word phrase from query appears in response
            q_words = q_lower.split()
            for i in range(len(q_words) - 2):
                phrase = " ".join(q_words[i:i+3])
                if phrase in resp_lower and len(phrase) > 8:
                    score += 0.3
                    break

            if score > best_score:
                best_score = score
                best_match = RecalledContext(
                    original_response=resp,
                    turn_number=turn,
                    relevance_score=min(score, 1.0),
                    match_type="keyword" if not entity_overlap else "entity",
                    matched_terms=list(overlap | entity_overlap),
                )

        return best_match if best_match and best_match.relevance_score >= 0.25 else None

    def _build_recall_response(
        self,
        recalled: RecalledContext,
        is_repeat: bool = False,
        emotion: str = "neutral",
    ) -> str:
        """Assemble a recall response from the matched context."""
        import random

        original = recalled.original_response

        # Strip action descriptions for cleaner recall
        # e.g., "*leans in*" → remove for the callback
        clean = re.sub(r'\*[^*]+\*', '', original).strip()

        # Truncate if very long (just use first 2 sentences)
        sentences = re.split(r'(?<=[.!?])\s+', clean)
        if len(sentences) > 2:
            summary = " ".join(sentences[:2])
        else:
            summary = clean

        if is_repeat:
            prefix = random.choice(_REPEAT_PREFIXES)
            return f"{prefix} {summary}"
        else:
            prefix = random.choice(_CALLBACK_PREFIXES)
            return f"{prefix} {summary}"

    def process(
        self,
        player_id: str,
        query: str,
        emotion: str = "neutral",
    ) -> Optional[Dict[str, Any]]:
        """
        Check if the player is referencing something the NPC said before.

        Returns:
            {
                "response": str,
                "source": "context_recall",
                "confidence": float,
                "recall_type": str,  # "callback" | "repeat" | "not_found"
                "original_turn": int,
                "matched_terms": list,
            }
            or None if no recall intent detected.
        """
        if not self._is_recall_query(query):
            return None

        # Check for repeat request
        q_lower = query.lower()
        is_repeat = any(t in q_lower for t in
                        {"again", "repeat", "say that again", "once more", "one more time"})

        # Find best matching prior response
        recalled = self._find_best_match(query, player_id)

        if not recalled:
            # Player asked about something but we can't find it
            import random
            return {
                "response": random.choice(_NO_RECALL_RESPONSES),
                "source": "context_recall",
                "confidence": 0.60,
                "recall_type": "not_found",
                "original_turn": None,
                "matched_terms": [],
            }

        response = self._build_recall_response(recalled, is_repeat=is_repeat, emotion=emotion)

        return {
            "response": response,
            "source": "context_recall",
            "confidence": min(0.70 + recalled.relevance_score * 0.25, 0.95),
            "recall_type": "repeat" if is_repeat else "callback",
            "original_turn": recalled.turn_number,
            "matched_terms": recalled.matched_terms,
        }

    def get_proactive_callback(
        self,
        player_id: str,
        current_topic_keywords: Set[str],
    ) -> Optional[str]:
        """
        Check if the NPC should proactively reference something it said
        earlier (e.g., "As I mentioned earlier about the road...").

        Called when the current conversation topic overlaps with a prior response.
        Returns a callback phrase or None.
        """
        if player_id not in self._response_history:
            return None

        history = self._response_history[player_id]
        if len(history) < 3:  # Need some conversation depth
            return None

        # Only check responses from 3+ turns ago (not too recent)
        current_turn = self._turn_counters.get(player_id, 0)
        for turn, resp, resp_keywords in history[:-2]:
            if current_turn - turn < 3:
                continue

            overlap = current_topic_keywords & resp_keywords
            if len(overlap) >= 2:
                import random
                # Truncate the original response for the callback
                clean = re.sub(r'\*[^*]+\*', '', resp).strip()
                sentences = re.split(r'(?<=[.!?])\s+', clean)
                first_sentence = sentences[0] if sentences else clean[:100]

                prefix = random.choice([
                    "As I mentioned before,",
                    "Going back to what I said earlier —",
                    "Remember when I told you",
                    "I said this before, but",
                ])
                return f"{prefix} {first_sentence}"

        return None
