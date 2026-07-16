"""
Module 12: State Persistence — Save/Load System

Serializes and deserializes the complete NPC world state to/from disk,
enabling game saves, session continuity, and hot-reload.

What gets persisted:
1. CognitiveEngine per-NPC state (conversations, emotions, relationships,
   context recall, negotiation sessions, world reactions, counters)
2. SocialFabric world state (NPC registry, factions, faction relations,
   gossip network, dispositions, group conversations)
3. World systems (economy, weather, quests, scheduling)
4. ConsciousState (crystallized memory, fluid memory, narrative timeline)

Format: JSON files in a save directory.
Cost: ~1-5ms save, ~2-8ms load for 100 NPCs. Zero GPU.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from core.conscious_state import ConsciousState, CrystallizedMemory, FluidState, NarrativeState, NarrativeEvent
from collections import deque

from .social_fabric import (
    SocialFabric,
    Faction,
    FactionRelation,
    GossipItem,
    GossipPriority,
    NPCMessage,
    GroupConversation,
    ConversationRole,
    NPCProfile,
)


# ── Helpers ──

def _set_to_list(obj: Any) -> Any:
    """Recursively convert sets to lists for JSON serialization."""
    if isinstance(obj, set):
        return sorted(list(obj))
    if isinstance(obj, dict):
        return {k: _set_to_list(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_set_to_list(item) for item in obj]
    if isinstance(obj, Enum):
        return obj.value
    return obj


def _list_to_set(obj: Any, set_keys: Set[str]) -> Any:
    """Convert specific list fields back to sets during deserialization."""
    if isinstance(obj, dict):
        return {
            k: set(v) if k in set_keys and isinstance(v, list)
            else _list_to_set(v, set_keys)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_list_to_set(item, set_keys) for item in obj]
    return obj


from enum import Enum


# ── Conscious State Serializer ──

class ConsciousStateSerializer:
    """Serializes and restores the core conscious state layers."""

    @staticmethod
    def extract_state(state: ConsciousState) -> Dict[str, Any]:
        narrative = []
        for event in state.narrative.timeline:
            narrative.append({
                "t": event.t,
                "query": event.query,
                "engines_used": list(event.engines_used),
                "summary": event.summary,
                "role": event.role,
                "emotional_tone": event.emotional_tone,
                "proof_trace": event.proof_trace,
                "explanations": list(event.explanations),
                "actions_taken": list(event.actions_taken),
            })

        return _set_to_list({
            "version": 1,
            "t": state.t,
            "crystallized": {
                "facts": dict(state.crystallized.facts),
                "rules": list(state.crystallized.rules),
                "causal_relations": list(state.crystallized.causal_relations),
                "user_traits": dict(state.crystallized.user_traits),
                "models_metadata": dict(state.crystallized.models_metadata),
                "system_logs": list(state.crystallized.system_logs),
                "candidate_rules": dict(state.crystallized.candidate_rules),
            },
            "fluid": {
                "observations": list(state.fluid.observations),
                "active_hypotheses": list(state.fluid.active_hypotheses),
                "predictions": dict(state.fluid.predictions),
                "anomalies": list(state.fluid.anomalies),
                "current_goals": list(state.fluid.current_goals),
                "belief_scores": dict(state.fluid.belief_scores),
                "current_domain": state.fluid.current_domain,
                "policy_prior": state.fluid.policy_prior,
                "risk_outcome": state.fluid.risk_outcome,
                "attention": state.fluid.attention,
            },
            "narrative": {
                "timeline": narrative,
                "current_role": state.narrative.current_role,
                "current_emotional_tone": state.narrative.current_emotional_tone,
            },
        })

    @staticmethod
    def restore_state(state: ConsciousState, data: Dict[str, Any]) -> None:
        state.t = data.get("t", 0)

        crystallized = data.get("crystallized", {})
        state.crystallized.facts = dict(crystallized.get("facts", {}))
        state.crystallized.rules = list(crystallized.get("rules", []))
        state.crystallized.causal_relations = list(crystallized.get("causal_relations", []))
        state.crystallized.user_traits = dict(crystallized.get("user_traits", {}))
        state.crystallized.models_metadata = dict(crystallized.get("models_metadata", {}))
        state.crystallized.system_logs = list(crystallized.get("system_logs", []))
        state.crystallized.candidate_rules = dict(crystallized.get("candidate_rules", {}))

        fluid = data.get("fluid", {})
        state.fluid.observations = list(fluid.get("observations", []))
        state.fluid.active_hypotheses = list(fluid.get("active_hypotheses", []))
        state.fluid.predictions = dict(fluid.get("predictions", {}))
        state.fluid.anomalies = list(fluid.get("anomalies", []))
        state.fluid.current_goals = list(fluid.get("current_goals", []))
        state.fluid.belief_scores = dict(fluid.get("belief_scores", {}))
        state.fluid.current_domain = fluid.get("current_domain", state.fluid.current_domain)
        state.fluid.policy_prior = fluid.get("policy_prior", state.fluid.policy_prior)
        state.fluid.risk_outcome = fluid.get("risk_outcome", state.fluid.risk_outcome)
        state.fluid.attention = fluid.get("attention", state.fluid.attention)

        narrative = data.get("narrative", {})
        state.narrative.current_role = narrative.get("current_role", state.narrative.current_role)
        state.narrative.current_emotional_tone = narrative.get(
            "current_emotional_tone", state.narrative.current_emotional_tone
        )
        state.narrative.timeline = [
            NarrativeEvent(
                t=event.get("t", 0),
                query=event.get("query", ""),
                engines_used=list(event.get("engines_used", [])),
                summary=event.get("summary", ""),
                role=event.get("role", "default"),
                emotional_tone=event.get("emotional_tone", "neutral"),
                proof_trace=event.get("proof_trace", ""),
                explanations=list(event.get("explanations", [])),
                actions_taken=list(event.get("actions_taken", [])),
            )
            for event in narrative.get("timeline", [])
        ]


# ── Cognitive Engine State Serializer ──

class CognitiveStateSerializer:
    """
    Extracts and restores per-NPC cognitive state from a CognitiveEngine.
    """

    @staticmethod
    def extract_state(engine) -> Dict[str, Any]:
        """
        Extract all mutable state from a CognitiveEngine instance.
        Returns a JSON-serializable dictionary.
        """
        state = {
            "character_id": engine.character_id,
            "version": 1,
            "timestamp": time.time(),

            # Conversation tracker state
            "conversations": CognitiveStateSerializer._extract_conversations(engine.tracker),

            # Emotion state machine
            "emotions": CognitiveStateSerializer._extract_emotions(engine.emotion),

            # Relationship tracker (already has its own persistence, but we
            # include it here for full-state snapshots)
            "relationships": CognitiveStateSerializer._extract_relationships(engine.relationships),

            # Context recall (NPC memory of what it said)
            "context_recall": CognitiveStateSerializer._extract_recall(engine.recall),

            # World state reactor flags
            "world_flags": dict(engine.world._flags) if hasattr(engine.world, '_flags') else {},

            # Counters
            "counters": {
                "total_queries": engine._total_queries,
                "local_handled": engine._local_handled,
                "escalated": engine._escalated,
                "knowledge_handled": engine._knowledge_handled,
                "personality_handled": engine._personality_handled,
                "recall_handled": engine._recall_handled,
                "semantic_wins": engine._semantic_wins,
            },
        }
        return _set_to_list(state)

    @staticmethod
    def restore_state(engine, state: Dict[str, Any]) -> None:
        """
        Restore mutable state into a CognitiveEngine instance.
        The engine must already be initialized with bio/patterns.
        """
        if state.get("character_id") != engine.character_id:
            raise ValueError(
                f"State character_id '{state.get('character_id')}' "
                f"doesn't match engine '{engine.character_id}'"
            )

        # Restore conversations
        CognitiveStateSerializer._restore_conversations(engine.tracker, state.get("conversations", {}))

        # Restore emotions
        CognitiveStateSerializer._restore_emotions(engine.emotion, state.get("emotions", {}))

        # Restore relationships
        CognitiveStateSerializer._restore_relationships(engine.relationships, state.get("relationships", {}))

        # Restore context recall
        CognitiveStateSerializer._restore_recall(engine.recall, state.get("context_recall", {}))

        # Restore world flags
        if hasattr(engine.world, '_flags'):
            engine.world._flags.update(state.get("world_flags", {}))

        # Restore counters
        counters = state.get("counters", {})
        engine._total_queries = counters.get("total_queries", 0)
        engine._local_handled = counters.get("local_handled", 0)
        engine._escalated = counters.get("escalated", 0)
        engine._knowledge_handled = counters.get("knowledge_handled", 0)
        engine._personality_handled = counters.get("personality_handled", 0)
        engine._recall_handled = counters.get("recall_handled", 0)
        engine._semantic_wins = counters.get("semantic_wins", 0)

    # ── Conversation Tracker ──

    @staticmethod
    def _extract_conversations(tracker) -> Dict[str, Any]:
        """Extract conversation state per player."""
        data = {}
        for player_id, conv in tracker._conversations.items():
            data[player_id] = {
                "turn_count": conv.turn_count,
                "active_topic": conv.active_topic.value if hasattr(conv.active_topic, 'value') else str(conv.active_topic),
                "previous_topic": conv.previous_topic.value if hasattr(conv.previous_topic, 'value') else str(conv.previous_topic),
                "last_interaction": conv.last_interaction,
                "player_messages": list(conv.player_messages),
                "npc_responses": list(conv.npc_responses),
                "topic_history": list(conv.topic_history),
                "open_questions": list(conv.open_questions),
                "mentioned_entities": {
                    name: {
                        "name": e.name,
                        "mention_count": e.mention_count,
                        "last_mentioned": e.last_mentioned,
                    }
                    for name, e in conv.mentioned_entities.items()
                },
            }
        return data

    @staticmethod
    def _restore_conversations(tracker, data: Dict[str, Any]) -> None:
        """Restore conversation state."""
        from .conversation_tracker import ConversationState, TrackedEntity, Topic
        for player_id, conv_data in data.items():
            if player_id not in tracker._conversations:
                tracker._conversations[player_id] = ConversationState()
            conv = tracker._conversations[player_id]
            conv.turn_count = conv_data.get("turn_count", 0)
            conv.last_interaction = conv_data.get("last_interaction", 0.0)

            # Restore topics
            for field_name in ("active_topic", "previous_topic"):
                topic_str = conv_data.get(field_name, "unknown")
                try:
                    setattr(conv, field_name, Topic(topic_str))
                except (ValueError, KeyError):
                    setattr(conv, field_name, Topic.UNKNOWN)

            # Restore deques
            conv.player_messages = deque(conv_data.get("player_messages", []), maxlen=5)
            conv.npc_responses = deque(conv_data.get("npc_responses", []), maxlen=5)
            conv.topic_history = deque(conv_data.get("topic_history", []), maxlen=10)
            conv.open_questions = conv_data.get("open_questions", [])

            # Restore entities
            for name, e_data in conv_data.get("mentioned_entities", {}).items():
                conv.mentioned_entities[name] = TrackedEntity(
                    name=e_data["name"],
                    mention_count=e_data.get("mention_count", 1),
                    last_mentioned=e_data.get("last_mentioned", 0.0),
                )

    # ── Emotion State Machine ──

    @staticmethod
    def _extract_emotions(emotion_machine) -> Dict[str, Any]:
        """Extract emotion states per player."""
        data = {}
        for player_id, npc_state in emotion_machine._states.items():
            data[player_id] = {
                "current": npc_state.current.value if hasattr(npc_state.current, 'value') else str(npc_state.current),
                "baseline": npc_state.baseline.value if hasattr(npc_state.baseline, 'value') else str(npc_state.baseline),
                "intensity": npc_state.intensity,
                "transition_count": npc_state.transition_count,
                "last_transition": npc_state.last_transition,
            }
        return data

    @staticmethod
    def _restore_emotions(emotion_machine, data: Dict[str, Any]) -> None:
        """Restore emotion states."""
        from .emotion_state_machine import EmotionState, NPCEmotionState
        for player_id, e_data in data.items():
            current_str = e_data.get("current", "neutral")
            baseline_str = e_data.get("baseline", "neutral")
            try:
                current = EmotionState(current_str)
            except (ValueError, KeyError):
                current = EmotionState.NEUTRAL
            try:
                baseline = EmotionState(baseline_str)
            except (ValueError, KeyError):
                baseline = EmotionState.NEUTRAL
            emotion_machine._states[player_id] = NPCEmotionState(
                current=current,
                baseline=baseline,
                intensity=e_data.get("intensity", 0.5),
                transition_count=e_data.get("transition_count", 0),
                last_transition=e_data.get("last_transition", 0.0),
            )

    # ── Relationship Tracker ──

    @staticmethod
    def _extract_relationships(rel_tracker) -> Dict[str, Any]:
        """Extract relationship data per player."""
        data = {}
        for player_id, rel in rel_tracker._relationships.items():
            data[player_id] = {
                "trust": rel.trust,
                "fondness": rel.fondness,
                "respect": rel.respect,
                "debt": rel.debt,
                "interactions": rel.interactions,
                "first_met": rel.first_met,
                "last_seen": rel.last_seen,
                "nickname": rel.nickname,
                "titles": list(rel.titles),
            }
        return data

    @staticmethod
    def _restore_relationships(rel_tracker, data: Dict[str, Any]) -> None:
        """Restore relationship data."""
        from .relationship_tracker import Relationship
        for player_id, r_data in data.items():
            rel_tracker._relationships[player_id] = Relationship(
                trust=r_data.get("trust", 50.0),
                fondness=r_data.get("fondness", 50.0),
                respect=r_data.get("respect", 50.0),
                debt=r_data.get("debt", 0.0),
                interactions=r_data.get("interactions", 0),
                first_met=r_data.get("first_met", 0.0),
                last_seen=r_data.get("last_seen", 0.0),
                nickname=r_data.get("nickname"),
                titles=r_data.get("titles", []),
            )

    # ── Context Recall ──

    @staticmethod
    def _extract_recall(recall) -> Dict[str, Any]:
        """Extract NPC's memory of its own responses."""
        data = {}
        for player_id, history in recall._response_history.items():
            # history is a list of (turn, response, keywords_set) tuples
            data[player_id] = {
                "responses": [
                    {"turn": t, "response": r, "keywords": sorted(list(k))}
                    for t, r, k in history
                ],
                "turn_counter": recall._turn_counters.get(player_id, 0),
            }
        return data

    @staticmethod
    def _restore_recall(recall, data: Dict[str, Any]) -> None:
        """Restore context recall memory."""
        for player_id, recall_data in data.items():
            history = []
            for entry in recall_data.get("responses", []):
                history.append((
                    entry["turn"],
                    entry["response"],
                    set(entry.get("keywords", [])),
                ))
            recall._response_history[player_id] = history
            recall._turn_counters[player_id] = recall_data.get("turn_counter", 0)


