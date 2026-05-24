"""
KN Node Module — Base and specialized node types for the Knowledge Network.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class NodeType(Enum):
    """Broad category of knowledge entity."""
    PERSON = "person"
    PLACE = "place"
    ITEM = "item"
    FACTION = "faction"
    EVENT = "event"
    CONCEPT = "concept"
    CREATURE = "creature"
    KNOWLEDGE = "knowledge"      # A piece of lore/fact
    RELATIONSHIP = "relationship"
    SESSION = "session"          # Conversation session node
    UNKNOWN = "unknown"


class EdgeType(Enum):
    """Relationship type between nodes."""
    KNOWS = "knows"
    LOCATED_AT = "located_at"
    PART_OF = "part_of"
    OWNED_BY = "owned_by"
    ALLIED_WITH = "allied_with"
    HOSTILE_TO = "hostile_to"
    RELATED_TO = "related_to"
    CAUSED = "caused"
    FOLLOWS = "follows"
    MENTIONED_IN = "mentioned_in"
    MEMBER_OF = "member_of"
    LEADS = "leads"
    REFERENCES = "references"
    SIMILAR_TO = "similar_to"


@dataclass
class Edge:
    """A directed, weighted relationship between two nodes."""
    source_id: str
    target_id: str
    edge_type: EdgeType = EdgeType.RELATED_TO
    weight: float = 1.0          # 0.0 (irrelevant) to 1.0 (strongly connected)
    bidirectional: bool = False  # If True, weight applies in both directions
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Convert the Edge instance to a dictionary representation.
        
        Returns:
            Dict[str, Any]: Dictionary containing all edge fields.
        """
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type.value,
            "weight": self.weight,
            "bidirectional": self.bidirectional,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Edge":
        """Create an Edge instance from a dictionary representation.
        
        Args:
            data (Dict[str, Any]): Dictionary containing edge data.
            
        Returns:
            Edge: A new Edge instance.
        """
        return cls(
            source_id=data["source_id"],
            target_id=data["target_id"],
            edge_type=EdgeType(data.get("edge_type", "related_to")),
            weight=data.get("weight", 1.0),
            bidirectional=data.get("bidirectional", False),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", time.time()),
        )


