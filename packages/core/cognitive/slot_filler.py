#!/usr/bin/env python3
"""
SlotFiller — Schema-Driven Variable Binding for Knowledge Cloud Patterns
AIVM Synthesus 2.0 — MVP for Hypothesis: "Retrieval + Chaining + Slot Filling ≈ Generation"

GOAL (locked):
  Prove that compositional Lego-building on retrieved patterns can match
  smooth interpolation on 175B weights IF the pattern space is dense enough
  and the routing is precise.

WHAT THIS MODULE DOES:
  Takes a ChainPlan from SequenceLinker and fills [entity], [emotion],
  [time], [topic] slots using deterministic resolution from world state
  and dialogue context.

SLOT RESOLUTION ORDER (highest precision first):
  1. World state (entities, locations, items already known)
  2. Recent dialogue memory (last N turns, extracted entities)
  3. Query extraction (regex + keyword lists for time, emotion)
  4. Context vector fallback (emotion from Swarm signals)

SLOT SCHEMA CONVENTION:
  Patterns declare slots in metadata:
    {
      "response": "I can help with [topic]. Tell me about [entity].",
      "slots": ["[topic]", "[entity]"],
      "constraints": {
        "entity": {"must_exist_in_world_state": true},
        "topic": {"values": ["combat", "magic", "trade"]}
      }
    }

  Required slots: [name] — must be filled or pattern is rejected
  Optional slots: [?name] — nice-to-have, removed if unfilled

EXTRACTION STRATEGIES:
  Entity:  Direct match against world_state["entities"]
  Time:    Regex ("morning|afternoon|evening|night|\\d+ o'clock")
  Emotion: Context vector emotion field OR keyword scan
  Topic:   Intent classification OR keyword list

HARD CONSTRAINT:
  If a required slot cannot be filled, the pattern is marked UNSATISFIABLE
  and SequenceLinker should downrank/reject it.

EXTENDING THIS MODULE:
  1. To add new slot types: extend _extract_by_type()
  2. To add new extractors: add methods, register in extractors dict
  3. To add NER: import spaCy model, call in _extract_entities_ner()
  4. To make learned: train slot→extractor mapping on dialogue logs

INTEGRATION POINT:
  Called from CognitiveEngine._synthesize_knowledge_response() AFTER
  SequenceLinker builds the chain, BEFORE text is rendered.
  Takes ChainPlan, returns {slot_name: filled_value} dict.

AUTHOR: Cascade
DATE: 2026-04-02
VERSION: MVP-1.0 (deterministic extraction, no ML models required)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# ── Data Classes ──────────────────────────────────────────────────────────

@dataclass
class SlotBinding:
    """A single slot with its filled value and provenance."""
    name: str
    value: str
    source: str  # "world_state", "dialogue_memory", "query_extraction", "context_fallback"
    confidence: float  # 0.0–1.0

@dataclass
class FillResult:
    """Result of filling slots for a pattern."""
    bindings: Dict[str, str] = field(default_factory=dict)  # slot_name → value (Legacy - first step only)
    step_bindings: List[Dict[str, str]] = field(default_factory=list) # Bindings per step
    unsatisfied_required: List[str] = field(default_factory=list)  # required slots we couldn't fill
    filled_optional: List[str] = field(default_factory=list)  # optional slots we did fill
    all_satisfied: bool = True  # True if all required slots filled

# ── SlotFiller Class ───────────────────────────────────────────────────────

class SlotFiller:
    """
    Fills [entity], [emotion], [time], [topic] slots in patterns.

    Usage:
        filler = SlotFiller()
        result = filler.fill_slots(
            chain_plan=plan,
            world_state={"entities": ["dragon", "castle"], "locations": ["Ironhaven"]},
            dialogue_memory=[{"entities": ["king"], "time": "morning"}],
            query="Tell me about the dragon this morning",
            context_vector={"intent": "ask_about", "emotion": "curious"}
        )
        # result.bindings = {"entity": "dragon", "time": "morning", "emotion": "curious"}
    """

    # Regex patterns for time extraction
    TIME_PATTERNS = [
        r"\b(morning|afternoon|evening|night|dawn|dusk|noon|midnight)\b",
        r"\b(\d{1,2})\s*(am|pm|o['\"]clock)\b",
        r"\b(yesterday|today|tomorrow|now|soon|later)\b",
    ]

    # Emotion keyword lists
    EMOTION_KEYWORDS = {
        "angry": ["angry", "furious", "mad", "rage", "hate", "annoyed"],
        "afraid": ["afraid", "scared", "terrified", "fear", "worried", "nervous"],
        "happy": ["happy", "joy", "glad", "pleased", "excited", "delighted"],
        "sad": ["sad", "sorrow", "depressed", "grief", "unhappy", "melancholy"],
        "curious": ["curious", "wonder", "interested", "intrigued", "how", "why"],
        "neutral": ["know", "tell", "what", "where", "when", "who"],
    }

    # Topic keyword lists
    TOPIC_KEYWORDS = {
        "combat": ["fight", "battle", "weapon", "attack", "defend", "kill", "sword"],
        "magic": ["spell", "magic", "wizard", "sorcerer", "enchant", "mana"],
        "trade": ["buy", "sell", "gold", "merchant", "price", "coin", "shop"],
        "lore": ["history", "legend", "story", "ancient", "tale", "myth"],
        "quest": ["quest", "mission", "task", "adventure", "journey"],
    }

    def __init__(self):
        """Initialize SlotFiller with deterministic extractors."""
        self._compiled_time_patterns = [re.compile(p, re.IGNORECASE) for p in self.TIME_PATTERNS]

    def fill_slots(
        self,
        chain_plan: Any,  # ChainPlan from SequenceLinker
        world_state: Dict[str, Any],
        dialogue_memory: Optional[List[Dict[str, Any]]] = None,
        query: str = "",
        context_vector: Optional[Dict[str, Any]] = None,
    ) -> FillResult:
        """
        Fill all slots in a chain plan using available sources.

        Args:
            chain_plan: ChainPlan with steps containing slots_required/slots_optional
            world_state: Dict with "entities", "locations", "items", etc.
            dialogue_memory: List of recent turns with extracted metadata
            query: Original player query text
            context_vector: 7 Swarm signals (intent, emotion, etc.)

        Returns:
            FillResult with bindings and satisfaction status
        """
        step_bindings: List[Dict[str, str]] = []
        unsatisfied_required: List[str] = []
        filled_optional: List[str] = []
        all_satisfied = True

        for step in chain_plan.steps:
            bindings: Dict[str, str] = {}
            # Extract preferred entity from pattern_id (e.g., "cloud_dragon")
            preferred_entity = step.pattern_id.replace("cloud_", "").replace("kg_", "")

            for slot in step.slots_required:
                slot_name = self._normalize_slot_name(slot)
                binding = self._resolve_slot(
                    slot_name=slot_name,
                    world_state=world_state,
                    dialogue_memory=dialogue_memory or [],
                    query=query,
                    context_vector=context_vector or {},
                    preferred_entity=preferred_entity
                )
                if binding:
                    bindings[slot_name] = binding.value
                else:
                    unsatisfied_required.append(f"{step.pattern_id}:{slot_name}")
                    all_satisfied = False

            for slot in step.slots_optional:
                slot_name = self._normalize_slot_name(slot)
                binding = self._resolve_slot(
                    slot_name=slot_name,
                    world_state=world_state,
                    dialogue_memory=dialogue_memory or [],
                    query=query,
                    context_vector=context_vector or {},
                    preferred_entity=preferred_entity
                )
                if binding:
                    bindings[slot_name] = binding.value
                    filled_optional.append(slot_name)

            step_bindings.append(bindings)

        # Legacy compatibility: 'bindings' returns the first step's bindings
        legacy_bindings = step_bindings[0] if step_bindings else {}

        return FillResult(
            bindings=legacy_bindings,
            step_bindings=step_bindings,
            unsatisfied_required=unsatisfied_required,
            filled_optional=filled_optional,
            all_satisfied=all_satisfied
        )

    def _normalize_slot_name(self, slot: str) -> str:
        """Normalize [slot] or [?slot] to slot name."""
        slot = slot.strip("[]")
        slot = slot.lstrip("?")
        return slot.lower()

    def _resolve_slot(
        self,
        slot_name: str,
        world_state: Dict[str, Any],
        dialogue_memory: List[Dict[str, Any]],
        query: str,
        context_vector: Dict[str, Any],
        preferred_entity: Optional[str] = None,
    ) -> Optional[SlotBinding]:
        """
        Resolve a single slot using priority order.
        Returns SlotBinding or None if unresolvable.
        """
        # Priority 1: World state (highest confidence)
        binding = self._extract_from_world_state(slot_name, world_state, preferred_entity)
        if binding:
            return binding

        # Priority 2: Dialogue memory
        binding = self._extract_from_dialogue_memory(slot_name, dialogue_memory)
        if binding:
            return binding

        # Priority 3: Query extraction
        binding = self._extract_from_query(slot_name, query, context_vector)
        if binding:
            return binding

        # Priority 4: Context vector fallback
        binding = self._extract_from_context(slot_name, context_vector)
        if binding:
            return binding

        return None

    def _extract_from_world_state(
        self,
        slot_name: str,
        world_state: Dict[str, Any],
        preferred_entity: Optional[str] = None,
    ) -> Optional[SlotBinding]:
        """Extract slot from world state entities/locations/items."""
        slot_lower = slot_name.lower()

        # SPECIAL CASE: if slot is 'entity', pick the most relevant one
        if slot_lower in ["entity", "subject", "target"]:
            # 1. Try preferred entity if provided (e.g. from the step context)
            if preferred_entity:
                for ent in world_state.get("entities", []):
                    if preferred_entity.lower() == ent.lower():
                        return SlotBinding(name=slot_name, value=ent.replace("_", " ").title(), source="world_state", confidence=1.0)

            # 2. Check if any entity from world_state is in the query (handled by _extract_from_query usually, but here for priority)

            entities = world_state.get("entities", [])
            if entities:
                # If only one entity, use it
                if len(entities) == 1:
                    return SlotBinding(name=slot_name, value=entities[0].replace("_", " ").title(), source="world_state", confidence=0.9)

                # If multiple, pick the one with most overlaps with the query keywords
                # (This is handled better in _extract_from_query, but we can do a quick check here)
                return SlotBinding(name=slot_name, value=entities[0].replace("_", " ").title(), source="world_state", confidence=0.8)

        # Check entities (legacy logic for specific slot names matching entity IDs)
        # Fix: Prioritize exact matches over substrings
        entities = world_state.get("entities", [])
        for entity in entities:
            if slot_lower == entity.lower():
                return SlotBinding(name=slot_name, value=entity, source="world_state", confidence=1.0)

        for entity in entities:
            if slot_lower in entity.lower() or entity.lower() in slot_lower:
                return SlotBinding(
                    name=slot_name,
                    value=entity,
                    source="world_state",
                    confidence=0.95
                )

        # Check locations
        for loc in world_state.get("locations", []):
            if slot_lower in loc.lower() or loc.lower() in slot_lower:
                return SlotBinding(
                    name=slot_name,
                    value=loc,
                    source="world_state",
                    confidence=0.95
                )

        # Check items
        for item in world_state.get("items", []):
            if slot_lower in item.lower() or item.lower() in slot_lower:
                return SlotBinding(
                    name=slot_name,
                    value=item,
                    source="world_state",
                    confidence=0.95
                )

        # Direct key match in world_state (e.g., world_state["emotion"])
        if slot_lower in world_state:
            val = world_state[slot_lower]
            if isinstance(val, str):
                return SlotBinding(
                    name=slot_name,
                    value=val,
                    source="world_state",
                    confidence=0.90
                )

        return None

    def _extract_from_dialogue_memory(
        self,
        slot_name: str,
        dialogue_memory: List[Dict[str, Any]],
    ) -> Optional[SlotBinding]:
        """Extract slot from recent dialogue (higher confidence for recent)."""
        slot_lower = slot_name.lower()

        for i, turn in enumerate(reversed(dialogue_memory[-5:])):  # Last 5 turns
            recency_boost = 0.9 - (i * 0.1)  # 0.9, 0.8, 0.7...

            # Check turn metadata
            for key in ["entities", "locations", "items", "time", "emotion", "topic"]:
                if key in turn:
                    vals = turn[key] if isinstance(turn[key], list) else [turn[key]]
                    for val in vals:
                        if slot_lower in str(val).lower():
                            return SlotBinding(
                                name=slot_name,
                                value=str(val),
                                source="dialogue_memory",
                                confidence=recency_boost
                            )

        return None

    def _extract_from_query(
        self,
        slot_name: str,
        query: str,
        context_vector: Dict[str, Any],
    ) -> Optional[SlotBinding]:
        """Extract slot from player query using type-specific extractors."""
        query_lower = query.lower()
        slot_lower = slot_name.lower()

        # Time extraction
        if slot_lower == "time":
            return self._extract_time(query)

        # Emotion extraction from query text
        if slot_lower == "emotion":
            return self._extract_emotion_from_query(query)

        # Topic extraction
        if slot_lower == "topic":
            return self._extract_topic(query, context_vector)

        # Entity extraction (naive: find capitalized words or quoted phrases)
        if slot_lower in ["entity", "subject", "target"]:
            return self._extract_entity(query)

        # Fallback: keyword match
        words = query_lower.split()
        for word in words:
            if slot_lower in word or word in slot_lower:
                return SlotBinding(
                    name=slot_name,
                    value=word,
                    source="query_extraction",
                    confidence=0.5
                )

        return None

    def _extract_time(self, query: str) -> Optional[SlotBinding]:
        """Extract time reference from query."""
        for pattern in self._compiled_time_patterns:
            match = pattern.search(query)
            if match:
                return SlotBinding(
                    name="time",
                    value=match.group(1).lower(),
                    source="query_extraction",
                    confidence=0.8
                )
        return None

    def _extract_emotion_from_query(self, query: str) -> Optional[SlotBinding]:
        """Extract emotion from query keywords."""
        query_lower = query.lower()

        for emotion, keywords in self.EMOTION_KEYWORDS.items():
            for keyword in keywords:
                if keyword in query_lower:
                    return SlotBinding(
                        name="emotion",
                        value=emotion,
                        source="query_extraction",
                        confidence=0.7
                    )
        return None

    def _extract_topic(self, query: str, context_vector: Dict[str, Any]) -> Optional[SlotBinding]:
        """Extract topic from query or intent."""
        query_lower = query.lower()

        # First: check intent from context vector
        intent = context_vector.get("intent", "")
        if intent:
            # Map intent to topic
            intent_topic_map = {
                "combat": "combat",
                "shop_buy": "trade",
                "shop_sell": "trade",
                "ask_lore": "lore",
                "lore_query": "lore",
                "ask_history": "lore",
                "quest_accept": "quest",
            }
            if intent in intent_topic_map:
                return SlotBinding(
                    name="topic",
                    value=intent_topic_map[intent],
                    source="context_fallback",
                    confidence=0.8
                )

        # Second: keyword matching
        for topic, keywords in self.TOPIC_KEYWORDS.items():
            for keyword in keywords:
                if keyword in query_lower:
                    return SlotBinding(
                        name="topic",
                        value=topic,
                        source="query_extraction",
                        confidence=0.75
                    )

        return None

    def _extract_entity(self, query: str) -> Optional[SlotBinding]:
        """Extract entity (capitalized words or quoted phrases)."""
        # Look for quoted phrases first
        quoted = re.findall(r'"([^"]+)"', query)
        if quoted:
            return SlotBinding(
                name="entity",
                value=quoted[0],
                source="query_extraction",
                confidence=0.7
            )

        # Command verbs to skip
        SKIP_VERBS = {"Tell", "Show", "What", "Where", "When", "How", "Who", "Explain", "List", "About", "Tell me", "Does"}

        # Improved: Look for multi-word capitalized phrases
        # Find all sequences of capitalized words
        phrases = re.findall(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', query)
        for phrase in phrases:
            if phrase in SKIP_VERBS:
                continue
            if len(phrase) > 3:
                return SlotBinding(
                    name="entity",
                    value=phrase,
                    source="query_extraction",
                    confidence=0.7
                )

        # Fallback to single capitalized words
        words = query.split()
        for word in words:
            clean = re.sub(r'[^\w]', '', word)
            if clean and clean[0].isupper() and len(clean) > 2:
                if clean in SKIP_VERBS:
                    continue
                return SlotBinding(
                    name="entity",
                    value=clean,
                    source="query_extraction",
                    confidence=0.6
                )

        return None

    def _extract_from_context(
        self,
        slot_name: str,
        context_vector: Dict[str, Any],
    ) -> Optional[SlotBinding]:
        """Fallback extraction from context vector (lowest confidence)."""
        slot_lower = slot_name.lower()

        # Emotion from context
        if slot_lower == "emotion":
            emotion = context_vector.get("emotion", context_vector.get("player_emotion", "neutral"))
            if emotion:
                return SlotBinding(
                    name=slot_name,
                    value=emotion,
                    source="context_fallback",
                    confidence=0.5
                )

        # Time fallback
        if slot_lower == "time":
            return SlotBinding(
                name=slot_name,
                value="now",
                source="context_fallback",
                confidence=0.3
            )

        # Intent as topic fallback
        if slot_lower == "topic" or slot_lower == "intent":
            intent = context_vector.get("intent", "")
            if intent:
                return SlotBinding(
                    name=slot_name,
                    value=intent,
                    source="context_fallback",
                    confidence=0.4
                )

        return None

# ── Utility Functions ──────────────────────────────────────────────────────

def create_slot_schema_example() -> Dict[str, Any]:
    """
    Example of how patterns should declare slots in Knowledge Cloud entries.

    This shows the convention for the MVP. Real deployment would enforce
    this schema at ingestion time.
    """
    return {
        "entity_id": "dragon_warning",
        "entity": "Dragon Warning",
        "description": "[entity] is a dangerous [topic] creature. Approach with [emotion] caution.",
        "slots": ["[entity]", "[topic]", "[emotion]"],
        "constraints": {
            "entity": {"must_exist_in_world_state": True},
            "topic": {"values": ["combat", "lore"]},
            "emotion": {"fallback": "neutral"}
        },
        "facts": [
            "Breathes fire",
            "Guards treasure"
        ]
    }

# ── Module Test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Quick sanity test
    logging.basicConfig(level=logging.INFO)

    from dataclasses import dataclass, field

    @dataclass
    class MockStep:
        slots_required: List[str] = field(default_factory=list)
        slots_optional: List[str] = field(default_factory=list)

    @dataclass
    class MockPlan:
        steps: List[MockStep]

    # Create test data
    plan = MockPlan(steps=[
        MockStep(slots_required=["[entity]", "[topic]"], slots_optional=["[emotion]"]),
        MockStep(slots_required=["[time]"], slots_optional=[]),
    ])

    world_state = {
        "entities": ["dragon", "Ironhaven"],
        "locations": ["castle"],
        "emotion": "curious"
    }

    dialogue_memory = [
        {"entities": ["king"], "time": "morning"}
    ]

    query = "Tell me about the dragon in the castle this morning"

    context_vector = {
        "intent": "ask_about",
        "emotion": "curious",
        "player_emotion": "interested"
    }

    # Fill slots
    filler = SlotFiller()
    result = filler.fill_slots(plan, world_state, dialogue_memory, query, context_vector)

    print(f"\nSlot Fill Result:")
    print(f"  All satisfied: {result.all_satisfied}")
    print(f"  Bindings: {result.bindings}")
    print(f"  Unsatisfied required: {result.unsatisfied_required}")
    print(f"  Filled optional: {result.filled_optional}")
