"""
Module 1: Conversation Tracker
"What did we just talk about?"

Maintains a rolling context window of the current conversation.
Tracks: last N messages, active topic, mentioned entities, open questions.
Enables multi-turn context without any inference.

Cost: ~0.1ms per query, ~500 bytes RAM per conversation
"""

from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple


class Topic(Enum):
    SHOPPING = "shopping"
    QUEST = "quest"
    BACKSTORY = "backstory"
    WORLD_INFO = "world_info"
    COMBAT = "combat"
    SOCIAL = "social"
    FAREWELL = "farewell"
    UNKNOWN = "unknown"


# Topic detection rules: keyword sets → topic
_TOPIC_RULES: List[Tuple[Set[str], Topic]] = [
    ({"buy", "sell", "price", "cost", "gold", "shop", "wares", "sword", "potion",
      "weapon", "armor", "item", "haggle", "discount", "cheap", "expensive",
      "appraise", "trade", "merchant", "inventory"}, Topic.SHOPPING),
    ({"quest", "job", "work", "task", "mission", "caravan", "missing", "deliver",
      "escort", "reward", "danger", "road", "bandits", "rescue", "help",
      "investigate", "find"}, Topic.QUEST),
    ({"story", "past", "history", "scar", "remember", "years", "ago", "war",
      "wife", "family", "father", "mother", "child", "born", "young",
      "background", "origin", "elara", "yourself", "married"}, Topic.BACKSTORY),
    ({"town", "city", "duke", "guard", "tavern", "inn", "mage", "guild",
      "rumor", "news", "gossip", "politics", "kingdom", "where", "directions",
      "map", "location"}, Topic.WORLD_INFO),
    ({"fight", "attack", "kill", "sword", "shield", "battle", "enemy",
      "monster", "danger", "hurt", "wounded", "die", "death"}, Topic.COMBAT),
    ({"hello", "hi", "hey", "greetings", "goodbye", "bye", "farewell",
      "thanks", "thank", "sorry"}, Topic.SOCIAL),
    ({"goodbye", "bye", "farewell", "leave", "leaving", "go"}, Topic.FAREWELL),
]


@dataclass
class TrackedEntity:
    """A named entity mentioned in conversation."""
    name: str
    entity_type: str  # ITEM, NPC, PLACE, CONCEPT
    last_mentioned: float = 0.0
    mention_count: int = 0


@dataclass
class ConversationState:
    """The rolling state of one player↔NPC conversation."""
    player_messages: deque = field(default_factory=lambda: deque(maxlen=5))
    npc_responses: deque = field(default_factory=lambda: deque(maxlen=5))
    active_topic: Topic = Topic.UNKNOWN
    previous_topic: Topic = Topic.UNKNOWN
    mentioned_entities: Dict[str, TrackedEntity] = field(default_factory=dict)
    open_questions: List[str] = field(default_factory=list)
    turn_count: int = 0
    last_interaction: float = 0.0
    topic_history: deque = field(default_factory=lambda: deque(maxlen=10))

    def reset_if_stale(self, timeout_seconds: float = 300.0) -> bool:
        """Reset conversation if player has been away too long."""
        if self.last_interaction > 0 and (time.time() - self.last_interaction) > timeout_seconds:
            self.player_messages.clear()
            self.npc_responses.clear()
            self.active_topic = Topic.UNKNOWN
            self.previous_topic = Topic.UNKNOWN
            self.open_questions.clear()
            self.turn_count = 0
            return True
        return False


# Stop words for content extraction
_STOP_WORDS = {
    "the", "a", "an", "is", "it", "of", "in", "to", "and", "or", "i", "me", "my",
    "you", "your", "do", "does", "did", "can", "could", "would", "should",
    "what", "how", "why", "when", "where", "who", "that", "this", "if",
    "about", "for", "with", "on", "at", "by", "from", "up", "out", "so",
    "be", "been", "am", "are", "was", "were", "have", "has", "had", "not",
    "but", "just", "more", "very", "ever", "one", "thing", "like", "any",
    "some", "no", "all", "them", "they", "we", "he", "she", "its",
    "don't", "there", "i'll", "got", "get", "know", "think", "tell",
    "really", "much", "way", "too", "also", "here", "now", "then",
    "going", "want", "need", "make", "let", "go", "come", "see",
    "take", "give", "say", "said", "look", "well", "back", "even",
    "still", "us", "our", "his", "her", "their", "him", "it's", "i'm",
}