@dataclass
class KNode:
    """
    Base knowledge node. Can represent any entity: person, place, item, etc.
    
    The node stores its own content plus metadata for retrieval and linking.
    """
    id: str
    node_type: NodeType = NodeType.UNKNOWN
    content: str = ""
    
    # Display and identification
    display_name: str = ""
    aliases: List[str] = field(default_factory=list)
    
    # Relationship data
    description: str = ""
    facts: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    
    # Trust/access gating
    trust_threshold: float = 0.0   # 0 = public, 100 = fully trusted
    
    # Emotional coloring
    emotion_variants: Dict[str, str] = field(default_factory=dict)
    
    # Links to other nodes (node IDs)
    outgoing_edges: List[str] = field(default_factory=list)   # node IDs this node links to
    incoming_edges: List[str] = field(default_factory=list)    # node IDs that link to this node
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    depth: str = "acquainted"     # How well this knowledge is known: intimate/familiar/acquainted/rumor/unknown
    confidence: float = 0.70       # Confidence in this node's accuracy
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    version: int = 1               # Incremented on each update
    
    # Source tracking
    source: str = ""              # Where this knowledge came from (character, world_lore, etc.)
    provenance: List[str] = field(default_factory=list)   # Chain of sources
    
    def get_embedding_text(self) -> str:
        """Composite text used for semantic embedding.
        
        Returns:
            str: Combined text representation of the node for vectorization.
        """
        parts = [self.display_name or self.id, self.content, self.description]
        parts.extend(self.facts)
        parts.extend(self.aliases)
        parts.extend(self.tags)
        return " ".join(p for p in parts if p)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the KNode instance to a dictionary representation.
        
        Returns:
            Dict[str, Any]: Dictionary containing all node fields.
        """
        return {
            "id": self.id,
            "node_type": self.node_type.value,
            "content": self.content,
            "display_name": self.display_name,
            "aliases": self.aliases,
            "description": self.description,
            "facts": self.facts,
            "tags": self.tags,
            "trust_threshold": self.trust_threshold,
            "emotion_variants": self.emotion_variants,
            "outgoing_edges": self.outgoing_edges,
            "incoming_edges": self.incoming_edges,
            "metadata": self.metadata,
            "depth": self.depth,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
            "source": self.source,
            "provenance": self.provenance,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KNode":
        """Create a KNode instance from a dictionary representation.
        
        Args:
            data (Dict[str, Any]): Dictionary containing node data.
            
        Returns:
            KNode: A new KNode instance.
        """
        return cls(
            id=data["id"],
            node_type=NodeType(data.get("node_type", "unknown")),
            content=data.get("content", ""),
            display_name=data.get("display_name", ""),
            aliases=data.get("aliases", []),
            description=data.get("description", ""),
            facts=data.get("facts", []),
            tags=data.get("tags", []),
            trust_threshold=data.get("trust_threshold", 0.0),
            emotion_variants=data.get("emotion_variants", {}),
            outgoing_edges=data.get("outgoing_edges", []),
            incoming_edges=data.get("incoming_edges", []),
            metadata=data.get("metadata", {}),
            depth=data.get("depth", "acquainted"),
            confidence=data.get("confidence", 0.70),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            version=data.get("version", 1),
            source=data.get("source", ""),
            provenance=data.get("provenance", []),
        )
    
    def update_content(self, content: str, description: str = "", facts: Optional[List[str]] = None) -> None:
        """Update node content with version tracking."""
        self.content = content
        if description:
            self.description = description
        if facts is not None:
            self.facts = facts
        self.updated_at = time.time()
        self.version += 1
    
    def add_edge(self, target_id: str) -> None:
        """Add an outgoing edge to another node."""
        if target_id not in self.outgoing_edges:
            self.outgoing_edges.append(target_id)
            self.updated_at = time.time()
    
    def add_alias(self, alias: str) -> None:
        """Add an alias for this node."""
        if alias not in self.aliases:
            self.aliases.append(alias)
            self.updated_at = time.time()
    
    def add_fact(self, fact: str) -> None:
        """Add a fact to this node."""
        if fact not in self.facts:
            self.facts.append(fact)
            self.updated_at = time.time()
    
    def add_tag(self, tag: str) -> None:
        """Add a tag to this node."""
        if tag not in self.tags:
            self.tags.append(tag)
            self.updated_at = time.time()


# Specialized node types for common use cases

@dataclass
class PersonNode(KNode):
    """A person/character entity."""
    role: str = ""           # e.g., "merchant", "guard", "noble"
    faction: str = ""        # Faction affiliation
    location: str = ""       # Current/associated location
    personality: str = ""     # Brief personality note
    
    def __post_init__(self):
        """Initialize PersonNode specific defaults after dataclass initialization."""
        if self.node_type == NodeType.UNKNOWN:
            self.node_type = NodeType.PERSON
        if not self.display_name:
            self.display_name = self.id.replace("_", " ").title()


@dataclass
class PlaceNode(KNode):
    """A location entity."""
    region: str = ""          # Geographic region
    population: str = ""      # Population string
    governing_faction: str = ""
    location_type: str = ""  # city, village, dungeon, etc.
    
    def __post_init__(self):
        """Initialize PlaceNode specific defaults after dataclass initialization."""
        if self.node_type == NodeType.UNKNOWN:
            self.node_type = NodeType.PLACE
        if not self.display_name:
            self.display_name = self.id.replace("_", " ").title()


@dataclass
class ItemNode(KNode):
    """An item/object entity."""
    item_type: str = ""       # weapon, potion, treasure, etc.
    rarity: str = ""          # common, rare, legendary, etc.
    value: str = ""           # Monetary or intrinsic value
    location: str = ""        # Where it can be found/purchased
    
    def __post_init__(self):
        """Initialize ItemNode specific defaults after dataclass initialization."""
        if self.node_type == NodeType.UNKNOWN:
            self.node_type = NodeType.ITEM
        if not self.display_name:
            self.display_name = self.id.replace("_", " ").title()


@dataclass
class FactionNode(KNode):
    """A faction/organization entity."""
    faction_type: str = ""    # guild, army, secret society, etc.
    alignment: str = ""       # Chaotic good, lawful evil, etc.
    leader: str = ""          # ID of the leader node
    members: List[str] = field(default_factory=list)  # Node IDs of members
    
    def __post_init__(self):
        """Initialize FactionNode specific defaults after dataclass initialization."""
        if self.node_type == NodeType.UNKNOWN:
            self.node_type = NodeType.FACTION
        if not self.display_name:
            self.display_name = self.id.replace("_", " ").title()


@dataclass
class EventNode(KNode):
    """An event/incident entity."""
    event_type: str = ""      # battle, discovery, betrayal, etc.
    date: str = ""            # When it happened
    location: str = ""       # Where it happened
    participants: List[str] = field(default_factory=list)  # Node IDs
    
    def __post_init__(self):
        """Initialize EventNode specific defaults after dataclass initialization."""
        if self.node_type == NodeType.UNKNOWN:
            self.node_type = NodeType.EVENT
        if not self.display_name:
            self.display_name = self.id.replace("_", " ").title()


@dataclass
class KnowledgeNode(KNode):
    """A piece of lore or fact — the basic unit of the Knowledge Cloud."""
    subject: str = ""         # What this knowledge is about
    claim: str = ""           # The actual claim/statement
    evidence: List[str] = field(default_factory=list)  # Supporting evidence
    contradicts: List[str] = field(default_factory=list)  # IDs of contradicting nodes
    supports: List[str] = field(default_factory=list)    # IDs of supported nodes
    
    def __post_init__(self):
        """Initialize KnowledgeNode specific defaults after dataclass initialization."""
        if self.node_type == NodeType.UNKNOWN:
            self.node_type = NodeType.KNOWLEDGE
        if not self.display_name:
            self.display_name = self.id
    
    def get_embedding_text(self) -> str:
        """Composite text used for semantic embedding for KnowledgeNode.
        
        Returns:
            str: Combined text representation including subject and claim.
        """
        parts = [self.subject, self.claim, self.content]
        parts.extend(self.facts)
        parts.extend(self.evidence)
        parts.extend(self.tags)
        return " ".join(p for p in parts if p)


def create_node(
    node_id: str,
    node_type: NodeType,
    content: str = "",
    display_name: str = "",
    **kwargs
) -> KNode:
    """
    Factory function to create the appropriate node subclass.
    
    Usage:
        node = create_node("dragon", NodeType.CREATURE, "A fearsome dragon...")
        person = create_node("gorn_the_merchant", NodeType.PERSON, role="merchant")
    """
    subclasses = {
        NodeType.PERSON: PersonNode,
        NodeType.PLACE: PlaceNode,
        NodeType.ITEM: ItemNode,
        NodeType.FACTION: FactionNode,
        NodeType.EVENT: EventNode,
        NodeType.KNOWLEDGE: KnowledgeNode,
        NodeType.CREATURE: KNode,  # Creatures use base KNode
    }
    
    cls = subclasses.get(node_type, KNode)
    node = cls(id=node_id, node_type=node_type, content=content, display_name=display_name, **kwargs)
    return node