# ── Social Fabric State Serializer ──

class SocialFabricSerializer:
    """Serializes and deserializes the entire SocialFabric world state."""

    @staticmethod
    def extract_state(fabric: SocialFabric) -> Dict[str, Any]:
        """Extract all social fabric state as a JSON-serializable dict."""
        state = {
            "version": 1,
            "timestamp": time.time(),

            "npcs": {
                npc_id: {
                    "character_id": p.character_id,
                    "name": p.name,
                    "faction_ids": sorted(list(p.faction_ids)),
                    "location": p.location,
                    "disposition": dict(p.disposition),
                    "known_gossip": sorted(list(p.known_gossip)),
                    "personality_traits": dict(p.personality_traits),
                    "social_tags": sorted(list(p.social_tags)),
                    "last_active": p.last_active,
                }
                for npc_id, p in fabric._npcs.items()
            },

            "factions": {
                fid: {
                    "faction_id": f.faction_id,
                    "name": f.name,
                    "description": f.description,
                    "members": sorted(list(f.members)),
                    "leader": f.leader,
                    "values": dict(f.values),
                    "created_at": f.created_at,
                }
                for fid, f in fabric._factions.items()
            },

            "faction_relations": {
                f"{k[0]}|{k[1]}": v.value if hasattr(v, 'value') else str(v)
                for k, v in fabric._faction_relations.items()
            },

            "gossip": {
                gid: {
                    "gossip_id": g.gossip_id,
                    "content": g.content,
                    "source_npc": g.source_npc,
                    "subject": g.subject,
                    "priority": g.priority.value,
                    "truth_value": g.truth_value,
                    "decay_per_hop": g.decay_per_hop,
                    "hops": g.hops,
                    "heard_by": sorted(list(g.heard_by)),
                    "created_at": g.created_at,
                    "tags": sorted(list(g.tags)),
                }
                for gid, g in fabric._gossip.items()
            },

            "groups": {
                gid: {
                    "group_id": g.group_id,
                    "location": g.location,
                    "participants": {
                        pid: role.value for pid, role in g.participants.items()
                    },
                    "topic": g.topic,
                    "started_at": g.started_at,
                    "max_messages": g.max_messages,
                    "active": g.active,
                    "messages": [
                        {
                            "message_id": m.message_id,
                            "sender_id": m.sender_id,
                            "content": m.content,
                            "intent": m.intent,
                            "emotion": m.emotion,
                            "target_id": m.target_id,
                            "group_id": m.group_id,
                            "timestamp": m.timestamp,
                        }
                        for m in g.messages
                    ],
                }
                for gid, g in fabric._groups.items()
            },

            "metrics": {
                "total_messages": fabric._total_messages,
                "total_gossip_spread": fabric._total_gossip_spread,
                "total_npc_interactions": fabric._total_npc_interactions,
            },
        }
        return state

    @staticmethod
    def restore_state(fabric: SocialFabric, state: Dict[str, Any]) -> None:
        """Restore social fabric state from a saved dict."""
        fabric.reset()

        # Restore factions first (NPCs reference them)
        for fid, f_data in state.get("factions", {}).items():
            faction = Faction(
                faction_id=f_data["faction_id"],
                name=f_data["name"],
                description=f_data.get("description", ""),
                members=set(f_data.get("members", [])),
                leader=f_data.get("leader"),
                values=f_data.get("values", {}),
                created_at=f_data.get("created_at", time.time()),
            )
            fabric._factions[fid] = faction

        # Restore faction relations
        for key_str, rel_val in state.get("faction_relations", {}).items():
            parts = key_str.split("|")
            if len(parts) == 2:
                fabric._faction_relations[tuple(parts)] = FactionRelation(rel_val)

        # Restore NPCs
        for npc_id, n_data in state.get("npcs", {}).items():
            profile = NPCProfile(
                character_id=n_data["character_id"],
                name=n_data["name"],
                faction_ids=set(n_data.get("faction_ids", [])),
                location=n_data.get("location", "unknown"),
                disposition=n_data.get("disposition", {}),
                known_gossip=set(n_data.get("known_gossip", [])),
                personality_traits=n_data.get("personality_traits", {}),
                social_tags=set(n_data.get("social_tags", [])),
                last_active=n_data.get("last_active", time.time()),
            )
            fabric._npcs[npc_id] = profile

        # Restore gossip
        for gid, g_data in state.get("gossip", {}).items():
            gossip = GossipItem(
                gossip_id=g_data["gossip_id"],
                content=g_data["content"],
                source_npc=g_data["source_npc"],
                subject=g_data.get("subject"),
                priority=GossipPriority(g_data.get("priority", 1)),
                truth_value=g_data.get("truth_value", 1.0),
                decay_per_hop=g_data.get("decay_per_hop", 0.15),
                hops=g_data.get("hops", 0),
                heard_by=set(g_data.get("heard_by", [])),
                created_at=g_data.get("created_at", time.time()),
                tags=set(g_data.get("tags", [])),
            )
            fabric._gossip[gid] = gossip

        # Restore groups
        for gid, grp_data in state.get("groups", {}).items():
            group = GroupConversation(
                group_id=grp_data["group_id"],
                location=grp_data.get("location", "unknown"),
                topic=grp_data.get("topic", "general"),
                started_at=grp_data.get("started_at", time.time()),
                max_messages=grp_data.get("max_messages", 50),
                active=grp_data.get("active", True),
            )
            for pid, role_val in grp_data.get("participants", {}).items():
                group.participants[pid] = ConversationRole(role_val)
            for m_data in grp_data.get("messages", []):
                msg = NPCMessage(
                    message_id=m_data["message_id"],
                    sender_id=m_data["sender_id"],
                    content=m_data["content"],
                    intent=m_data.get("intent", "chat"),
                    emotion=m_data.get("emotion", "neutral"),
                    target_id=m_data.get("target_id"),
                    group_id=m_data.get("group_id"),
                    timestamp=m_data.get("timestamp", time.time()),
                )
                group.messages.append(msg)
            fabric._groups[gid] = group

        # Restore metrics
        metrics = state.get("metrics", {})
        fabric._total_messages = metrics.get("total_messages", 0)
        fabric._total_gossip_spread = metrics.get("total_gossip_spread", 0)
        fabric._total_npc_interactions = metrics.get("total_npc_interactions", 0)


