"""
Module 8: Knowledge Graph
A structured entity knowledge base for each NPC. Stores what the NPC
KNOWS about people, places, items, factions, and events — with
relationship-aware response selection.

The NPC doesn't look things up in a database — it "remembers" things
it personally knows, colored by its own perspective and emotion.

Knowledge is loaded from a per-character knowledge.json file.

Cost: ~0.1ms per query, ~20 KB RAM per NPC, zero GPU.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


class EntityType(Enum):
    PERSON = "person"
    PLACE = "place"
    ITEM = "item"
    FACTION = "faction"
    EVENT = "event"
    CONCEPT = "concept"


class KnowledgeDepth(Enum):
    """How well the NPC knows this entity."""
    INTIMATE = "intimate"      # Family, close associates
    FAMILIAR = "familiar"      # Regular interactions
    ACQUAINTED = "acquainted"  # Knows of them
    RUMOR = "rumor"            # Heard about, uncertain
    UNKNOWN = "unknown"        # Doesn't know


@dataclass
class EntityKnowledge:
    """What one NPC knows about one entity."""
    entity_id: str
    entity_type: EntityType
    display_name: str
    depth: KnowledgeDepth = KnowledgeDepth.ACQUAINTED

    # Core knowledge (what the NPC says when asked directly)
    description: str = ""           # Main response when asked about this entity
    relationship_to_npc: str = ""   # "my driver", "a regular customer", "the duke"

    # Emotion-variant descriptions
    emotion_variants: Dict[str, str] = field(default_factory=dict)

    # Related entities (for multi-hop queries)
    related_entities: List[str] = field(default_factory=list)

    # Alternate names / synonyms for matching
    aliases: List[str] = field(default_factory=list)

    # Topics this entity is relevant to (for context-aware surfacing)
    topics: List[str] = field(default_factory=list)

    # Trust-gated knowledge (only shared at certain relationship levels)
    secret_description: str = ""    # Shared only with trusted players
    trust_threshold: float = 70.0   # Trust needed for secret info


# ── Entity Type String → Enum Mapping ──
_TYPE_MAP = {
    "person": EntityType.PERSON,
    "place": EntityType.PLACE,
    "item": EntityType.ITEM,
    "faction": EntityType.FACTION,
    "event": EntityType.EVENT,
    "concept": EntityType.CONCEPT,
}

_DEPTH_MAP = {
    "intimate": KnowledgeDepth.INTIMATE,
    "familiar": KnowledgeDepth.FAMILIAR,
    "acquainted": KnowledgeDepth.ACQUAINTED,
    "rumor": KnowledgeDepth.RUMOR,
    "unknown": KnowledgeDepth.UNKNOWN,
}


def _parse_entity(eid: str, edata: Dict[str, Any]) -> EntityKnowledge:
    """Parse a single entity dict into an EntityKnowledge object."""
    return EntityKnowledge(
        entity_id=eid,
        entity_type=_TYPE_MAP.get(edata.get("entity_type", "concept"), EntityType.CONCEPT),
        display_name=edata.get("display_name", eid),
        depth=_DEPTH_MAP.get(edata.get("depth", "acquainted"), KnowledgeDepth.ACQUAINTED),
        description=edata.get("description", ""),
        relationship_to_npc=edata.get("relationship_to_npc", ""),
        emotion_variants=edata.get("emotion_variants", {}),
        related_entities=edata.get("related_entities", []),
        aliases=edata.get("aliases", []),
        topics=edata.get("topics", []),
        secret_description=edata.get("secret_description", ""),
        trust_threshold=edata.get("trust_threshold", 70.0),
    )


def load_knowledge_from_file(filepath: str) -> Dict[str, EntityKnowledge]:
    """Load a knowledge graph from a knowledge.json file.
    
    The JSON format is:
    {
      "entities": {
        "entity_id": {
          "entity_type": "person|place|item|faction|event|concept",
          "display_name": "...",
          "depth": "intimate|familiar|acquainted|rumor|unknown",
          "description": "...",
          ...
        }
      }
    }
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, PermissionError) as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to load knowledge file at {filepath}: {e}")
        return {}
    
    entities_data = data.get("entities", {})
    return {eid: _parse_entity(eid, edata) for eid, edata in entities_data.items()}


def load_knowledge_from_dict(entities_data: Dict[str, Any]) -> Dict[str, EntityKnowledge]:
    """Load knowledge from an already-parsed dict (for inline/programmatic use)."""
    return {eid: _parse_entity(eid, edata) for eid, edata in entities_data.items()}


