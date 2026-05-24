"""
Module 11: Social Fabric — Multi-NPC Interaction System

Enables NPCs to:
1. Talk to each other (NPC-to-NPC conversations)
2. Form and dissolve factions/groups
3. Spread information (gossip/rumor propagation)
4. React to each other's emotions and actions
5. Hold group conversations (tavern scenes, council meetings)

Architecture:
- SocialFabric is a singleton world-level coordinator
- Each NPC registers via its CognitiveEngine
- NPCs communicate through a message bus (not direct function calls)
- Faction system tracks alliances, rivalries, and neutral relations
- Gossip propagation uses a decay model (info degrades over hops)

Cost: ~0.5ms per NPC interaction tick, ~50 KB RAM for 100 NPCs, zero GPU.
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


# ── Enums ──

class FactionRelation(Enum):
    """How two factions feel about each other."""
    ALLIED = "allied"         # Will help each other
    FRIENDLY = "friendly"     # Positive disposition
    NEUTRAL = "neutral"       # Default
    RIVAL = "rival"           # Competitive tension
    HOSTILE = "hostile"       # Active conflict


class GossipPriority(Enum):
    """How important a piece of gossip is."""
    TRIVIAL = 0     # Weather chat, idle observations
    NORMAL = 1      # General news
    IMPORTANT = 2   # Major events
    URGENT = 3      # Threats, emergencies


class ConversationRole(Enum):
    """Role in a group conversation."""
    INITIATOR = "initiator"
    PARTICIPANT = "participant"
    OBSERVER = "observer"     # Nearby but not directly involved


# ── Data Classes ──

@dataclass
class Faction:
    """A group of NPCs with shared identity."""
    faction_id: str
    name: str
    description: str = ""
    members: Set[str] = field(default_factory=set)       # character_ids
    leader: Optional[str] = None
    values: Dict[str, float] = field(default_factory=dict)  # e.g. {"honor": 0.8, "greed": 0.3}
    created_at: float = field(default_factory=time.time)

    def add_member(self, character_id: str) -> None:
        self.members.add(character_id)

    def remove_member(self, character_id: str) -> None:
        self.members.discard(character_id)
        if self.leader == character_id:
            self.leader = None

    @property
    def size(self) -> int:
        return len(self.members)


@dataclass
class GossipItem:
    """A piece of information spreading through the NPC network."""
    gossip_id: str
    content: str                              # What the gossip says
    source_npc: str                           # Who originated it
    subject: Optional[str] = None             # Who/what it's about
    priority: GossipPriority = GossipPriority.NORMAL
    truth_value: float = 1.0                  # 1.0 = true, 0.0 = fabricated
    decay_per_hop: float = 0.15              # How much fidelity degrades per retelling
    hops: int = 0                            # How many times it's been passed along
    heard_by: Set[str] = field(default_factory=set)  # NPCs who know this
    created_at: float = field(default_factory=time.time)
    tags: Set[str] = field(default_factory=set)       # e.g. {"trade", "danger"}

    @property
    def current_fidelity(self) -> float:
        """How accurate this gossip still is after N hops."""
        return max(0.0, self.truth_value - (self.decay_per_hop * self.hops))

    @property
    def is_stale(self) -> bool:
        """Gossip is stale if fidelity drops below 0.2."""
        return self.current_fidelity < 0.2


@dataclass
class NPCMessage:
    """A message from one NPC to another (or to a group)."""
    message_id: str
    sender_id: str
    content: str
    intent: str = "chat"           # chat, warn, trade, greet, insult, inform, ask
    emotion: str = "neutral"
    target_id: Optional[str] = None        # None = broadcast to group
    group_id: Optional[str] = None         # For group conversations
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GroupConversation:
    """An active multi-NPC conversation."""
    group_id: str
    location: str = "unknown"
    participants: Dict[str, ConversationRole] = field(default_factory=dict)
    messages: List[NPCMessage] = field(default_factory=list)
    topic: str = "general"
    started_at: float = field(default_factory=time.time)
    max_messages: int = 50
    active: bool = True

    def add_participant(self, npc_id: str, role: ConversationRole = ConversationRole.PARTICIPANT) -> None:
        self.participants[npc_id] = role

    def remove_participant(self, npc_id: str) -> None:
        self.participants.pop(npc_id, None)
        if not self.participants:
            self.active = False

    @property
    def participant_ids(self) -> Set[str]:
        return {npc_id for npc_id, role in self.participants.items()
                if role != ConversationRole.OBSERVER}


# ── NPC Registry Entry ──

@dataclass
class NPCProfile:
    """Registered NPC in the social fabric."""
    character_id: str
    name: str
    faction_ids: Set[str] = field(default_factory=set)
    location: str = "unknown"
    disposition: Dict[str, float] = field(default_factory=dict)  # char_id → [-1, 1]
    known_gossip: Set[str] = field(default_factory=set)          # gossip_ids
    personality_traits: Dict[str, float] = field(default_factory=dict)
    social_tags: Set[str] = field(default_factory=set)  # e.g. {"merchant", "guard"}
    last_active: float = field(default_factory=time.time)


# ── Social Fabric (Singleton Coordinator) ──

class SocialFabric:
    """
    World-level coordinator for multi-NPC interactions.

    Manages:
    - NPC registry and social profiles
    - Faction system with inter-faction relations
    - Gossip propagation network
    - Group conversations
    - NPC-to-NPC message bus
    """

    def __init__(self, max_gossip: int = 500, max_groups: int = 50):
        # NPC registry
        self._npcs: Dict[str, NPCProfile] = {}

        # Faction system
        self._factions: Dict[str, Faction] = {}
        self._faction_relations: Dict[Tuple[str, str], FactionRelation] = {}

        # Gossip network
        self._gossip: Dict[str, GossipItem] = {}
        self._max_gossip = max_gossip

        # Group conversations
        self._groups: Dict[str, GroupConversation] = {}
        self._max_groups = max_groups

        # Message bus
        self._message_queue: deque = deque(maxlen=1000)
        self._message_handlers: Dict[str, List[Callable]] = defaultdict(list)

        # Metrics
        self._total_messages = 0
        self._total_gossip_spread = 0
        self._total_npc_interactions = 0

    # ══════════════════════════════════════
    # NPC Registration
    # ══════════════════════════════════════

    def register_npc(
        self,
        character_id: str,
        name: str,
        faction_ids: Optional[Set[str]] = None,
        location: str = "unknown",
        personality_traits: Optional[Dict[str, float]] = None,
        social_tags: Optional[Set[str]] = None,
    ) -> NPCProfile:
        """Register an NPC in the social fabric."""
        profile = NPCProfile(
            character_id=character_id,
            name=name,
            faction_ids=faction_ids or set(),
            location=location,
            personality_traits=personality_traits or {},
            social_tags=social_tags or set(),
        )
        self._npcs[character_id] = profile

        # Auto-add to factions
        for fid in profile.faction_ids:
            if fid in self._factions:
                self._factions[fid].add_member(character_id)

        return profile

    def unregister_npc(self, character_id: str) -> bool:
        """Remove an NPC from the social fabric."""
        profile = self._npcs.pop(character_id, None)
        if not profile:
            return False
        # Remove from factions
        for fid in profile.faction_ids:
            if fid in self._factions:
                self._factions[fid].remove_member(character_id)
        # Remove from active groups
        for group in self._groups.values():
            group.remove_participant(character_id)
        return True

    def get_npc(self, character_id: str) -> Optional[NPCProfile]:
        return self._npcs.get(character_id)

    def get_npcs_at_location(self, location: str) -> List[NPCProfile]:
        """Get all NPCs at a specific location."""
        return [npc for npc in self._npcs.values() if npc.location == location]

    def get_npcs_by_tag(self, tag: str) -> List[NPCProfile]:
        """Get all NPCs with a specific social tag."""
        return [npc for npc in self._npcs.values() if tag in npc.social_tags]

    def move_npc(self, character_id: str, new_location: str) -> bool:
        """Move an NPC to a new location."""
        npc = self._npcs.get(character_id)
        if not npc:
            return False
        npc.location = new_location
        npc.last_active = time.time()
        return True

    @property
    def npc_count(self) -> int:
        return len(self._npcs)

    @property
    def registered_npcs(self) -> List[str]:
        return list(self._npcs.keys())

    # ══════════════════════════════════════
    # Faction System
    # ══════════════════════════════════════

    def create_faction(
        self,
        name: str,
        description: str = "",
        leader: Optional[str] = None,
        values: Optional[Dict[str, float]] = None,
        faction_id: Optional[str] = None,
    ) -> Faction:
        """Create a new faction."""
        fid = faction_id or f"faction_{uuid.uuid4().hex[:8]}"
        faction = Faction(
            faction_id=fid,
            name=name,
            description=description,
            leader=leader,
            values=values or {},
        )
        if leader:
            faction.add_member(leader)
            if leader in self._npcs:
                self._npcs[leader].faction_ids.add(fid)
        self._factions[fid] = faction
        return faction

    def dissolve_faction(self, faction_id: str) -> bool:
        """Dissolve a faction and remove all members."""
        faction = self._factions.pop(faction_id, None)
        if not faction:
            return False
        for member_id in faction.members:
            if member_id in self._npcs:
                self._npcs[member_id].faction_ids.discard(faction_id)
        # Clean up relations
        to_remove = [k for k in self._faction_relations if faction_id in k]
        for k in to_remove:
            del self._faction_relations[k]
        return True

    def join_faction(self, character_id: str, faction_id: str) -> bool:
        """Add an NPC to a faction."""
        if faction_id not in self._factions or character_id not in self._npcs:
            return False
        self._factions[faction_id].add_member(character_id)
        self._npcs[character_id].faction_ids.add(faction_id)
        return True

    def leave_faction(self, character_id: str, faction_id: str) -> bool:
        """Remove an NPC from a faction."""
        if faction_id not in self._factions:
            return False
        self._factions[faction_id].remove_member(character_id)
        if character_id in self._npcs:
            self._npcs[character_id].faction_ids.discard(faction_id)
        return True

    def set_faction_relation(
        self, faction_a: str, faction_b: str, relation: FactionRelation
    ) -> bool:
        """Set the relationship between two factions (bidirectional)."""
        if faction_a not in self._factions or faction_b not in self._factions:
            return False
        key = tuple(sorted([faction_a, faction_b]))
        self._faction_relations[key] = relation
        return True

    def get_faction_relation(self, faction_a: str, faction_b: str) -> FactionRelation:
        """Get the relationship between two factions."""
        key = tuple(sorted([faction_a, faction_b]))
        return self._faction_relations.get(key, FactionRelation.NEUTRAL)

    def get_faction(self, faction_id: str) -> Optional[Faction]:
        return self._factions.get(faction_id)

    def get_npc_factions(self, character_id: str) -> List[Faction]:
        """Get all factions an NPC belongs to."""
        npc = self._npcs.get(character_id)
        if not npc:
            return []
        return [self._factions[fid] for fid in npc.faction_ids if fid in self._factions]

    def are_allies(self, npc_a: str, npc_b: str) -> bool:
        """Check if two NPCs share an allied faction."""
        a = self._npcs.get(npc_a)
        b = self._npcs.get(npc_b)
        if not a or not b:
            return False
        # Same faction = allies
        if a.faction_ids & b.faction_ids:
            return True
        # Check cross-faction alliance
        for fa in a.faction_ids:
            for fb in b.faction_ids:
                if self.get_faction_relation(fa, fb) == FactionRelation.ALLIED:
                    return True
        return False

    def are_hostile(self, npc_a: str, npc_b: str) -> bool:
        """Check if two NPCs belong to hostile factions."""
        a = self._npcs.get(npc_a)
        b = self._npcs.get(npc_b)
        if not a or not b:
            return False
        for fa in a.faction_ids:
            for fb in b.faction_ids:
                if fa != fb:
                    rel = self.get_faction_relation(fa, fb)
                    if rel in (FactionRelation.HOSTILE, FactionRelation.RIVAL):
                        return True
        return False

    @property
    def faction_count(self) -> int:
        return len(self._factions)

    # ══════════════════════════════════════
    # Disposition (NPC-to-NPC feelings)
    # ══════════════════════════════════════

    def set_disposition(self, from_npc: str, to_npc: str, value: float) -> bool:
        """Set how one NPC feels about another. Range: [-1.0, 1.0]."""
        npc = self._npcs.get(from_npc)
        if not npc or to_npc not in self._npcs:
            return False
        npc.disposition[to_npc] = max(-1.0, min(1.0, value))
        return True

    def adjust_disposition(self, from_npc: str, to_npc: str, delta: float) -> float:
        """Adjust disposition by delta. Returns new value."""
        npc = self._npcs.get(from_npc)
        if not npc or to_npc not in self._npcs:
            return 0.0
        current = npc.disposition.get(to_npc, 0.0)
        new_val = max(-1.0, min(1.0, current + delta))
        npc.disposition[to_npc] = new_val
        return new_val

    def get_disposition(self, from_npc: str, to_npc: str) -> float:
        """Get how one NPC feels about another. Default 0.0 (neutral)."""
        npc = self._npcs.get(from_npc)
        if not npc:
            return 0.0
        base = npc.disposition.get(to_npc, 0.0)
        # Faction bonus/penalty
        if self.are_allies(from_npc, to_npc):
            base = max(base, base + 0.2)
        elif self.are_hostile(from_npc, to_npc):
            base = min(base, base - 0.3)
        return max(-1.0, min(1.0, base))

    # ══════════════════════════════════════
    # Gossip Propagation
    # ══════════════════════════════════════

    def create_gossip(
        self,
        source_npc: str,
        content: str,
        subject: Optional[str] = None,
        priority: GossipPriority = GossipPriority.NORMAL,
        truth_value: float = 1.0,
        decay_per_hop: float = 0.15,
        tags: Optional[Set[str]] = None,
    ) -> GossipItem:
        """Create a new piece of gossip originating from an NPC."""
        gossip = GossipItem(
            gossip_id=f"gossip_{uuid.uuid4().hex[:8]}",
            content=content,
            source_npc=source_npc,
            subject=subject,
            priority=priority,
            truth_value=truth_value,
            decay_per_hop=decay_per_hop,
            tags=tags or set(),
        )
        gossip.heard_by.add(source_npc)
        if source_npc in self._npcs:
            self._npcs[source_npc].known_gossip.add(gossip.gossip_id)

        # Evict oldest if at capacity
        if len(self._gossip) >= self._max_gossip:
            oldest_id = min(self._gossip, key=lambda gid: self._gossip[gid].created_at)
            self._evict_gossip(oldest_id)

        self._gossip[gossip.gossip_id] = gossip
        return gossip

    def spread_gossip(
        self,
        gossip_id: str,
        from_npc: str,
        to_npc: str,
    ) -> Optional[Dict[str, Any]]:
        """
        One NPC tells another a piece of gossip.
        Returns the gossip state after spreading, or None if failed.
        """
        gossip = self._gossip.get(gossip_id)
        if not gossip:
            return None
        if from_npc not in gossip.heard_by:
            return None  # Can't spread what you don't know
        if to_npc in gossip.heard_by:
            return None  # Already knows

        # Spread it
        gossip.hops += 1
        gossip.heard_by.add(to_npc)
        if to_npc in self._npcs:
            self._npcs[to_npc].known_gossip.add(gossip_id)

        self._total_gossip_spread += 1

        return {
            "gossip_id": gossip_id,
            "content": gossip.content,
            "fidelity": gossip.current_fidelity,
            "hops": gossip.hops,
            "is_stale": gossip.is_stale,
        }

    def propagate_gossip_at_location(self, location: str) -> List[Dict[str, Any]]:
        """
        Tick-based gossip spread: all NPCs at a location share gossip.
        Each NPC shares their highest-priority unknown gossip with others present.
        Returns list of spread events.
        """
        npcs_here = self.get_npcs_at_location(location)
        if len(npcs_here) < 2:
            return []

        events = []
        for npc in npcs_here:
            # Find this NPC's highest priority gossip that others might not know
            npc_gossip = [
                self._gossip[gid] for gid in npc.known_gossip
                if gid in self._gossip and not self._gossip[gid].is_stale
            ]
            if not npc_gossip:
                continue

            # Sort by priority (highest first)
            npc_gossip.sort(key=lambda g: g.priority.value, reverse=True)
            best = npc_gossip[0]

            # Share with NPCs at the same location who haven't heard it
            for other in npcs_here:
                if other.character_id == npc.character_id:
                    continue
                if other.character_id in best.heard_by:
                    continue
                # Disposition check — hostile NPCs don't share
                disp = self.get_disposition(npc.character_id, other.character_id)
                if disp < -0.5:
                    continue

                result = self.spread_gossip(best.gossip_id, npc.character_id, other.character_id)
                if result:
                    result["from_npc"] = npc.character_id
                    result["to_npc"] = other.character_id
                    events.append(result)

        return events

    def get_npc_gossip(self, character_id: str) -> List[GossipItem]:
        """Get all gossip known by an NPC."""
        npc = self._npcs.get(character_id)
        if not npc:
            return []
        return [
            self._gossip[gid] for gid in npc.known_gossip
            if gid in self._gossip
        ]

    def get_gossip_about(self, subject: str) -> List[GossipItem]:
        """Get all gossip about a specific subject."""
        return [g for g in self._gossip.values() if g.subject == subject]

    def _evict_gossip(self, gossip_id: str) -> None:
        """Remove a gossip item and clean up references."""
        gossip = self._gossip.pop(gossip_id, None)
        if gossip:
            for npc_id in gossip.heard_by:
                if npc_id in self._npcs:
                    self._npcs[npc_id].known_gossip.discard(gossip_id)

    @property
    def gossip_count(self) -> int:
        return len(self._gossip)

    # ══════════════════════════════════════
    # NPC-to-NPC Messaging
    # ══════════════════════════════════════

    def send_message(
        self,
        sender_id: str,
        content: str,
        intent: str = "chat",
        emotion: str = "neutral",
        target_id: Optional[str] = None,
        group_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[NPCMessage]:
        """Send a message from one NPC to another or to a group."""
        if sender_id not in self._npcs:
            return None
        if target_id and target_id not in self._npcs:
            return None
        if group_id and group_id not in self._groups:
            return None

        msg = NPCMessage(
            message_id=f"msg_{uuid.uuid4().hex[:8]}",
            sender_id=sender_id,
            content=content,
            intent=intent,
            emotion=emotion,
            target_id=target_id,
            group_id=group_id,
            metadata=metadata or {},
        )

        # Add to group conversation if applicable
        if group_id and group_id in self._groups:
            group = self._groups[group_id]
            if group.active:
                group.messages.append(msg)
                if len(group.messages) > group.max_messages:
                    group.messages = group.messages[-group.max_messages:]

        self._message_queue.append(msg)
        self._total_messages += 1
        self._total_npc_interactions += 1

        # Disposition adjustment based on intent
        if target_id:
            if intent == "insult":
                self.adjust_disposition(target_id, sender_id, -0.1)
            elif intent in ("greet", "compliment"):
                self.adjust_disposition(target_id, sender_id, 0.05)
            elif intent == "warn":
                # Warnings improve disposition if allied
                if self.are_allies(sender_id, target_id):
                    self.adjust_disposition(target_id, sender_id, 0.1)

        # Fire message handlers
        for handler in self._message_handlers.get(intent, []):
            handler(msg)
        for handler in self._message_handlers.get("*", []):
            handler(msg)

        return msg

    def on_message(self, intent: str, handler: Callable[[NPCMessage], None]) -> None:
        """Register a handler for messages of a given intent. Use '*' for all."""
        self._message_handlers[intent].append(handler)

    def get_recent_messages(
        self,
        npc_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[NPCMessage]:
        """Get recent messages, optionally filtered by NPC involvement."""
        msgs = list(self._message_queue)
        if npc_id:
            msgs = [m for m in msgs if m.sender_id == npc_id or m.target_id == npc_id]
        return msgs[-limit:]

    # ══════════════════════════════════════
    # Group Conversations
    # ══════════════════════════════════════

    def start_group_conversation(
        self,
        initiator_id: str,
        participant_ids: List[str],
        location: str = "unknown",
        topic: str = "general",
    ) -> Optional[GroupConversation]:
        """Start a group conversation between multiple NPCs."""
        if initiator_id not in self._npcs:
            return None
        valid_participants = [pid for pid in participant_ids if pid in self._npcs]
        if not valid_participants:
            return None

        if len(self._groups) >= self._max_groups:
            # Evict oldest inactive
            inactive = [g for g in self._groups.values() if not g.active]
            if inactive:
                oldest = min(inactive, key=lambda g: g.started_at)
                del self._groups[oldest.group_id]
            else:
                return None

        group = GroupConversation(
            group_id=f"group_{uuid.uuid4().hex[:8]}",
            location=location,
            topic=topic,
        )
        group.add_participant(initiator_id, ConversationRole.INITIATOR)
        for pid in valid_participants:
            if pid != initiator_id:
                group.add_participant(pid, ConversationRole.PARTICIPANT)

        # Add observers — NPCs at same location who aren't participants
        for npc in self.get_npcs_at_location(location):
            if npc.character_id not in group.participants:
                group.add_participant(npc.character_id, ConversationRole.OBSERVER)

        self._groups[group.group_id] = group
        return group

    def end_group_conversation(self, group_id: str) -> bool:
        """End a group conversation."""
        group = self._groups.get(group_id)
        if not group:
            return False
        group.active = False
        return True

    def get_group(self, group_id: str) -> Optional[GroupConversation]:
        return self._groups.get(group_id)

    def get_active_groups(self, location: Optional[str] = None) -> List[GroupConversation]:
        """Get all active group conversations, optionally at a location."""
        groups = [g for g in self._groups.values() if g.active]
        if location:
            groups = [g for g in groups if g.location == location]
        return groups

    def get_npc_groups(self, character_id: str) -> List[GroupConversation]:
        """Get all active groups an NPC is participating in."""
        return [
            g for g in self._groups.values()
            if g.active and character_id in g.participants
            and g.participants[character_id] != ConversationRole.OBSERVER
        ]

    @property
    def active_group_count(self) -> int:
        return sum(1 for g in self._groups.values() if g.active)

    # ══════════════════════════════════════
    # NPC-to-NPC Interaction Generation
    # ══════════════════════════════════════

    def generate_npc_interaction(
        self,
        npc_a: str,
        npc_b: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a contextual interaction between two NPCs based on their
        relationships, factions, dispositions, and shared gossip.

        Returns a structured interaction descriptor.
        """
        a_profile = self._npcs.get(npc_a)
        b_profile = self._npcs.get(npc_b)
        if not a_profile or not b_profile:
            return None

        self._total_npc_interactions += 1

        disposition = self.get_disposition(npc_a, npc_b)
        allied = self.are_allies(npc_a, npc_b)
        hostile = self.are_hostile(npc_a, npc_b)

        # Determine interaction type based on disposition + faction
        if hostile and disposition < -0.3:
            interaction_type = "confrontation"
            tone = "aggressive"
        elif hostile:
            interaction_type = "tense_exchange"
            tone = "guarded"
        elif allied and disposition > 0.3:
            interaction_type = "friendly_chat"
            tone = "warm"
        elif disposition > 0.5:
            interaction_type = "friendly_chat"
            tone = "casual"
        elif disposition < -0.3:
            interaction_type = "cold_exchange"
            tone = "dismissive"
        else:
            interaction_type = "neutral_exchange"
            tone = "polite"

        # Find shared gossip they could discuss
        shared_gossip = a_profile.known_gossip & b_profile.known_gossip
        unshared_a = a_profile.known_gossip - b_profile.known_gossip
        unshared_b = b_profile.known_gossip - a_profile.known_gossip

        # Determine topics
        topics = []
        if unshared_a:
            topics.append("npc_a_has_news")
        if unshared_b:
            topics.append("npc_b_has_news")
        if shared_gossip:
            topics.append("shared_knowledge")

        # Check for trade potential
        if "merchant" in a_profile.social_tags or "merchant" in b_profile.social_tags:
            topics.append("trade")

        # Check for shared faction business
        shared_factions = a_profile.faction_ids & b_profile.faction_ids
        if shared_factions:
            topics.append("faction_business")

        return {
            "npc_a": npc_a,
            "npc_b": npc_b,
            "interaction_type": interaction_type,
            "tone": tone,
            "disposition": disposition,
            "allied": allied,
            "hostile": hostile,
            "topics": topics,
            "shared_gossip_count": len(shared_gossip),
            "shared_factions": list(shared_factions) if 'shared_factions' in dir() else [],
            "context": context or {},
        }

    # ══════════════════════════════════════
    # World Tick
    # ══════════════════════════════════════

    def tick(self, locations: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Run one social fabric tick.
        - Propagates gossip at each location
        - Generates ambient NPC interactions
        Returns summary of what happened.
        """
        start = time.time()
        gossip_events = []
        interactions = []

        # Get all active locations
        if locations is None:
            locations = list(set(npc.location for npc in self._npcs.values()))

        for loc in locations:
            # Gossip propagation
            events = self.propagate_gossip_at_location(loc)
            gossip_events.extend(events)

            # Ambient interactions between nearby NPCs
            npcs_here = self.get_npcs_at_location(loc)
            if len(npcs_here) >= 2:
                # Generate one ambient interaction per location per tick
                a = npcs_here[0]
                b = npcs_here[1]
                interaction = self.generate_npc_interaction(
                    a.character_id, b.character_id
                )
                if interaction:
                    interactions.append(interaction)

        elapsed = (time.time() - start) * 1000

        return {
            "gossip_events": gossip_events,
            "interactions": interactions,
            "locations_processed": len(locations),
            "elapsed_ms": round(elapsed, 2),
        }

    # ══════════════════════════════════════
    # Metrics & Debug
    # ══════════════════════════════════════

    def get_metrics(self) -> Dict[str, Any]:
        return {
            "registered_npcs": self.npc_count,
            "factions": self.faction_count,
            "active_gossip": self.gossip_count,
            "active_groups": self.active_group_count,
            "total_messages": self._total_messages,
            "total_gossip_spread": self._total_gossip_spread,
            "total_npc_interactions": self._total_npc_interactions,
        }

    def reset(self) -> None:
        """Reset the entire social fabric."""
        self._npcs.clear()
        self._factions.clear()
        self._faction_relations.clear()
        self._gossip.clear()
        self._groups.clear()
        self._message_queue.clear()
        self._message_handlers.clear()
        self._total_messages = 0
        self._total_gossip_spread = 0
        self._total_npc_interactions = 0
