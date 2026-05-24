#!/usr/bin/env python3
"""
DialogueMemory — Persistent conversation context for slot filling and multi-turn chains.
AIVM Synthesus 2.0 — Enhanced memory system for contextual NPC responses.

WHAT THIS MODULE DOES:
  Maintains conversation history with entity tracking, slot bindings, and context state.
  Provides memory for multi-turn conversations and persistent slot resolution.
  Enables SequenceLinker to build chains that reference previous turns.

MEMORY STRUCTURE:
  {
    "conversation_id": "session_123",
    "turns": [
      {
        "turn_id": 1,
        "timestamp": "2026-04-06T10:00:00Z",
        "query": "Tell me about the dragon",
        "response": "Dragons are fearsome creatures...",
        "slots_filled": {"entity": "dragon", "emotion": "curious"},
        "entities_mentioned": ["dragon"],
        "context_state": {"intent": "ask_about", "emotion": "curious"},
        "chain_used": ["dragon", "combat"],
        "satisfaction_score": 4.2
      }
    ],
    "persistent_slots": {
      "entity": "dragon",  // Last mentioned entity
      "location": "Ironhaven",  // Current location context
      "topic": "combat"  // Ongoing conversation topic
    },
    "entity_relationships": {
      "dragon": {"mentioned_count": 3, "last_turn": 5},
      "Ironhaven": {"mentioned_count": 8, "last_turn": 12}
    }
  }

INTEGRATION POINTS:
  - SlotFiller._extract_from_dialogue_memory() — Reads recent turns
  - SequenceLinker.build_chain() — Uses persistent context for transitions
  - CognitiveEngine — Stores new turns after response generation

MEMORY POLICIES:
  - Keep last 10 turns in active memory
  - Persist entity relationships across sessions
  - Clear conversation context after 30 minutes of inactivity
  - Compress old turns to summaries after 50 turns

AUTHOR: Cascade
DATE: 2026-04-06
VERSION: v1.0 - Multi-turn conversation support
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ── Data Classes ──────────────────────────────────────────────────────────

@dataclass
class DialogueTurn:
    """A single turn in the conversation."""
    turn_id: int
    timestamp: str
    query: str
    response: str
    slots_filled: Dict[str, str] = field(default_factory=dict)
    entities_mentioned: List[str] = field(default_factory=list)
    context_state: Dict[str, Any] = field(default_factory=dict)
    chain_used: List[str] = field(default_factory=list)
    satisfaction_score: float = 0.0

@dataclass
class EntityMemory:
    """Persistent memory for an entity across conversations."""
    entity_id: str
    mentioned_count: int = 0
    last_turn: int = 0
    first_mentioned: str = ""
    last_mentioned: str = ""
    associated_slots: Dict[str, str] = field(default_factory=dict)
    relationship_score: float = 0.0  # How central to conversation

@dataclass
class ConversationContext:
    """Current conversation state."""
    conversation_id: str
    turns: List[DialogueTurn] = field(default_factory=list)
    persistent_slots: Dict[str, str] = field(default_factory=dict)
    entity_relationships: Dict[str, EntityMemory] = field(default_factory=dict)
    last_activity: str = ""
    turn_counter: int = 0

# ── DialogueMemory Class ─────────────────────────────────────────────────

class DialogueMemory:
    """
    Manages persistent conversation context for enhanced slot filling.

    Usage:
        memory = DialogueMemory("data/dialogue_memory")
        context = memory.load_context("player_123")

        # Add new turn
        turn = DialogueTurn(
            turn_id=context.turn_counter + 1,
            timestamp=datetime.now().isoformat(),
            query="Tell me about dragons",
            response="Dragons are...",
            slots_filled={"entity": "dragon"},
            entities_mentioned=["dragon"]
        )
        memory.add_turn(context, turn)

        # Get recent context for slot filling
        recent_turns = memory.get_recent_turns(context, limit=5)
    """

    def __init__(self, storage_path: str = "data/dialogue_memory"):
        """Initialize memory system with persistent storage."""
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # In-memory cache for active conversations
        self._active_contexts: Dict[str, ConversationContext] = {}

        # Memory policies
        self.MAX_ACTIVE_TURNS = 10
        self.MAX_TOTAL_TURNS = 50
        self.INACTIVITY_TIMEOUT_MINUTES = 30
        self.COMPRESSION_THRESHOLD = 20

    def load_context(self, conversation_id: str) -> ConversationContext:
        """
        Load or create conversation context.
        Returns cached context if available, otherwise loads from disk.
        """
        # Check cache first
        if conversation_id in self._active_contexts:
            context = self._active_contexts[conversation_id]

            # Check for inactivity timeout
            if self._is_inactive(context):
                logger.info(f"Conversation {conversation_id} inactive, clearing context")
                self.clear_context(conversation_id)
                context = self._create_new_context(conversation_id)
            else:
                return context

        # Load from disk
        context_file = self.storage_path / f"{conversation_id}.json"
        if context_file.exists():
            try:
                with open(context_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Reconstruct context
                turns = [DialogueTurn(**turn_data) for turn_data in data.get("turns", [])]
                entity_relationships = {}
                for entity_id, mem_data in data.get("entity_relationships", {}).items():
                    entity_relationships[entity_id] = EntityMemory(**mem_data)

                context = ConversationContext(
                    conversation_id=conversation_id,
                    turns=turns,
                    persistent_slots=data.get("persistent_slots", {}),
                    entity_relationships=entity_relationships,
                    last_activity=data.get("last_activity", ""),
                    turn_counter=data.get("turn_counter", len(turns))
                )

                # Update last_activity to now so loaded context isn't flagged inactive
                # before it gets used (conversation may have ended in the past)
                context.last_activity = datetime.now().isoformat()

                # Apply memory policies
                context = self._apply_memory_policies(context)

            except Exception as e:
                logger.error(f"Failed to load context {conversation_id}: {e}")
                context = self._create_new_context(conversation_id)
        else:
            context = self._create_new_context(conversation_id)

        # Cache it
        self._active_contexts[conversation_id] = context
        return context

    def _create_new_context(self, conversation_id: str) -> ConversationContext:
        """Create a new empty conversation context."""
        now = datetime.now().isoformat()
        return ConversationContext(
            conversation_id=conversation_id,
            turns=[],
            persistent_slots={},
            entity_relationships={},
            last_activity=now,
            turn_counter=0
        )

    def add_turn(self, context: ConversationContext, turn: DialogueTurn) -> None:
        """
        Add a new turn to the conversation and update persistent state.
        """
        # Update turn ID and timestamp if not set
        if turn.turn_id == 0:
            context.turn_counter += 1
            turn.turn_id = context.turn_counter
        else:
            # Ensure counter stays ahead of any manually-assigned turn IDs
            if turn.turn_id >= context.turn_counter:
                context.turn_counter = turn.turn_id + 1

        if not turn.timestamp:
            turn.timestamp = datetime.now().isoformat()

        # Add to turns
        context.turns.append(turn)
        context.last_activity = turn.timestamp

        # Update entity relationships
        self._update_entity_relationships(context, turn)

        # Update persistent slots
        self._update_persistent_slots(context, turn)

        # Apply memory policies
        context = self._apply_memory_policies(context)

        # Save to disk
        self._save_context(context)

    def _update_entity_relationships(self, context: ConversationContext, turn: DialogueTurn) -> None:
        """Update entity mention counts and relationships."""
        for entity in turn.entities_mentioned:
            if entity not in context.entity_relationships:
                context.entity_relationships[entity] = EntityMemory(
                    entity_id=entity,
                    first_mentioned=turn.timestamp,
                    mentioned_count=0
                )

            mem = context.entity_relationships[entity]
            mem.mentioned_count += 1
            mem.last_turn = turn.turn_id
            mem.last_mentioned = turn.timestamp

            # Update associated slots
            for slot_name, slot_value in turn.slots_filled.items():
                if slot_name in ["entity", "location", "item"]:
                    mem.associated_slots[slot_name] = slot_value

            # Calculate relationship score (recency + frequency)
            turns_since_last = context.turn_counter - mem.last_turn
            mem.relationship_score = mem.mentioned_count / (1 + turns_since_last * 0.1)

    def _update_persistent_slots(self, context: ConversationContext, turn: DialogueTurn) -> None:
        """Update persistent slot values based on conversation flow."""
        # Update slots that tend to persist (location, topic, emotion)
        persistent_keys = ["location", "topic", "emotion", "entity"]

        for slot_name, slot_value in turn.slots_filled.items():
            if slot_name in persistent_keys:
                context.persistent_slots[slot_name] = slot_value

        # If no entity mentioned recently, decay old persistent entity
        recent_entities = set()
        for t in context.turns[-3:]:  # Last 3 turns
            recent_entities.update(t.entities_mentioned)

        if "entity" in context.persistent_slots:
            if context.persistent_slots["entity"] not in recent_entities:
                # Decay after 3 turns without mention
                context.persistent_slots.pop("entity", None)

    def _apply_memory_policies(self, context: ConversationContext) -> ConversationContext:
        """Apply memory management policies to prevent unbounded growth."""
        turns = context.turns

        # Keep only recent turns
        if len(turns) > self.MAX_ACTIVE_TURNS:
            # Keep last 5, and compress older ones
            recent_turns = turns[-5:]
            older_turns = turns[:-5]

            # Compress older turns into summaries (keep every 3rd turn)
            compressed = []
            for i, turn in enumerate(older_turns):
                if i % 3 == 0:  # Keep every 3rd turn
                    compressed.append(turn)

            context.turns = compressed + recent_turns

        # Compress very old conversations
        if len(turns) > self.MAX_TOTAL_TURNS:
            # Summarize first half into a single summary turn
            summary_turn = self._create_summary_turn(turns[:len(turns)//2])
            context.turns = [summary_turn] + turns[len(turns)//2:]

        return context

    def _create_summary_turn(self, old_turns: List[DialogueTurn]) -> DialogueTurn:
        """Create a summary turn from multiple old turns."""
        all_entities = set()
        all_slots = {}
        total_satisfaction = 0

        for turn in old_turns:
            all_entities.update(turn.entities_mentioned)
            all_slots.update(turn.slots_filled)
            total_satisfaction += turn.satisfaction_score

        return DialogueTurn(
            turn_id=old_turns[0].turn_id,
            timestamp=old_turns[0].timestamp,
            query="[CONVERSATION SUMMARY]",
            response=f"Previous conversation covered: {', '.join(all_entities)}",
            slots_filled=all_slots,
            entities_mentioned=list(all_entities),
            context_state={},
            chain_used=[],
            satisfaction_score=total_satisfaction / len(old_turns) if old_turns else 0
        )

    def get_recent_turns(self, context: ConversationContext, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get recent turns formatted for slot filler consumption.
        Returns list of turn dicts with metadata.
        """
        recent_turns = context.turns[-limit:]

        formatted = []
        for turn in recent_turns:
            formatted_turn = {
                "turn_id": turn.turn_id,
                "query": turn.query,
                "response": turn.response,
                "entities": turn.entities_mentioned,
                "slots": turn.slots_filled,
                "context": turn.context_state,
                "timestamp": turn.timestamp
            }
            formatted.append(formatted_turn)

        return formatted

    def get_persistent_slots(self, context: ConversationContext) -> Dict[str, str]:
        """Get current persistent slot values."""
        return context.persistent_slots.copy()

    def get_top_entities(self, context: ConversationContext, limit: int = 5) -> List[str]:
        """Get most relevant entities by relationship score."""
        entities = list(context.entity_relationships.values())
        entities.sort(key=lambda x: x.relationship_score, reverse=True)
        return [e.entity_id for e in entities[:limit]]

    def _is_inactive(self, context: ConversationContext) -> bool:
        """Check if conversation has been inactive too long."""
        if not context.last_activity:
            return False

        last_time = datetime.fromisoformat(context.last_activity)
        now = datetime.now()
        # Strip timezone info from both to make comparison consistent
        if last_time.tzinfo is not None:
            last_time = last_time.replace(tzinfo=None)
        time_since = now - last_time
        return time_since > timedelta(minutes=self.INACTIVITY_TIMEOUT_MINUTES)

    def clear_context(self, conversation_id: str) -> None:
        """Clear conversation context from memory and disk."""
        if conversation_id in self._active_contexts:
            del self._active_contexts[conversation_id]

        context_file = self.storage_path / f"{conversation_id}.json"
        if context_file.exists():
            context_file.unlink()

    def _save_context(self, context: ConversationContext) -> None:
        """Save context to disk."""
        context_file = self.storage_path / f"{context.conversation_id}.json"

        # Convert to serializable format
        data = {
            "conversation_id": context.conversation_id,
            "turns": [self._turn_to_dict(turn) for turn in context.turns],
            "persistent_slots": context.persistent_slots,
            "entity_relationships": {eid: self._entity_to_dict(mem)
                                   for eid, mem in context.entity_relationships.items()},
            "last_activity": context.last_activity,
            "turn_counter": context.turn_counter
        }

        try:
            with open(context_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save context {context.conversation_id}: {e}")

    def _turn_to_dict(self, turn: DialogueTurn) -> Dict[str, Any]:
        """Convert DialogueTurn to dict for JSON serialization."""
        return {
            "turn_id": turn.turn_id,
            "timestamp": turn.timestamp,
            "query": turn.query,
            "response": turn.response,
            "slots_filled": turn.slots_filled,
            "entities_mentioned": turn.entities_mentioned,
            "context_state": turn.context_state,
            "chain_used": turn.chain_used,
            "satisfaction_score": turn.satisfaction_score
        }

    def _entity_to_dict(self, entity: EntityMemory) -> Dict[str, Any]:
        """Convert EntityMemory to dict for JSON serialization."""
        return {
            "entity_id": entity.entity_id,
            "mentioned_count": entity.mentioned_count,
            "last_turn": entity.last_turn,
            "first_mentioned": entity.first_mentioned,
            "last_mentioned": entity.last_mentioned,
            "associated_slots": entity.associated_slots,
            "relationship_score": entity.relationship_score
        }

# ── Integration Helper ───────────────────────────────────────────────────

def extract_entities_from_text(text: str) -> List[str]:
    """Extract likely entity mentions from text (simple implementation)."""
    import re

    entities = []

    # Find quoted phrases
    quoted = re.findall(r'"([^"]+)"', text)
    entities.extend(quoted)

    # Find capitalized words (proper nouns)
    words = text.split()
    for word in words:
        clean = re.sub(r'[^\w]', '', word)
        if clean and clean[0].isupper() and len(clean) > 2:
            entities.append(clean)

    # Remove duplicates while preserving order
    seen = set()
    unique_entities = []
    for entity in entities:
        if entity.lower() not in seen:
            seen.add(entity.lower())
            unique_entities.append(entity)

    return unique_entities

# ── Module Test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Quick test
    logging.basicConfig(level=logging.INFO)

    memory = DialogueMemory("data/dialogue_memory")

    # Create test context
    context = memory.load_context("test_conversation")

    # Add some turns
    turns_data = [
        {
            "query": "Tell me about dragons",
            "response": "Dragons are fearsome creatures of legend.",
            "slots_filled": {"entity": "dragon", "emotion": "curious"},
            "entities_mentioned": ["dragon"],
            "context_state": {"intent": "ask_about"},
            "satisfaction_score": 4.5
        },
        {
            "query": "Are they dangerous?",
            "response": "Yes, dragons breathe fire and guard treasure.",
            "slots_filled": {"entity": "dragon", "topic": "combat"},
            "entities_mentioned": ["dragon"],
            "context_state": {"intent": "ask_danger"},
            "satisfaction_score": 4.2
        },
        {
            "query": "What about Ironhaven?",
            "response": "Ironhaven is a bustling trade city.",
            "slots_filled": {"entity": "Ironhaven", "topic": "trade"},
            "entities_mentioned": ["Ironhaven"],
            "context_state": {"intent": "ask_about"},
            "satisfaction_score": 4.8
        }
    ]

    for turn_data in turns_data:
        turn = DialogueTurn(
            turn_id=0,  # Will be auto-assigned
            timestamp="",
            **turn_data
        )
        memory.add_turn(context, turn)

    # Test retrieval
    recent = memory.get_recent_turns(context, limit=2)
    persistent = memory.get_persistent_slots(context)
    top_entities = memory.get_top_entities(context, limit=3)

    print(f"\nRecent turns: {len(recent)}")
    print(f"Persistent slots: {persistent}")
    print(f"Top entities: {top_entities}")
    print(f"Total turns in context: {len(context.turns)}")
    print(f"Entity relationships: {list(context.entity_relationships.keys())}")