class KnowledgeGraph:
    """
    Module 8 of the Cognitive Engine.
    Structured entity knowledge for NPC-aware responses.
    """

    def __init__(self, knowledge: Optional[Dict[str, EntityKnowledge]] = None):
        self.entities: Dict[str, EntityKnowledge] = knowledge or {}
        # Build alias index for fast lookup
        self._alias_index: Dict[str, str] = {}
        for eid, ek in self.entities.items():
            self._alias_index[ek.display_name.lower()] = eid
            for alias in ek.aliases:
                self._alias_index[alias.lower()] = eid

    def get_known_entities(self) -> Dict[str, str]:
        """Extract entity names and types for use by the conversation tracker.
        
        Returns a dict of {display_name: entity_type_string} for all known entities.
        This replaces the hardcoded entity extraction in the cognitive engine.
        """
        entities = {}
        type_label_map = {
            EntityType.PERSON: "NPC",
            EntityType.PLACE: "PLACE",
            EntityType.ITEM: "ITEM",
            EntityType.FACTION: "FACTION",
            EntityType.EVENT: "EVENT",
            EntityType.CONCEPT: "CONCEPT",
        }
        for eid, ek in self.entities.items():
            label = type_label_map.get(ek.entity_type, "NPC")
            entities[ek.display_name] = label
            # Also add aliases as recognizable entities
            for alias in ek.aliases:
                # Only add aliases that look like proper names (capitalized, multi-char)
                if len(alias) > 2:
                    entities[alias.title()] = label
        return entities

    def lookup(
        self,
        query: str,
        player_trust: float = 50.0,
        emotion: str = "neutral",
    ) -> Optional[Dict[str, Any]]:
        """
        Look up an entity in the knowledge graph.

        Searches for entity names/aliases in the query text.
        Returns the NPC's knowledge about the best-matching entity.

        Args:
            query: Player's message
            player_trust: Current trust score (for gated knowledge)
            emotion: Current NPC emotion (for variant selection)

        Returns:
            {
                "response": str,
                "entity_id": str,
                "entity_name": str,
                "entity_type": str,
                "depth": str,
                "source": "knowledge_graph",
                "confidence": float,
                "has_secret": bool,
                "related": [str],
            }
            or None if no entity found.
        """
        q_lower = query.lower()

        # Find the longest matching alias (prefer "Merchant's Alliance" over "the")
        best_eid = None
        best_len = 0

        for alias, eid in self._alias_index.items():
            if alias in q_lower and len(alias) > best_len:
                # Ensure it's a word boundary match for short aliases
                if len(alias) <= 3:
                    # Skip very short aliases unless exact word
                    pattern = r'\b' + re.escape(alias) + r'\b'
                    if not re.search(pattern, q_lower):
                        continue
                best_eid = eid
                best_len = len(alias)

        if not best_eid or best_eid not in self.entities:
            return None

        entity = self.entities[best_eid]

        # Select response text
        response = entity.description
        if emotion in entity.emotion_variants:
            response = entity.emotion_variants[emotion]

        # Check for trust-gated secret knowledge
        has_secret = bool(entity.secret_description)
        if has_secret and player_trust >= entity.trust_threshold:
            response += f" {entity.secret_description}"

        # Confidence based on knowledge depth
        depth_confidence = {
            KnowledgeDepth.INTIMATE: 0.95,
            KnowledgeDepth.FAMILIAR: 0.85,
            KnowledgeDepth.ACQUAINTED: 0.75,
            KnowledgeDepth.RUMOR: 0.60,
            KnowledgeDepth.UNKNOWN: 0.30,
        }

        return {
            "response": response,
            "entity_id": entity.entity_id,
            "entity_name": entity.display_name,
            "entity_type": entity.entity_type.value,
            "depth": entity.depth.value,
            "source": "knowledge_graph",
            "confidence": depth_confidence.get(entity.depth, 0.70),
            "has_secret": has_secret and player_trust >= entity.trust_threshold,
            "related": entity.related_entities,
        }

    def get_entity(self, entity_id: str) -> Optional[EntityKnowledge]:
        """Direct entity access by ID."""
        return self.entities.get(entity_id)

    def get_related(self, entity_id: str) -> List[EntityKnowledge]:
        """Get entities related to a given entity."""
        entity = self.entities.get(entity_id)
        if not entity:
            return []
        return [self.entities[rid] for rid in entity.related_entities
                if rid in self.entities]

    def list_entities(self, entity_type: Optional[EntityType] = None) -> List[EntityKnowledge]:
        """List all known entities, optionally filtered by type."""
        entities = list(self.entities.values())
        if entity_type:
            entities = [e for e in entities if e.entity_type == entity_type]
        return entities
