"""
Cognitive Engine — The NPC Right Hemisphere
Orchestrates all 9 cognitive modules into a single NPC brain.

The CognitiveEngine is the main entry point. It:
1. Receives ML Swarm signals (intent, sentiment, player emotion)
2. Runs the query through all 9 cognitive modules
3. Returns a fully assembled, context-aware response
4. Reports whether it handled locally or needs escalation

Left Hemisphere: Hybrid token + semantic matching.
- Token matcher: fast keyword/substring overlap
- Semantic matcher: SwarmEmbedder (TF-IDF + SVD) + FAISS cosine similarity
- Hybrid score = max(token_score, semantic_score * confidence)

ML Swarm integration: IntentClassifier, SentimentAnalyzer, EmotionDetector,
BehaviorPredictor feed signals into emotion state machine, escalation gate,
and response composition. Total cost: <1ms for ML + ~2-5ms for cognitive.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .conversation_tracker import ConversationTracker, Topic
from .emotion_state_machine import EmotionStateMachine, EmotionState
from .response_compositor import ResponseCompositor
from .relationship_tracker import RelationshipTracker
from .world_state_reactor import WorldStateReactor, WorldReaction
from .escalation_gate import EscalationGate
from .personality_bank import PersonalityBank
from .knowledge_graph import KnowledgeGraph, load_knowledge_from_file, load_knowledge_from_dict
from .context_recall import ContextRecall
from .semantic_matcher import SemanticMatcher
from .goal_stack import GoalStack
from .proactive_engine import ProactiveEngine
from .agent_dispatcher import AgentDispatcher
from .pattern_engine import PatternEngine
from .dialogue_memory import DialogueMemory


class _AwaitableQueryResult:
    """
    A helper class that allows a coroutine to be awaited later.
    Used to bridge synchronous and asynchronous query processing.
    """
    def __init__(self, coro_factory):
        self._coro_factory = coro_factory

    def __await__(self):
        return self._coro_factory().__await__()


# Stop words (duplicated for self-contained pattern matching)
_STOP = {
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


def _tokenize(text: str) -> set:
    """
    Tokenizes input text into a set of content words, excluding stop words.

    Args:
        text: The raw string to tokenize.

    Returns:
        A set of lowercase alphanumeric tokens.
    """
    return set(re.findall(r'[a-z]+', text.lower())) - _STOP


class CognitiveEngine:
    """
    The NPC Right Hemisphere.

    Combines:
    - ConversationTracker (multi-turn context)
    - EmotionStateMachine (emotional reactions)
    - ResponseCompositor (varied response assembly)
    - RelationshipTracker (persistent relationships)
    - WorldStateReactor (world event awareness)
    - EscalationGate (smart routing to Thinking Layer)
    - PersonalityBank (pre-authored creative responses)
    - KnowledgeGraph (entity knowledge base)
    - ContextRecall (NPC references its own prior statements)

    Plus the left hemisphere pattern matcher.
    """

    def __init__(
        self,
        character_id: str,
        bio: Optional[Dict[str, Any]] = None,
        patterns: Optional[Dict[str, Any]] = None,
        persist_dir: Optional[str] = None,
        char_dir: Optional[str] = None,
        kal_client: Optional[Any] = None,
        substrate: Any = None,
        knowledge_cloud: Any = None
    ):
        """
        Initializes the CognitiveEngine for a specific character.

        Args:
            character_id: Unique identifier for the character.
            bio: Dictionary containing character biography and metadata.
            patterns: Dictionary of response patterns and triggers.
            persist_dir: Directory for persisting character-specific state.
            char_dir: Directory containing character-specific asset files.
            kal_client: Client for interacting with the Knowledge & Logic service.
            substrate: The universal substrate for shared world state.
            knowledge_cloud: The shared knowledge cloud for world lore.
        """
        self.character_id = character_id
        self.substrate = substrate
        self.knowledge_cloud = knowledge_cloud
        self._persist_dir = Path(persist_dir) if persist_dir else None
        self._char_dir = Path(char_dir) if char_dir else None

        # 1. Load Bio & Patterns (Prioritize passed-in, fallback to empty)
        self.bio = bio or {}
        self.patterns = patterns or {}

        # Merge Substrate if available (Additive)
        if self.substrate:
            sub_bio = self.substrate.get_parameter(f"char_{character_id}.bio")
            if sub_bio and isinstance(sub_bio, dict):
                # Update with cloud values if present
                self.bio.update(sub_bio.get("value") or {})

            sub_pats = self.substrate.get_parameter(f"char_{character_id}.patterns")
            if sub_pats and isinstance(sub_pats, dict):
                # Update with cloud patterns if present
                self.patterns.update(sub_pats.get("value") or {})

        # Module 8: Knowledge Graph
        knowledge = self._load_knowledge(self.bio, character_id)
        if self.substrate:
            # Merge with Universal Knowledge (Right Hemisphere)
            sub_kg = self.substrate.get_parameter(f"char_{character_id}.knowledge")
            if sub_kg and isinstance(sub_kg, dict):
                sub_kg_value = sub_kg.get("value", {})
                if isinstance(sub_kg_value, dict):
                    # Substrate value is a wrapped dict: {character_id, version, entities}
                    # Only pass the entities sub-dict
                    entities_dict = sub_kg_value.get("entities", {})
                    if entities_dict and isinstance(entities_dict, dict):
                        knowledge.update(load_knowledge_from_dict(entities_dict))
                    elif sub_kg_value and not entities_dict:
                        # Fallback: treat the whole value as an entities dict
                        # (handles direct {entity_id: entity_data} format)
                        knowledge.update(load_knowledge_from_dict(sub_kg_value))

        self.knowledge = KnowledgeGraph(knowledge=knowledge)

        # Extract known entities
        known_entities = self._extract_known_entities(self.bio, self.patterns, self.knowledge)

        # Initialize modules
        self.tracker = ConversationTracker(known_entities=known_entities)
        self.emotion = EmotionStateMachine()
        self.compositor = ResponseCompositor()
        self.relationships = RelationshipTracker(
            npc_id=character_id,
            persist_path=str(self._persist_dir / "relationships.json") if self._persist_dir else None,
        )
        self.world = WorldStateReactor(
            reactions=self._build_world_reactions(self.bio)
        )
        self.gate = EscalationGate()

        # Module 7: Personality Bank
        archetype = self.bio.get("archetype", self.bio.get("role", "merchant")).lower()
        personality_file = str(self._char_dir / "personality.json") if self._char_dir else None
        self.personality = PersonalityBank(
            archetype=archetype,
            personality_file=personality_file,
        )
        if self.substrate:
            sub_pb = self.substrate.get_parameter(f"char_{character_id}.personality")
            if sub_pb and isinstance(sub_pb, dict):
                self.personality.load_from_dict(sub_pb.get("value", {}))

        self.recall = ContextRecall()
        self.goal_stack = GoalStack()
        self.proactive_engine = ProactiveEngine()
        # Phase 13: Lore Volunteer Trigger
        from .proactive_engine import ProactiveTrigger, TriggerType
        self.proactive_engine.add_trigger(ProactiveTrigger(
            trigger_id="lore_gossip",
            trigger_type=TriggerType.LORE_VOLUNTEER,
            message="", # Dynamically filled by the trigger check
            priority=0.8, # Higher than standard greetings
            cooldown_seconds=600 # Don't gossip too often
        ))
        self.agent_dispatcher = AgentDispatcher()
        self.patterns_gen = PatternEngine(substrate=self.substrate)
        self.kal_client = kal_client

        self._memory_store = None

        # Module 15: Dialogue Memory (Multi-turn conversation support)
        dialogue_memory_path = str(self._persist_dir / "dialogue_memory") if self._persist_dir else "data/dialogue_memory"
        self.dialogue_memory = DialogueMemory(dialogue_memory_path)

        # Pre-process patterns
        self._synthetic = self.patterns.get("synthetic_patterns", [])
        self._generic = self.patterns.get("generic_patterns", [])
        self._fallback_text = self.patterns.get(
            "fallback",
            f"I am {self.bio.get('name', character_id)}. Could you rephrase?"
        )

        # Module 10: Semantic Matcher
        self.semantic = SemanticMatcher(similarity_floor=0.35)
        try:
            self.semantic.build_index(self._synthetic, self._generic)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"SemanticMatcher init failed: {e}")
            self.semantic._enabled = False

        # Stats
        self._total_queries = 0
        self._local_handled = 0
        self._escalated = 0
        self._knowledge_handled = 0
        self._personality_handled = 0
        self._recall_handled = 0
        self._semantic_wins = 0  # Times semantic beat token matching
        self._kal_handled = 0   # V4: Times KAL provided useful context
        self._generative_handled = 0  # Phase 6: Times PatternEngine synthesized response
        self._cloud_handled = 0  # Knowledge Cloud: Times shared world knowledge answered

    @staticmethod
    def _extract_known_entities(
        bio: Dict, patterns: Dict, knowledge_graph: Optional[KnowledgeGraph] = None,
    ) -> Dict[str, str]:
        """Extract named entities from bio, patterns, and knowledge graph.

        Entity sources (in priority order):
        1. Knowledge graph entities (most reliable — typed and aliased)
        2. NPC's own name from bio
        3. Capitalized proper nouns found in pattern response_templates
        """
        entities = {}

        # Source 1: Knowledge graph provides typed, aliased entities
        if knowledge_graph:
            kg_entities = knowledge_graph.get_known_entities()
            entities.update(kg_entities)

        # Source 2: NPC's own name from bio
        name = bio.get("name", bio.get("display_name", ""))
        if name:
            for part in name.split():
                if len(part) > 2:
                    entities[part] = "SELF"

        # Source 3: Scan pattern response_templates for capitalized proper nouns
        for pat_list in [patterns.get("synthetic_patterns", []),
                         patterns.get("generic_patterns", [])]:
            for pat in pat_list:
                text = pat.get("response_template", "")
                words = text.split()
                for j, w in enumerate(words):
                    if j == 0:
                        continue
                    prev = words[j - 1] if j > 0 else ""
                    if prev.endswith(('.', '!', '?', '"')):
                        continue
                    clean = re.sub(r'[^a-zA-Z]', '', w)
                    if clean and clean[0].isupper() and len(clean) > 2:
                        low = clean.lower()
                        if low not in _STOP and clean not in entities:
                            # Default to NPC if not already typed by KG
                            entities[clean] = "NPC"

        return entities

    async def _synthesize_knowledge_response(
        self,
        cloud_results: List[Dict[str, Any]],
        query: str,
        player_id: str,
        ml_context: Optional[Dict[str, Any]] = None,
        world_state: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Synthesizes a natural, character-voiced response from one or more knowledge cloud results.

        HYPOTHESIS INTEGRATION (MVP-1.0):
          This method now implements the core "Retrieval + Chaining + Slot Filling ≈ Generation"
          hypothesis by using two new modules:

          1. SequenceLinker: Chains multiple patterns into coherent multi-sentence responses
          2. SlotFiller: Binds [entity], [emotion], [time], [topic] variables deterministically

          The existing PatternEngine.synthesize_knowledge() is retained as a fallback for
          comparison and robustness.
        """
        if not cloud_results:
            return ""

        if isinstance(cloud_results, dict):
            cloud_results = [cloud_results]

        ml_context = ml_context or {}

        # ── NEW: SequenceLinker + SlotFiller Integration ─────────────────────
        try:
            from .sequence_linker import SequenceLinker
            from .slot_filler import SlotFiller

            # Build context vector from ML Swarm signals
            context_vector = {
                "intent": ml_context.get("intent", "unknown"),
                "emotion": ml_context.get("player_emotion", "neutral"),
                "sentiment": ml_context.get("sentiment", "neutral"),
                "predicted_action": ml_context.get("predicted_action", ""),
                "escalation_risk": ml_context.get("escalation_risk", 0.0),
                "engagement_score": ml_context.get("engagement_score", 0.5),
            }

            # Extract world state entities if not provided
            if not world_state or not world_state.get("entities"):
                world_state = {"entities": [r.get("entity_id", "") for r in cloud_results]}

            # Step 1: Build chain using SequenceLinker
            linker = SequenceLinker(
                transitions_path="data/knowledge_cloud/transitions.json"
            )
            chain_plan = linker.build_chain(
                knowledge_results=cloud_results,
                context_vector=context_vector,
                world_state=world_state,
                dialogue_memory=self.dialogue_memory.get_recent_turns(
                    self.dialogue_memory.load_context(player_id), limit=5
                ) if player_id else [],
                query=query,
            )

            # Step 2: Fill slots using SlotFiller
            filler = SlotFiller()
            fill_result = filler.fill_slots(
                chain_plan=chain_plan,
                world_state=world_state,
                dialogue_memory=[],  # Could pass actual memory from self.recall
                query=query,
                context_vector=context_vector,
            )

            # Step 3: Render if we have a valid chain
            if chain_plan.steps and fill_result.all_satisfied:
                # Use per-step bindings for maximum precision
                composed_response = linker.render_chain_text(chain_plan, fill_result.step_bindings)

                if composed_response and len(composed_response.split()) > 4:
                    # Add depth-aware prefix
                    depth_ranks = {"intimate": 4, "familiar": 3, "acquainted": 2, "rumor": 1, "unknown": 0}
                    max_depth = max(cloud_results, key=lambda x: depth_ranks.get(x.get("depth", "unknown"), 0)).get("depth", "acquainted")

                    prefixes = {
                        "rumor": ["I've heard whispers that...", "Some say...", "Rumor has it that..."],
                        "acquainted": ["It's common knowledge that...", "Most people know...", "I've heard tell of..."],
                        "familiar": ["I'm fairly certain that...", "If memory serves...", "I recall hearing that..."],
                        "intimate": ["I know for a fact that...", "Listen closely, because...", "I can tell you exactly..."],
                    }

                    import random
                    prefix_list = prefixes.get(max_depth, prefixes["acquainted"])
                    prefix = random.choice(prefix_list)

                    return f"{prefix} {composed_response}"

        except Exception as e:
            # Log but don't fail — fall through to legacy synthesis
            import logging
            logging.getLogger(__name__).info(f"SequenceLinker/SlotFiller path skipped: {e}")

        # ── LEGACY: PatternEngine Synthesis (Fallback) ────────────────────────
        # This path remains for:
        #   1. Comparison against the new chaining approach
        #   2. Robustness when chaining fails
        #   3. Gradual migration as we validate the hypothesis

        # 1. Prepare raw factual material from all entities
        knowledge_texts = []
        entity_names = []

        all_facts = []
        for res in cloud_results:
            description = res.get("response", "")
            facts = res.get("facts", [])
            knowledge_texts.append(description)
            knowledge_texts.extend(facts)
            all_facts.extend(facts)
            entity_names.append(res.get("entity_name", "the unknown"))

        # 2. Relational Bridge Logic
        # Check if any mentioned entities have known relationships with each other
        entity_ids = [res["entity_id"] for res in cloud_results]
        bridge_sentences = []
        for res in cloud_results:
            relations = res.get("related", {})
            for rel_type, target_id in relations.items():
                if target_id in entity_ids:
                    # Found a connection! Ironhaven governed_by Duke Aldric
                    target_name = next((r["entity_name"] for r in cloud_results if r["entity_id"] == target_id), target_id)
                    bridge_sentences.append(f"The {res['entity_name']} is {rel_type.replace('_', ' ')} {target_name}.")

        # Phase 12: Boost facts relative to description to ensure they appear in synthesis
        knowledge_texts.extend(all_facts * 3)

        # Inject bridges into knowledge corpus with extra weight
        knowledge_texts.extend(bridge_sentences * 2)

        # 3. Prepare character voice material
        voice_samples = []
        for pat in self._synthetic[:20]:
            if "response" in pat:
                voice_samples.append(pat["response"])
            elif "responses" in pat and pat["responses"]:
                 voice_samples.append(pat["responses"][0])

        # 4. Add Depth-Aware Hedging (based on the highest depth result)
        depth_ranks = {"intimate": 4, "familiar": 3, "acquainted": 2, "rumor": 1, "unknown": 0}
        max_depth = max(cloud_results, key=lambda x: depth_ranks.get(x.get("depth", "unknown"), 0)).get("depth", "acquainted")

        prefixes = {
            "rumor": ["I've heard whispers that...", "Some say...", "Rumor has it that...", "The word on the street is..."],
            "acquainted": ["It's common knowledge that...", "Most people know...", "I've heard tell of...", "They say..."],
            "familiar": ["I'm fairly certain that...", "If memory serves...", "I recall hearing that...", "Ah, yes..."],
            "intimate": ["I know for a fact that...", "Listen closely, because...", "I can tell you exactly...", "Make no mistake..."],
        }

        import random
        prefix_list = prefixes.get(max_depth, prefixes["acquainted"])
        prefix = random.choice(prefix_list)

        # 5. Attempt Synthesis via PatternEngine
        try:
            synthesized = await self.patterns_gen.synthesize_knowledge(
                knowledge_texts=knowledge_texts,
                voice_texts=voice_samples,
                query=query,
                temperature=0.7
            )

            if synthesized and len(synthesized.split()) > 4:
                return f"{prefix} {synthesized}"
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Knowledge Synthesis failed: {e}")

        # 6. Fallback: Concatenate descriptions if synthesis failed
        import re
        import logging
        logging.getLogger(__name__).info("SequenceLinker FAILED or SKIPPED, falling back to legacy synthesis")
        synthesized = " ".join([res.get("response", "") for res in cloud_results])
        # Clean up any remaining tags
        synthesized = re.sub(r"\[\?[^\]]+\]", "", synthesized)  # Optional tags
        synthesized = re.sub(r"\[[^\]]+\]", "", synthesized)     # Required tags
        synthesized = re.sub(r"\s+", " ", synthesized).strip()
        return f"{prefix} {synthesized}" if synthesized else prefix

    def _load_knowledge(self, bio: Dict, character_id: str) -> Dict:
        """Load knowledge graph from character's knowledge.json file.

        Falls back to empty dict if no file exists.
        """
        if self._char_dir:
            kg_path = self._char_dir / "knowledge.json"
            if kg_path.exists():
                return load_knowledge_from_file(str(kg_path))

        # Check if bio has inline knowledge data
        if "knowledge" in bio and isinstance(bio["knowledge"], dict):
            return load_knowledge_from_dict(bio["knowledge"])

        return {}

    @staticmethod
    def _build_world_reactions(bio: Dict) -> List[WorldReaction]:
        """Build default world reactions based on character role."""
        reactions = [
            # Town under attack: NPC is afraid, shop patterns disabled
            WorldReaction(
                flag_name="TOWN_UNDER_ATTACK",
                flag_value=True,
                emotion_override=EmotionState.AFRAID,
                disabled_patterns=set(),  # Individual chars override this
                greeting_override="Thank the gods you're here! The town is under attack!",
            ),
            # Night time: shop closed
            WorldReaction(
                flag_name="TIME_OF_DAY",
                flag_value="night",
                greeting_override="Shop's closed for the night. Come back in the morning.",
            ),
            # Player is a known criminal
            WorldReaction(
                flag_name="PLAYER_REPUTATION",
                flag_value="criminal",
                emotion_override=EmotionState.SUSPICIOUS,
            ),
        ]
        return reactions

    def _match_pattern_token(self, query: str) -> Tuple[Optional[Dict], float]:
        """
        Token-based pattern matching (Left Hemisphere v1).
        Fast keyword/substring overlap with geometric mean scoring.
        Returns (pattern_dict, score).
        """
        q = query.strip().lower()
        q_tokens = _tokenize(q)

        best_match = None
        best_score = 0.0

        for pat_list, is_generic in [(self._synthetic, False), (self._generic, True)]:
            for pat in pat_list:
                triggers = pat.get("trigger", [])
                if isinstance(triggers, str):
                    triggers = [triggers]
                conf = pat.get("confidence", 0.5)

                for t in triggers:
                    t_lower = t.lower().strip()
                    t_tokens = _tokenize(t_lower)

                    # Exact match
                    if t_lower == q:
                        return pat, 1.0

                    score = 0.0
                    overlap = q_tokens & t_tokens
                    n_overlap = len(overlap)

                    # Full-trigger substring
                    if t_lower in q and len(t_lower) >= 4:
                        specificity = len(t_lower) / max(len(q), 1)
                        score = conf * (0.7 + 0.3 * specificity)

                    # Token overlap
                    elif t_tokens and q_tokens:
                        min_required = 1 if (len(t_tokens) <= 2 or len(q_tokens) <= 2) else 2
                        if n_overlap >= min_required:
                            trigger_cov = n_overlap / len(t_tokens)
                            query_cov = n_overlap / len(q_tokens)
                            geo_mean = (trigger_cov * query_cov) ** 0.5
                            score = geo_mean * conf

                    if is_generic:
                        score *= 0.7

                    if score > best_score:
                        best_score = score
                        best_match = pat

        return best_match, best_score

    def _match_pattern(self, query: str) -> Tuple[Optional[Dict], float]:
        """
        Hybrid pattern matching (Left Hemisphere v2).

        Runs BOTH token matching and semantic matching in parallel,
        then takes the better result. This ensures:
        - Exact/substring matches still get 1.0 scores (token wins)
        - Paraphrases, slang, indirect refs get caught (semantic wins)
        - No regression on existing behavior

        Semantic score is scaled by the pattern's confidence value
        to maintain consistency with the token scorer.

        Returns (pattern_dict, hybrid_score).
        """
        # Run token matcher (always available, ~0.1ms)
        token_match, token_score = self._match_pattern_token(query)

        # Short-circuit: perfect token match needs no semantic check
        if token_score >= 1.0:
            return token_match, token_score

        # Run semantic matcher (if available, ~12ms)
        if not self.semantic._enabled:
            return token_match, token_score

        sem_pat, sem_trigger, sem_cosine, sem_generic = self.semantic.get_best_match(query)

        if sem_pat is None:
            return token_match, token_score

        # Scale semantic cosine score by pattern confidence
        # (mirrors how token scorer uses conf multiplier)
        sem_conf = sem_pat.get("confidence", 0.5)
        sem_score = sem_cosine * sem_conf
        if sem_generic:
            sem_score *= 0.7

        # Take the better result
        if sem_score > token_score:
            self._semantic_wins += 1
            return sem_pat, sem_score

        return token_match, token_score

    def _build_result(
        self,
        response: Optional[str],
        source: str,
        confidence: float,
        emotion: Any,
        rel_result: Dict[str, Any],
        conv_context: Dict[str, Any],
        world_result: Dict[str, Any],
        match_score: float,
        pattern_id: Optional[str],
        start_time: float,
        actions_taken: List[Dict[str, Any]],
        ml_context: Optional[Dict[str, Any]] = None,
        kal_context: Optional[Dict[str, Any]] = None,
        escalation: Optional[Dict[str, Any]] = None,
        debug_extra: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        latency_ms = round((time.time() - start_time) * 1000, 2)
        return {
            "response": response,
            "source": source,
            "confidence": confidence,
            "emotion": emotion.value if hasattr(emotion, "value") else str(emotion),
            "relationship": rel_result,
            "conversation": conv_context,
            "world": world_result,
            "context": context or {},
            "match_score": match_score,
            "pattern_id": pattern_id,
            "latency_ms": latency_ms,
            "actions_taken": actions_taken,
            "ml_context": ml_context or {},
            "kal_context": kal_context or {},
            "escalation": escalation,
            "debug": {
                "latency_ms": latency_ms,
                "match_score": match_score,
                "pattern_matched": pattern_id,
                "topic": conv_context.get("active_topic").value if hasattr(conv_context.get("active_topic"), "value") else str(conv_context.get("active_topic")),
                "turn_count": conv_context.get("turn_count", 0),
                **(debug_extra or {})
            }
        }

    def set_shared_layers(self, knowledge_cloud: Any = None, substrate: Any = None, memory_store: Any = None) -> None:
        if knowledge_cloud is not None:
            self.knowledge_cloud = knowledge_cloud
        if substrate is not None:
            self.substrate = substrate
        if memory_store is not None:
            self._memory_store = memory_store

    def process_query(
        self,
        player_id: str,
        query: str,
        thinking_layer_available: bool = False,
        ml_context: Optional[Dict[str, Any]] = None,
    ):
        """
        Processes a player query, either synchronously or asynchronously.

        Args:
            player_id: Unique identifier for the player.
            query: The player's input text.
            thinking_layer_available: Whether to allow escalation to a thinking layer.
            ml_context: Optional context from ML services (intent, sentiment, etc.).

        Returns:
            An awaitable result that resolves to a dictionary of response data.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._process_query_async(player_id, query, thinking_layer_available, ml_context))
        return _AwaitableQueryResult(lambda: self._process_query_async(player_id, query, thinking_layer_available, ml_context))

    async def _process_query_async(
        self,
        player_id: str,
        query: str,
        thinking_layer_available: bool = False,
        ml_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        The main entry point. Process a player query through the full
        cognitive engine pipeline.

        Args:
            player_id: Unique player identifier
            query: The player's query text
            thinking_layer_available: Whether escalation to thinking layer is possible
            ml_context: Pre-computed ML Swarm signals from the production server:
                - intent: classified player intent (e.g. "greeting", "shop_buy", "lore")
                - sentiment: emotional valence ("positive", "negative", "neutral", etc.)
                - player_emotion: detected emotion ("joy", "anger", "fear", etc.)
                - emotion_intensity: 0-1 intensity of detected emotion
                - predicted_action: next likely player action
                - engagement_score: 0-1 engagement probability
                - escalation_risk: 0-1 escalation risk score

        Returns:
            Dict with response, confidence, emotion, relationship, debug info.
        """
        start_time = time.time()
        self._total_queries += 1
        ml_context = ml_context or {}

        # ── Step 0: Agent Dispatcher (Tool Use) ──
        actions_taken = []
        tool_result = await self.agent_dispatcher.evaluate_and_dispatch(query, self.character_id)
        if tool_result:
            actions_taken.append({
                "description": f"Used tool {tool_result['tool']} ({tool_result['action']})",
                "type": "tool_use",
                "tool": tool_result['tool'],
                "action": tool_result['action'],
                "result": tool_result
            })
            # Inject tool context into the query so subsequent modules can use it
            # (e.g. if the user asked to summarize a site, the RAG/Pattern match sees the site content)
            tool_context = tool_result.get("context", "")
            query = f"{query}\n\n[External Tool Context]: {tool_context}"
            # Record that we used a tool in the local history store (tracked by ConsciousState if present)
            # For CognitiveEngine, we just proceed with the augmented query.

        # ── Step 0.5: KAL Pre-fetch (V4 — Abductive Retrieval) ──
        # Before reasoning starts, query KAL for relevant knowledge nodes
        # based on extracted entities and namespaces from the query.
        kal_context: Optional[Dict[str, Any]] = None
        # 2. KAL (Knowledge & Logic) Enrichment
        if self.kal_client is not None:
            try:
                # Derive namespaces from character archetype
                archetype = self.bio.get("archetype", self.bio.get("role", "")).lower()
                # V4: Multi-namespace fan-out (Hemisphere-aware)
                char_domains = self.bio.get("knowledge_domains", [])
                namespaces = [f"char_{self.character_id}", "character_genome", "general"] + char_domains
                filters = {} # V4: Disable character filter to allow cross-character lore in this version

                kal_result = await self.kal_client.query_semantic(
                    question=query,
                    namespaces=namespaces,
                    filters=filters,
                    top_k=5,
                )

                if kal_result.results:
                    kal_context = {
                        "results": [n.dict() for n in kal_result.results],
                        "latency_ms": kal_result.retrieval_latency_ms,
                        "cache_hit": kal_result.cache_hit,
                    }
                    self._kal_handled += 1
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    f"KAL pre-fetch failed for {self.character_id}: {e}"
                )

        # ── Step 1: Conversation Tracker ──
        conv_context = self.tracker.process(player_id, query)
        keywords = conv_context["keywords"]

        # ── Step 2: Emotion State Machine ──
        # Feed ML-detected player emotion into the NPC's emotional response
        emotion_result = self.emotion.process(player_id, keywords)
        current_emotion = emotion_result["emotion"]

        # If ML Swarm detected strong player emotion, influence NPC reaction
        if ml_context.get("emotion_intensity", 0) > 0.5:
            player_emo = ml_context.get("player_emotion", "neutral")
            # Threatening players make NPC suspicious/afraid
            if player_emo in ("anger", "disgust"):
                from .emotion_state_machine import EmotionState
                if hasattr(EmotionState, 'SUSPICIOUS'):
                    self.emotion.force_state(player_id, EmotionState.SUSPICIOUS)
                    current_emotion = EmotionState.SUSPICIOUS
            elif player_emo == "fear":
                from .emotion_state_machine import EmotionState
                if hasattr(EmotionState, 'CONCERNED'):
                    self.emotion.force_state(player_id, EmotionState.CONCERNED)
                    current_emotion = EmotionState.CONCERNED

        # ── Step 3: Relationship Tracker ──
        rel_result = self.relationships.process(player_id, keywords)

        # ── Step 4: World State Reactor & Proactive Engine ──
        world_result = self.world.process()

        # Build global context for proactive/goal evaluation
        context = {
            "player_id": player_id,
            "query": query,
            "topic": conv_context["active_topic"],
            "world_flags": world_result.get("active_flags", {}),
            "relationship": {
                "trust": rel_result["trust"],
                "fondness": rel_result["fondness"],
                "respect": rel_result["respect"],
                "debt": rel_result["debt"],
                "tier": next((k for k, v in rel_result["tier"].items() if v), "stranger"),
                "interactions": rel_result.get("interactions", 0),
            },
            "last_interaction_time": self.tracker.get_state(player_id).last_interaction,
        }

        # 4. Proactive Lore Enrichment (Phase 13)
        if self.knowledge_cloud:
            # Fetch spicy rumors to pass to proactive engine
            rumors = self.knowledge_cloud.get_entries_by_depth("rumor", limit=3)
            context["active_lore"] = rumors

        # Check for proactive greeting override (goals/events/time)
        prefix_greeting = None
        if not self.goal_stack.get_active_goals(): # Only if no urgent goals blocking
            prefix_greeting = self.proactive_engine.check(player_id, context)

        # If proactive engine returned a lore-based message, treat it as a conversational hint.
        # Do not count it as cloud-handled here; the knowledge-cloud source is tracked below.

        # Apply world emotion override if set
        if world_result["emotion_override"] is not None:
            current_emotion = world_result["emotion_override"]
            self.emotion.force_state(player_id, current_emotion)

        # Check for greeting override (world events / proactive)
        greeting = prefix_greeting or world_result.get("greeting_override")
        lower_query = query.lower()
        is_greeting_query = bool(re.search(r"\b(hi|hello|hey|greetings|good morning|good afternoon|good evening)\b", lower_query))
        if conv_context["turn_count"] == 1 and greeting and is_greeting_query:
            response = greeting
            self.tracker.record_npc_response(player_id, response)
            self.recall.record_response(player_id, response)
            self._local_handled += 1
            return self._build_result(
                response=response,
                source="cognitive_engine",
                confidence=0.95,
                emotion=current_emotion,
                rel_result=rel_result,
                conv_context=conv_context,
                world_result=world_result,
                match_score=0.95,
                pattern_id="world_greeting_override",
                start_time=start_time,
                actions_taken=actions_taken,
            )

        # ── Step 4b: Context Recall Priority Check ──
        # If the player explicitly references something the NPC said earlier
        # ("you mentioned...", "you said...", "remember when..."),
        # context recall gets FIRST shot before pattern matching.
        # This prevents pattern triggers (e.g., "tomás") from hijacking
        # legitimate recall queries like "you mentioned Tomás earlier".
        emotion_str_pre = current_emotion.value if hasattr(current_emotion, 'value') else str(current_emotion)
        if self.recall._is_recall_query(query):
            cr_early = self.recall.process(
                player_id=player_id,
                query=query,
                emotion=emotion_str_pre,
            )
            if cr_early and cr_early.get("recall_type") != "not_found":
                response = cr_early["response"]
                self.tracker.record_npc_response(player_id, response)
                self._local_handled += 1
                self._recall_handled += 1
                return self._build_result(
                    response=response,
                    source="context_recall",
                    confidence=cr_early["confidence"],
                    emotion=current_emotion,
                    rel_result=rel_result,
                    conv_context=conv_context,
                    world_result=world_result,
                    match_score=cr_early["confidence"],
                    pattern_id=f"cr_{cr_early['recall_type']}",
                    start_time=start_time,
                    actions_taken=actions_taken,
                )

        # ── NEW: 4-Module Fallback Cascade (Prioritized Generative) ──
        # Before falling back to static patterns, try the brain modules:
        #   1. Pattern Engine   → generative synthesis (V4.1 Beta)
        #   2. Knowledge Graph  → entity-specific knowledge
        #   3. Personality Bank → creative/personal responses
        #   4. Context Recall   → reference to own prior statements

        emotion_str = current_emotion.value if hasattr(current_emotion, 'value') else str(current_emotion)
        player_trust = ml_context.get("trust", rel_result.get("trust", 50.0))
        lower_query = query.lower()
        multi_entity_query = bool(re.search(r"\b(and|versus|vs|plus|along with)\b", lower_query))

        # ── Pre-evaluate Pattern Match for Identity Protection ──
        matched_pattern, match_score = self._match_pattern(query)
        import logging
        logging.warning(f"DEBUG EARLY MATCH: query='{query}' score={match_score} pat={matched_pattern.get('id') if matched_pattern else None}")

        # Check if pattern is disabled by world state
        if matched_pattern:
            pat_id = matched_pattern.get("id", "")
            if pat_id in world_result.get("disabled_patterns", set()):
                matched_pattern = None
                match_score = 0.0
            elif pat_id in world_result.get("pattern_overrides", {}):
                matched_pattern = dict(matched_pattern)  # Copy
                matched_pattern["response_template"] = world_result["pattern_overrides"][pat_id]

        # Only run Knowledge Graph/Cloud if we don't have a very high confidence pattern match
        if not matched_pattern or match_score < 0.85:
            # Queries that clearly ask about more than one thing should avoid the
            # single-entity Knowledge Graph shortcut so the Knowledge Cloud synthesis path can handle conjunction-based prompts like 'dragons and healing potions'.
            if not multi_entity_query:
                # 1. Knowledge Graph
                kg_result = self.knowledge.lookup(
                    query=query,
                    player_trust=player_trust,
                    emotion=emotion_str,
                )
                if kg_result:
                    response = kg_result["response"]
                    self.tracker.record_npc_response(player_id, response)
                    self.recall.record_response(player_id, response)
                    self._local_handled += 1
                    self._knowledge_handled += 1
                    return self._build_result(
                        response=response,
                        source="knowledge_graph",
                        confidence=kg_result["confidence"],
                        emotion=current_emotion,
                        rel_result=rel_result,
                        conv_context=conv_context,
                        world_result=world_result,
                        match_score=kg_result["confidence"],
                        pattern_id=f"kg_{kg_result['entity_id']}",
                        start_time=start_time,
                        actions_taken=actions_taken,
                        kal_context=kal_context,
                    )

            # 2. Knowledge Cloud (shared world knowledge)
            if self.knowledge_cloud:
                cloud_results = self.knowledge_cloud.lookup_multi(
                    query=query,
                    emotion=emotion_str,
                    trust=player_trust,
                    top_k=4,  # Multi-entity reasoning limit
                )
                if cloud_results:
                    # Query-Focused Retrieval: Boost results that match query keywords
                    for res in cloud_results:
                        match_targets = {res.get("entity_id", ""), res.get("entity_name", "").lower()}
                        match_targets.update([a.lower() for a in res.get("aliases", [])])
                        if any(t in query.lower() for t in match_targets if len(t) > 3):
                            res["confidence"] = min(res.get("confidence", 0.5) * 2.0, 1.0)

                    # Sort by pinned confidence (Descending)
                    cloud_results.sort(key=lambda x: x.get("confidence", 0), reverse=True)

                    # Phase 10: Multi-Entity Synthesis
                    response = await self._synthesize_knowledge_response(
                        cloud_results,
                        query,
                        player_id,
                        ml_context=ml_context,
                        world_state=world_result.get("world_state", {})
                    )

                    self.tracker.record_npc_response(player_id, response)
                    self.recall.record_response(player_id, response)
                    self._local_handled += 1
                    self._cloud_handled += 1

                    # Phase 11: Agentic Intent Mapping
                    # If player intent matches a knowledge-defined action, trigger it
                    detected_intent = ml_context.get("intent")
                    if detected_intent:
                        for res in cloud_results:
                            agentic = res.get("agentic_actions", {})
                            if detected_intent in agentic:
                                for action_cmd in agentic[detected_intent]:
                                    if action_cmd not in [a.get("action") for a in actions_taken]:
                                        actions_taken.append({
                                            "description": f"Triggered action '{action_cmd}' via {res['entity_name']} (Intent: {detected_intent})",
                                            "type": "agentic_knowledge",
                                            "action": action_cmd,
                                            "entity": res["entity_id"]
                                        })

                    confidence = sum(r["confidence"] for r in cloud_results) / len(cloud_results)

                    return self._build_result(
                        response=response,
                        source="knowledge_cloud",
                        confidence=confidence,
                        emotion=current_emotion,
                        rel_result=rel_result,
                        conv_context=conv_context,
                        world_result=world_result,
                        match_score=confidence,
                        pattern_id=f"cloud_{cloud_results[0]['entity_id']}",
                        start_time=start_time,
                        actions_taken=actions_taken,
                    )

        # ── Step 5: Pattern Matching (Legacy Template Matching) ──
        # Uses local character patterns + semantic similarity (already pre-evaluated above)

        # ── Step 6: Escalation Gate ──
        escalation = self.gate.evaluate(
            match_confidence=match_score,
            keywords=keywords,
            conversation_depth=conv_context.get("conversation_depth", 0),
            emotion_intensity=emotion_result["intensity"],
            query_text=query,
        )

        # Boost escalation if ML Swarm detected high escalation risk
        ml_escalation_risk = ml_context.get("escalation_risk", 0)
        if ml_escalation_risk > 0.5:
            escalation.total_score = min(escalation.total_score + ml_escalation_risk * 0.3, 1.0)

        # ── Decision: Local or Escalate? ──
        if matched_pattern and match_score >= 0.55:
            # Local handling via cognitive engine
            # Merge all context for the compositor
            full_context = {
                **conv_context,
                "emotion": current_emotion,
                **rel_result,
                "world_state": world_result.get("world_state", {}),
            }

            composed_surface = self.compositor.compose_labeled(
                pattern=matched_pattern,
                context=full_context,
                emotion=current_emotion,
                player_id=player_id,
            )
            response = composed_surface.text

            self.tracker.record_npc_response(player_id, response)
            self.recall.record_response(player_id, response)  # Feed Module 9
            self._local_handled += 1

            return self._build_result(
                response=response,
                source="cognitive_engine",
                confidence=match_score,
                emotion=current_emotion,
                rel_result=rel_result,
                escalation=None,
                conv_context=conv_context,
                world_result=world_result,
                match_score=match_score,
                pattern_id=matched_pattern.get("id", "unknown"),
                start_time=start_time,
                ml_context=ml_context,
                debug_extra={"template_surface": composed_surface.to_debug_dict()},
                actions_taken=actions_taken,
                kal_context=kal_context,
            )

        elif escalation.should_escalate and thinking_layer_available:
            # Escalate to thinking layer
            self._escalated += 1
            return self._build_result(
                response=None,  # Caller must fill via deeper processing
                source="escalated",
                confidence=match_score,
                emotion=current_emotion,
                rel_result=rel_result,
                escalation={
                    "should_escalate": True,
                    "score": escalation.total_score,
                    "signals": [
                        {"name": s.name, "weight": s.weight, "score": s.score, "reason": s.reason}
                        for s in escalation.signals
                    ],
                },
                conv_context=conv_context,
                world_result=world_result,
                match_score=match_score,
                pattern_id=None,
                start_time=start_time,
                actions_taken=actions_taken,
                kal_context=kal_context,
            )

        else:
            # ── NEW: 4-Module Fallback Cascade ──
            # Before stalling, try the 4 brain modules in order:
            #   1. Knowledge Graph  → entity-specific knowledge
            #   2. Personality Bank → creative/personal responses
            #   3. Context Recall   → reference to own prior statements

            emotion_str = current_emotion.value if hasattr(current_emotion, 'value') else str(current_emotion)
            player_trust = rel_result.get("trust", 50.0)

            # V4: If KAL returned context, try using it as a knowledge source (Direct Match)
            if kal_context and kal_context.get("results"):
                module_result = await self.patterns_gen.generate_response(
                    query=query,
                    kal_context=kal_context,
                    character_id=self.character_id
                )
                if module_result:
                    response = module_result["response"]
                    self.tracker.record_npc_response(player_id, response)
                    self.recall.record_response(player_id, response)
                    self._local_handled += 1
                    self._generative_handled += 1
                    return self._build_result(
                        response=response,
                        source="pattern_engine",
                        confidence=module_result["confidence"],
                        emotion=current_emotion,
                        rel_result=rel_result,
                        conv_context=conv_context,
                        world_result=world_result,
                        match_score=module_result["confidence"],
                        pattern_id=f"gen_{self.character_id}",
                        start_time=start_time,
                        actions_taken=actions_taken,
                        kal_context=kal_context,
                    )

            # 1. Knowledge Graph
            kg_result = self.knowledge.lookup(
                query=query,
                player_trust=player_trust,
                emotion=emotion_str,
            )
            if kg_result:
                response = kg_result["response"]
                self.tracker.record_npc_response(player_id, response)
                self.recall.record_response(player_id, response)
                self._local_handled += 1
                self._knowledge_handled += 1
                return self._build_result(
                    response=response,
                    source="knowledge_graph",
                    confidence=kg_result["confidence"],
                    emotion=current_emotion,
                    rel_result=rel_result,
                    conv_context=conv_context,
                    world_result=world_result,
                    match_score=kg_result["confidence"],
                    pattern_id=f"kg_{kg_result['entity_id']}",
                    start_time=start_time,
                    actions_taken=actions_taken,
                    kal_context=kal_context,
                )

            # 2. Personality Bank
            pb_result = self.personality.get_response(
                query=query,
                keywords=set(keywords) if isinstance(keywords, list) else keywords,
                emotion=emotion_str,
            )
            if pb_result:
                response = pb_result["response"]
                self.tracker.record_npc_response(player_id, response)
                self.recall.record_response(player_id, response)
                self._local_handled += 1
                self._personality_handled += 1
                return self._build_result(
                    response=response,
                    source="personality_bank",
                    confidence=pb_result["confidence"],
                    emotion=current_emotion,
                    rel_result=rel_result,
                    conv_context=conv_context,
                    world_result=world_result,
                    match_score=pb_result["confidence"],
                    pattern_id=f"pb_{pb_result['intent']}",
                    start_time=start_time,
                    actions_taken=actions_taken,
                    kal_context=kal_context,
                )

            # 3. Context Recall
            cr_result = self.recall.process(
                player_id=player_id,
                query=query,
                emotion=emotion_str,
            )
            if cr_result and cr_result.get("recall_type") != "not_found":
                response = cr_result["response"]
                self.tracker.record_npc_response(player_id, response)
                self._local_handled += 1
                self._recall_handled += 1
                return self._build_result(
                    response=response,
                    source="context_recall",
                    confidence=cr_result["confidence"],
                    emotion=current_emotion,
                    rel_result=rel_result,
                    conv_context=conv_context,
                    world_result=world_result,
                    match_score=cr_result["confidence"],
                    pattern_id=f"cr_{cr_result['recall_type']}",
                    start_time=start_time,
                    actions_taken=actions_taken,
                    kal_context=kal_context,
                )

            # 4. Pattern Engine (Generative Phase)
            # Fulfills user request: "generate language by predicting the next word"
            if kal_context and kal_context.get("results"):
                module_result = await self.patterns_gen.generate_response(
                    query=query,
                    kal_context=kal_context,
                    character_id=self.character_id
                )
                if module_result:
                    response = module_result["response"]
                    self.tracker.record_npc_response(player_id, response)
                    self.recall.record_response(player_id, response)
                    self._local_handled += 1
                    self._generative_handled += 1
                    return self._build_result(
                        response=response,
                        source="pattern_engine",
                        confidence=module_result["confidence"],
                        emotion=current_emotion,
                        rel_result=rel_result,
                        conv_context=conv_context,
                        world_result=world_result,
                        match_score=module_result["confidence"],
                        pattern_id=f"gen_{self.character_id}",
                        start_time=start_time,
                        actions_taken=actions_taken,
                        kal_context=kal_context,
                    )

            # ── All 4 modules missed → Original fallback ──
            if escalation.should_escalate:
                # Use stall response
                response = escalation.fallback_response or self._fallback_text
            else:
                response = self._fallback_text

            self.tracker.record_npc_response(player_id, response)
            self.recall.record_response(player_id, response)
            self._local_handled += 1

            return self._build_result(
                response=response,
                source="fallback",
                confidence=0.3,
                emotion=current_emotion,
                rel_result=rel_result,
                escalation={
                    "should_escalate": escalation.should_escalate,
                    "score": escalation.total_score,
                    "thinking_layer_available": thinking_layer_available,
                },
                conv_context=conv_context,
                world_result=world_result,
                match_score=match_score,
                pattern_id=None,
                start_time=start_time,
                context=context,  # Pass context for goal evaluation
                ml_context=ml_context,
                actions_taken=actions_taken,
                kal_context=kal_context,
            )

    def record_witness_event(
        self,
        entity_id: str,
        fact: str,
        depth: str = "acquainted",
        trust_threshold: float = 0.0
    ):
        """
        Record a witnessed event into the shared Knowledge Cloud (Phase 12).
        Allows NPCs to 'evolve' the world lore based on observations.
        """
        if not self.knowledge_cloud:
            return

        # Get existing or create new
        from core.knowledge_cloud import KnowledgeEntry

        target_entry = None
        if entity_id in self.knowledge_cloud._entries:
            target_entry = self.knowledge_cloud._entries[entity_id]
            if fact not in target_entry.facts:
                target_entry.facts.append(fact)
        else:
            # Create a basic new entry for this newly discovered entity
            target_entry = KnowledgeEntry(
                entity_id=entity_id,
                entity=entity_id.replace("_", " ").title(),
                entity_type="event",
                facts=[fact],
                depth=depth,
                trust_threshold=trust_threshold,
                description=f"A recorded event concerning {entity_id}."
            )

        self.knowledge_cloud.upsert_entry(target_entry)
        if self._memory_store is not None:
            try:
                self._memory_store.store_semantic(
                    character_id=self.character_id,
                    content=f"Witnessed {target_entry.entity_id}: {fact}",
                    importance=0.6,
                    tags=["knowledge_cloud", "witness"],
                )
            except Exception:
                pass

    def get_stats(self) -> Dict[str, Any]:
        """Return engine statistics."""
        stats = {
            "character_id": self.character_id,
            "total_queries": self._total_queries,
            "local_handled": self._local_handled,
            "escalated": self._escalated,
            "knowledge_handled": self._knowledge_handled,
            "personality_handled": self._personality_handled,
            "recall_handled": self._recall_handled,
            "semantic_wins": self._semantic_wins,
            "kal_handled": self._kal_handled,
            "generative_handled": self._generative_handled,
            "cloud_handled": self._cloud_handled,
            "local_pct": (
                round(self._local_handled / self._total_queries * 100, 1)
                if self._total_queries > 0 else 0
            ),
        }
        # Include semantic matcher stats
        if hasattr(self, 'semantic'):
            stats["semantic_matcher"] = self.semantic.get_stats()

        stats["goal_stack"] = self.goal_stack.get_stats()
        stats["proactive_engine"] = self.proactive_engine.get_stats()

        return stats

    @classmethod
    def from_character_dir(cls, char_dir: str, persist_dir: Optional[str] = None) -> "CognitiveEngine":
        """Load a CognitiveEngine from a character directory.

        Looks for:
          - bio.json (required)
          - patterns.json (optional)
          - knowledge.json (optional, loaded by _load_knowledge)
          - personality.json (optional, loaded by PersonalityBank)
        """
        char_path = Path(char_dir)
        bio_path = char_path / "bio.json"
        pat_path = char_path / "patterns.json"

        with open(bio_path) as f:
            bio = json.load(f)
        patterns = {}
        if pat_path.exists():
            with open(pat_path) as f:
                patterns = json.load(f)

        char_id = bio.get("id", bio.get("character_id", char_path.name))

        engine = cls(
            character_id=char_id,
            bio=bio,
            patterns=patterns,
            persist_dir=persist_dir,
            char_dir=str(char_path),
        )

        # Load agentic profiles
        if "goals" in bio:
            engine.goal_stack.load_from_config(bio["goals"])
        if "proactive_triggers" in bio:
            engine.proactive_engine.load_from_config(bio["proactive_triggers"])
        else:
            engine.proactive_engine.add_default_triggers()

        return engine