# ── Save Manager (Top-Level Save/Load) ──

class SaveManager:
    """
    Top-level save/load manager that coordinates persistence of
    all Synthesus subsystems into a single save directory.

    Save directory structure:
        save_dir/
            manifest.json          — Save metadata
            conscious_state.json    — Core conscious state layers
            npcs/
                {character_id}.json  — Per-NPC cognitive state
            social_fabric.json      — World social state
            world_state.json        — Economy, weather, quests
    """

    def __init__(self, save_dir: str):
        self.save_dir = Path(save_dir)
        self._npc_dir = self.save_dir / "npcs"

    def save(
        self,
        engines: Optional[Dict[str, Any]] = None,
        fabric: Optional[SocialFabric] = None,
        world_state: Optional[Dict[str, Any]] = None,
        conscious_state: Optional[ConsciousState] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Save all state to disk.

        Args:
            engines: Dict of character_id → CognitiveEngine instances
            fabric: SocialFabric instance
            world_state: Arbitrary world state dict (economy, weather, etc.)
            conscious_state: ConsciousState instance for the global reasoning state
            metadata: Extra metadata to include in manifest

        Returns: manifest dict
        """
        start = time.time()

        # Create directories
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self._npc_dir.mkdir(parents=True, exist_ok=True)

        saved_npcs = []
        saved_files = []

        # Save per-NPC cognitive state
        if engines:
            for char_id, engine in engines.items():
                npc_state = CognitiveStateSerializer.extract_state(engine)
                npc_path = self._npc_dir / f"{char_id}.json"
                npc_path.write_text(json.dumps(npc_state, indent=2, default=str))
                saved_npcs.append(char_id)
                saved_files.append(str(npc_path))

        # Save conscious state
        if conscious_state is not None:
            conscious_path = self.save_dir / "conscious_state.json"
            conscious_state_data = ConsciousStateSerializer.extract_state(conscious_state)
            conscious_path.write_text(json.dumps(conscious_state_data, indent=2, default=str))
            saved_files.append(str(conscious_path))

        # Save social fabric
        if fabric:
            fabric_state = SocialFabricSerializer.extract_state(fabric)
            fabric_path = self.save_dir / "social_fabric.json"
            fabric_path.write_text(json.dumps(fabric_state, indent=2, default=str))
            saved_files.append(str(fabric_path))

        # Save world state
        if world_state:
            world_path = self.save_dir / "world_state.json"
            world_path.write_text(json.dumps(world_state, indent=2, default=str))
            saved_files.append(str(world_path))

        elapsed = (time.time() - start) * 1000

        # Write manifest
        manifest = {
            "version": 1,
            "timestamp": time.time(),
            "elapsed_ms": round(elapsed, 2),
            "npcs_saved": saved_npcs,
            "files": saved_files,
            "has_conscious_state": conscious_state is not None,
            "has_social_fabric": fabric is not None,
            "has_world_state": world_state is not None,
            "metadata": metadata or {},
        }
        manifest_path = self.save_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))

        return manifest

    def load(self) -> Dict[str, Any]:
        """
        Load all state from disk.

        Returns:
        {
            "manifest": dict,
            "npc_states": {character_id: state_dict, ...},
            "conscious_state": dict or None,
            "social_fabric_state": dict or None,
            "world_state": dict or None,
        }
        """
        start = time.time()
        manifest_path = self.save_dir / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"No save found at {self.save_dir}")

        manifest = json.loads(manifest_path.read_text())

        # Load NPC states
        npc_states = {}
        if self._npc_dir.exists():
            for npc_file in self._npc_dir.glob("*.json"):
                char_id = npc_file.stem
                npc_states[char_id] = json.loads(npc_file.read_text())

        conscious_state = None
        conscious_path = self.save_dir / "conscious_state.json"
        if conscious_path.exists():
            conscious_state = json.loads(conscious_path.read_text())

        # Load social fabric
        fabric_state = None
        fabric_path = self.save_dir / "social_fabric.json"
        if fabric_path.exists():
            fabric_state = json.loads(fabric_path.read_text())

        # Load world state
        world_state = None
        world_path = self.save_dir / "world_state.json"
        if world_path.exists():
            world_state = json.loads(world_path.read_text())

        elapsed = (time.time() - start) * 1000

        return {
            "manifest": manifest,
            "npc_states": npc_states,
            "conscious_state": conscious_state,
            "social_fabric_state": fabric_state,
            "world_state": world_state,
            "load_elapsed_ms": round(elapsed, 2),
        }

    def restore_engines(
        self,
        engines: Dict[str, Any],
        npc_states: Dict[str, Dict],
    ) -> List[str]:
        """
        Restore loaded NPC states into live CognitiveEngine instances.
        Returns list of character_ids that were restored.
        """
        restored = []
        for char_id, state in npc_states.items():
            if char_id in engines:
                CognitiveStateSerializer.restore_state(engines[char_id], state)
                restored.append(char_id)
        return restored

    def restore_fabric(
        self,
        fabric: SocialFabric,
        fabric_state: Dict[str, Any],
    ) -> None:
        """Restore social fabric from loaded state."""
        SocialFabricSerializer.restore_state(fabric, fabric_state)

    def restore_conscious_state(self, conscious_state: ConsciousState, state: Dict[str, Any]) -> None:
        """Restore the global conscious state from loaded state."""
        ConsciousStateSerializer.restore_state(conscious_state, state)

    def exists(self) -> bool:
        """Check if a save exists at this path."""
        return (self.save_dir / "manifest.json").exists()

    def delete(self) -> bool:
        """Delete this save directory entirely."""
        if self.save_dir.exists():
            shutil.rmtree(self.save_dir)
            return True
        return False

    def list_saved_npcs(self) -> List[str]:
        """List character IDs in the save without loading full state."""
        if not self._npc_dir.exists():
            return []
        return [f.stem for f in self._npc_dir.glob("*.json")]


# ── Convenience: import deque for restore ──
from collections import deque