class ConversationTracker:
    """
    Module 1 of the Cognitive Engine.
    Tracks multi-turn conversation state per player-NPC pair.
    """

    def __init__(self, known_entities: Optional[Dict[str, str]] = None):
        """
        Args:
            known_entities: Dict of entity_name → entity_type from bio/patterns.
                           e.g. {"Tomás": "NPC", "Silvermoor": "PLACE", "silk": "ITEM"}
        """
        self._conversations: Dict[str, ConversationState] = {}
        self._known_entities = {k.lower(): TrackedEntity(name=k, entity_type=v)
                                for k, v in (known_entities or {}).items()}
        # Pronoun resolution targets
        self._pronoun_map = {"it", "that", "this", "those", "them", "they", "one"}

    def _get_state(self, player_id: str) -> ConversationState:
        if player_id not in self._conversations:
            self._conversations[player_id] = ConversationState()
        state = self._conversations[player_id]
        state.reset_if_stale()
        return state

    @staticmethod
    def _extract_keywords(text: str) -> Set[str]:
        """Extract content words from text."""
        return set(re.findall(r'[a-z]+', text.lower())) - _STOP_WORDS

    def _detect_topic(self, keywords: Set[str]) -> Topic:
        """Match keywords against topic rules, return best match."""
        best_topic = Topic.UNKNOWN
        best_overlap = 0
        for rule_keywords, topic in _TOPIC_RULES:
            overlap = len(keywords & rule_keywords)
            if overlap > best_overlap:
                best_overlap = overlap
                best_topic = topic
        return best_topic if best_overlap >= 1 else Topic.UNKNOWN

    def _extract_entities(self, text: str, state: ConversationState) -> List[TrackedEntity]:
        """Find named entities in text using known entity list + capitalization heuristic."""
        found = []
        text_lower = text.lower()

        # Check known entities
        for key, entity in self._known_entities.items():
            if key in text_lower:
                if key not in state.mentioned_entities:
                    state.mentioned_entities[key] = TrackedEntity(
                        name=entity.name,
                        entity_type=entity.entity_type,
                    )
                ent = state.mentioned_entities[key]
                ent.last_mentioned = time.time()
                ent.mention_count += 1
                found.append(ent)

        # Capitalized words that aren't sentence-starts (simple NER heuristic)
        words = text.split()
        for i, w in enumerate(words):
            if i > 0 and w[0].isupper() and w.lower() not in _STOP_WORDS:
                clean = re.sub(r'[^a-zA-Z]', '', w)
                if len(clean) > 2:
                    key = clean.lower()
                    if key not in state.mentioned_entities and key not in self._known_entities:
                        state.mentioned_entities[key] = TrackedEntity(
                            name=clean,
                            entity_type="UNKNOWN",
                        )
                    if key in state.mentioned_entities:
                        ent = state.mentioned_entities[key]
                        ent.last_mentioned = time.time()
                        ent.mention_count += 1
                        found.append(ent)
        return found

    def _resolve_pronouns(self, text: str, state: ConversationState) -> Optional[str]:
        """
        Resolve pronouns like 'it', 'that' to the most recently mentioned entity.
        Returns the resolved entity name, or None.
        """
        words = set(text.lower().split())
        if not words & self._pronoun_map:
            return None

        # Find most recently mentioned entity
        if not state.mentioned_entities:
            return None

        most_recent = max(
            state.mentioned_entities.values(),
            key=lambda e: e.last_mentioned,
            default=None
        )
        return most_recent.name if most_recent and most_recent.last_mentioned > 0 else None

    def _detect_questions(self, text: str) -> List[str]:
        """Detect if player asked a question (for open_questions tracking)."""
        questions = []
        # Split on sentence boundaries
        sentences = re.split(r'[.!?]+', text)
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            # Check for question indicators
            q_words = {"what", "how", "why", "when", "where", "who", "which", "can", "could",
                        "would", "do", "does", "is", "are", "will"}
            first_word = s.split()[0].lower() if s.split() else ""
            if first_word in q_words or s.endswith("?"):
                questions.append(s)
        return questions

    def process(self, player_id: str, player_message: str) -> Dict:
        """
        Process a player message and update conversation state.

        Returns a context dict that other modules can use:
        {
            "active_topic": Topic,
            "previous_topic": Topic,
            "keywords": set,
            "entities_mentioned": [TrackedEntity],
            "pronoun_resolution": str or None,
            "turn_count": int,
            "is_returning": bool,  (had previous conversation)
            "open_questions": [str],
            "last_npc_response": str or None,
        }
        """
        state = self._get_state(player_id)

        # Extract info from message
        keywords = self._extract_keywords(player_message)
        topic = self._detect_topic(keywords)
        entities = self._extract_entities(player_message, state)
        pronoun_target = self._resolve_pronouns(player_message, state)
        questions = self._detect_questions(player_message)

        # Update state
        is_returning = state.turn_count > 0
        state.player_messages.append(player_message)
        state.previous_topic = state.active_topic
        if topic != Topic.UNKNOWN:
            state.active_topic = topic
            state.topic_history.append(topic)
        state.open_questions = questions  # Replace with current questions
        state.turn_count += 1
        state.last_interaction = time.time()

        return {
            "active_topic": state.active_topic,
            "previous_topic": state.previous_topic,
            "keywords": keywords,
            "entities_mentioned": entities,
            "pronoun_resolution": pronoun_target,
            "turn_count": state.turn_count,
            "is_returning": is_returning,
            "is_topic_change": (state.previous_topic != Topic.UNKNOWN
                                and topic != Topic.UNKNOWN
                                and state.previous_topic != topic),
            "open_questions": questions,
            "last_npc_response": (state.npc_responses[-1]
                                  if state.npc_responses else None),
            "conversation_depth": len(state.player_messages),
        }

    def record_npc_response(self, player_id: str, response: str):
        """Record what the NPC said (for context in next turn)."""
        state = self._get_state(player_id)
        state.npc_responses.append(response)

    def get_state(self, player_id: str) -> ConversationState:
        """Get the raw conversation state for debugging."""
        return self._get_state(player_id)
