#!/usr/bin/env python3
"""
SequenceLinker — Pattern Chaining for Knowledge Cloud Responses
AIVM Synthesus 2.0 — MVP for Hypothesis: "Retrieval + Chaining + Slot Filling ≈ Generation"

GOAL (locked):
  Prove that compositional Lego-building on retrieved patterns can match
  smooth interpolation on 175B weights IF the pattern space is dense enough
  and the routing is precise.

WHAT THIS MODULE DOES:
  Takes top-N knowledge cloud results and chains them into a coherent
  multi-sentence response using lightweight transition scoring.

ARCHITECTURE:
  Input:  List[KnowledgeResult] from KnowledgeCloud.lookup_multi()
  Output: ChainPlan = ordered list of pattern references (1-4 steps)

  Scoring function (log-linear, no LSTM for MVP):
    score(chain) = Σ [
      w1 * retrieval_confidence +
      w2 * transition_p(pattern_i → pattern_i+1, context_bucket) +
      w3 * slot_fillability(pattern_i+1, current_bindings) +
      w4 * novelty_penalty(repetition avoidance)
    ]

STOP CONDITIONS (hard rules):
  - max_sentences: 4 (configurable)
  - min_confidence: 0.3 (drop below this → stop)
  - slot_failure: required slots cannot be filled → reject pattern
  - repetition: same entity mentioned twice in chain → penalize

TRANSITION STORE:
  Source: data/knowledge_cloud/transitions.json (hand-curated for MVP)
  Format: {"from_id": {"to_id": {"weight": 0.8, "context_buckets": ["combat", "lore"]}}}
  Fallback: uniform distribution if no edge exists

EXTENDING THIS MODULE:
  1. To add new transitions: edit transitions.json
  2. To add context buckets: extend the 7-signal → bucket mapping
  3. To swap in LSTM: replace _score_transition() with neural predictor
  4. To add learned edges: train on dialogue logs, write to transitions.json

INTEGRATION POINT:
  Called from CognitiveEngine._synthesize_knowledge_response() AFTER
  KnowledgeCloud returns results, BEFORE SlotFiller binds variables.

AUTHOR: Cascade
DATE: 2026-04-02
VERSION: MVP-1.0 (deterministic transitions, no training required)
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import re

logger = logging.getLogger(__name__)

# ── Data Classes ──────────────────────────────────────────────────────────

@dataclass
class ChainStep:
    """A single step in a pattern chain."""
    pattern_id: str
    pattern_text: str
    confidence: float
    slots_required: List[str] = field(default_factory=list)
    slots_optional: List[str] = field(default_factory=list)

@dataclass
class ChainPlan:
    """A complete chain of patterns to render."""
    steps: List[ChainStep]
    total_confidence: float
    context_bucket: str
    stop_reason: str  # "max_length", "confidence_drop", "slot_failure", "complete"

# ── SequenceLinker Class ──────────────────────────────────────────────────

class SequenceLinker:
    """
    Chains knowledge cloud patterns into multi-sentence responses.

    Usage:
        linker = SequenceLinker(transitions_path="data/transitions.json")
        plan = linker.build_chain(
            knowledge_results=cloud_results,
            context_vector={"intent": "ask_about", "emotion": "curious", ...},
            world_state={"entities": ["dragon", "castle"], ...}
        )
        # plan.steps = [step1, step2, step3] ordered for rendering
    """

    # Context signal → bucket mapping (7 Swarm signals → discrete buckets)
    CONTEXT_BUCKETS = {
        # Intent buckets
        "ask_about": "inquiry",
        "greet": "social",
        "threaten": "combat",
        "trade": "commerce",
        "quest": "narrative",
        # Emotion buckets
        "angry": "tense",
        "afraid": "tense",
        "happy": "social",
        "neutral": "general",
        "sad": "empathy",
        # Default
        "_default": "general"
    }

    def __init__(
        self,
        transitions_path: Optional[str] = None,
        max_chain_length: int = 4,
        min_step_confidence: float = 0.05,
        w_retrieval: float = 0.3,
        w_transition: float = 0.3,
        w_slot_compat: float = 0.3,
        w_novelty: float = 0.1,
    ):
        """
        Initialize SequenceLinker.

        Args:
            transitions_path: Path to transitions.json (None = empty)
            max_chain_length: Maximum patterns in a chain (default 4)
            min_step_confidence: Stop if step confidence below this
            w_retrieval: Weight for original retrieval confidence
            w_transition: Weight for transition probability
            w_slot_compat: Weight for slot fillability
            w_novelty: Weight for repetition penalty
        """
        self.max_chain_length = max_chain_length
        self.min_step_confidence = min_step_confidence
        self.w_retrieval = w_retrieval
        self.w_transition = w_transition
        self.w_slot_compat = w_slot_compat
        self.w_novelty = w_novelty

        # Load transitions
        self._transitions: Dict[str, Dict[str, Dict[str, Any]]] = {}
        if transitions_path and Path(transitions_path).exists():
            self._load_transitions(transitions_path)
        else:
            logger.info("SequenceLinker: No transitions file, using uniform fallback")

    def _load_transitions(self, path: str) -> None:
        """Load transition graph from JSON."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._transitions = data.get("transitions", {})
            logger.info(f"SequenceLinker: Loaded {len(self._transitions)} transition sources")
        except Exception as e:
            logger.warning(f"SequenceLinker: Failed to load transitions: {e}")
            self._transitions = {}

    def _get_context_bucket(self, context_vector: Dict[str, Any]) -> str:
        """Map 7-signal context vector to discrete bucket."""
        # Priority: intent > emotion > default
        intent = context_vector.get("intent", "")
        emotion = context_vector.get("emotion", "")

        if intent in self.CONTEXT_BUCKETS:
            return self.CONTEXT_BUCKETS[intent]
        if emotion in self.CONTEXT_BUCKETS:
            return self.CONTEXT_BUCKETS[emotion]

        return self.CONTEXT_BUCKETS["_default"]

    def _score_transition(
        self,
        from_id: str,
        to_id: str,
        context_bucket: str,
    ) -> float:
        """
        Score transition from_id → to_id in given context.

        MVP: Table lookup with bucket filtering.
        Future: Neural predictor (micro-LSTM) trained on dialogue logs.
        """
        if from_id not in self._transitions:
            # No outgoing edges → uniform fallback (exploration)
            return 0.5

        edges = self._transitions[from_id]
        if to_id not in edges:
            # No specific edge → slight penalty
            return 0.3

        edge = edges[to_id]
        base_weight = edge.get("weight", 0.5)

        # Context bucket boost
        buckets = edge.get("context_buckets", [])
        if context_bucket in buckets:
            base_weight *= 1.2  # 20% boost for context match

        return min(base_weight, 1.0)

    def _score_slot_compat(
        self,
        pattern_slots: List[str],
        fillable_slots: Set[str],
    ) -> float:
        """
        Score how well pattern slots can be filled from current context.

        Required slots must ALL be fillable → binary gate
        Optional slots contribute partial credit
        """
        if not pattern_slots:
            return 1.0  # No slots needed = perfect compatibility

        required = [s for s in pattern_slots if not s.startswith("?")]
        optional = [s for s in pattern_slots if s.startswith("?")]

        has_any_entities = any(s in fillable_slots for s in ["entity", "subject", "target"]) or len(fillable_slots) > 0

        for slot in required:
            slot_name = slot.strip("[]").lower()
            if slot_name in ["entity", "subject", "target"]:
                if has_any_entities:
                    continue
                return 0.0
            if slot_name in ["time", "topic", "emotion"]:
                continue
            if slot_name not in fillable_slots:
                return 0.0

        optional_filled = 0
        for s in optional:
            slot_name = s.strip("?[]").lower()
            if slot_name in ["entity", "subject", "target", "time", "emotion"] or slot_name in fillable_slots:
                optional_filled += 1

        optional_score = optional_filled / max(len(optional), 1)

        return 0.8 + (0.2 * optional_score)

    def _score_novelty(
        self,
        candidate_id: str,
        used_ids: Set[str],
        mentioned_entities: Set[str],
    ) -> float:
        """Penalty for repetition."""
        if candidate_id in used_ids:
            return 0.5  # Already used this pattern

        # Check entity overlap (extract entity from pattern_id like "kg_dragon")
        entity = candidate_id.split("_")[-1] if "_" in candidate_id else candidate_id
        if entity in mentioned_entities:
            return 0.7  # Same entity mentioned before

        return 1.0  # Novel

    def _query_terms(self, text: str) -> Set[str]:
        terms = set(re.findall(r"[a-z]+", text.lower()))
        stop_words = {
            "the", "a", "an", "and", "or", "to", "of", "in", "on", "at", "for", "with", "by",
            "is", "are", "was", "were", "be", "do", "does", "did", "what", "where", "when",
            "who", "how", "why", "tell", "me", "about", "this", "that", "these", "those", "they",
            "it", "its", "their", "there", "here", "from", "as", "into", "than", "then",
        }
        return {term for term in terms if term not in stop_words}

    def _result_terms(self, result: Dict[str, Any]) -> Set[str]:
        parts = [
            result.get("entity_id", ""),
            result.get("entity_name", ""),
            result.get("response", ""),
            " ".join(result.get("facts", [])),
            " ".join(result.get("aliases", [])),
            " ".join(result.get("tags", [])),
            " ".join(f"{k} {v}" for k, v in result.get("related", {}).items()),
        ]
        terms = set()
        for part in parts:
            terms.update(self._query_terms(part))
        return terms

    def build_chain(
        self,
        knowledge_results: List[Dict[str, Any]],
        context_vector: Dict[str, Any],
        world_state: Optional[Dict[str, Any]] = None,
        dialogue_memory: Optional[List[Dict[str, Any]]] = None,
        query: str = "",
    ) -> ChainPlan:
        """
        Build a chain of patterns from knowledge results.

        Args:
            knowledge_results: Output from KnowledgeCloud.lookup_multi()
            context_vector: 7 Swarm signals (intent, emotion, etc.)
            world_state: Available entities for slot filling
            dialogue_memory: Recent conversation turns for context
            query: Original query text when available; used to suppress filler chaining

        Returns:
            ChainPlan with ordered steps and metadata
        """
        if not knowledge_results:
            return ChainPlan(steps=[], total_confidence=0.0, context_bucket="none", stop_reason="no_results")

        # Determine context bucket
        context_bucket = self._get_context_bucket(context_vector)
        query_terms = self._query_terms(query) if query else set()

        # Extract fillable slots from world state
        fillable_slots: Set[str] = set()
        if world_state:
            fillable_slots.update(world_state.get("entities", []))
            fillable_slots.update(world_state.get("locations", []))
            fillable_slots.update(world_state.get("items", []))

        # Add context-derived slots
        fillable_slots.add(context_vector.get("emotion", "neutral"))
        fillable_slots.add(context_vector.get("intent", "unknown"))

        # Initialize chain with best result
        chain: List[ChainStep] = []
        used_ids: Set[str] = set()
        mentioned_entities: Set[str] = set()
        covered_query_terms: Set[str] = set()
        total_confidence = 0.0

        # Sort candidates by retrieval confidence
        sorted_results = sorted(
            knowledge_results,
            key=lambda r: r.get("confidence", 0),
            reverse=True
        )

        # First step: highest confidence result that passes slot check
        first_result = None
        for result in sorted_results:
            pattern_id = f"cloud_{result.get('entity_id', 'unknown')}"
            slots = result.get("slots", [])  # Patterns may declare slots

            compat = self._score_slot_compat(slots, fillable_slots)
            if compat == 0:
                continue  # Can't fill required slots

            first_result = result
            step = ChainStep(
                pattern_id=pattern_id,
                pattern_text=result.get("response", ""),
                confidence=result.get("confidence", 0.5) * compat,
                slots_required=[s for s in slots if not s.startswith("?")],
                slots_optional=[s for s in slots if s.startswith("?")],
            )
            chain.append(step)
            used_ids.add(pattern_id)
            entity_id = result.get("entity_id", "")
            mentioned_entities.add(entity_id)
            covered_query_terms.update(self._result_terms(result) & query_terms)
            total_confidence += step.confidence
            break

        if not first_result:
            return ChainPlan(steps=[], total_confidence=0.0, context_bucket=context_bucket, stop_reason="slot_failure")

        # Extend chain: greedy selection of next pattern
        while len(chain) < self.max_chain_length:
            best_next = None
            best_score = -1.0

            for result in sorted_results:
                # Unique Pattern ID Check
                pattern_id = f"cloud_{result.get('entity_id', 'unknown')}"
                if pattern_id in used_ids:
                    continue

                # Unique Entity Check
                entity_id = result.get('entity_id', '')
                if entity_id in mentioned_entities:
                    continue

                # Score components
                retrieval_conf = result.get("confidence", 0.5)
                slots = result.get("slots", [])
                slot_compat = self._score_slot_compat(slots, fillable_slots)

                if slot_compat == 0:
                    continue  # Can't fill required slots

                transition_p = self._score_transition(
                    chain[-1].pattern_id,
                    pattern_id,
                    context_bucket
                )
                novelty = self._score_novelty(
                    pattern_id,
                    used_ids,
                    mentioned_entities
                )

                candidate_terms = self._result_terms(result)
                new_query_terms = (candidate_terms & query_terms) - covered_query_terms if query_terms else set()
                if query_terms and len(chain) >= 2 and not new_query_terms:
                    continue

                # INTENT BOOST: Boost patterns that match the current intent bucket
                intent_boost = 1.0
                pattern_tags = result.get('tags', [])
                if context_bucket in pattern_tags or any(tag in context_bucket for tag in pattern_tags):
                    intent_boost = 1.3

                # Weighted sum
                score = (
                    self.w_retrieval * retrieval_conf * intent_boost +
                    self.w_transition * transition_p +
                    self.w_slot_compat * slot_compat +
                    self.w_novelty * novelty
                )

                if query_terms and new_query_terms:
                    score += min(len(new_query_terms), 3) * 0.08

                if score > best_score and score >= self.min_step_confidence:
                    best_score = score
                    best_next = (result, pattern_id, slots, score, new_query_terms)

            if not best_next:
                break  # No good candidate

            result, pattern_id, slots, step_conf, new_query_terms = best_next
            step = ChainStep(
                pattern_id=pattern_id,
                pattern_text=result.get("response", ""),
                confidence=step_conf,
                slots_required=[s for s in slots if not s.startswith("?")],
                slots_optional=[s for s in slots if s.startswith("?")],
            )
            chain.append(step)
            used_ids.add(pattern_id)
            entity_id = result.get("entity_id", "")
            mentioned_entities.add(entity_id)
            covered_query_terms.update(new_query_terms)
            total_confidence += step.confidence

        # Determine stop reason
        stop_reason = "complete"
        if len(chain) >= self.max_chain_length:
            stop_reason = "max_length"
        elif total_confidence / len(chain) < self.min_step_confidence:
            stop_reason = "confidence_drop"

        return ChainPlan(
            steps=chain,
            total_confidence=total_confidence / max(len(chain), 1),
            context_bucket=context_bucket,
            stop_reason=stop_reason
        )

    def _limit_sentences(self, text: str, max_sentences: int) -> str:
        """Return at most max_sentences sentences from text."""
        if max_sentences <= 0:
            return ""
        parts = re.split(r"(?<=[.!?])\s+", text.strip())
        kept = [part.strip() for part in parts if part.strip()][:max_sentences]
        return " ".join(kept)

    def render_chain_text(
        self,
        plan: ChainPlan,
        slot_bindings: Any,
        max_steps: int = 2,
        max_sentences_per_step: int = 1,
    ) -> str:
        """
        Render chain to text (SlotFiller fills bindings before this).

        Args:
            plan: ChainPlan from build_chain()
            slot_bindings: Either Dict[str, str] (Legacy) or List[Dict[str, str]] (Per-step)
            max_steps: Maximum number of chain steps to render
            max_sentences_per_step: Maximum number of sentences kept per step

        Returns:
            Concatenated, slot-filled response text
        """
        sentences = []
        seen_segments: Set[str] = set()

        for i, step in enumerate(plan.steps[:max_steps]):
            text = step.pattern_text

            # Use per-step bindings if available, otherwise fallback to global
            current_bindings = {}
            if isinstance(slot_bindings, list) and i < len(slot_bindings):
                current_bindings = slot_bindings[i]
            elif isinstance(slot_bindings, dict):
                current_bindings = slot_bindings

            # Fill slots in text
            for slot, value in current_bindings.items():
                text = text.replace(f"[{slot}]", value)
                text = text.replace(f"[?{slot}]", value)

            # Also try global fallback for common slots if not in current
            if isinstance(slot_bindings, list) and len(slot_bindings) > 0:
                # Merge with first step's bindings for common context (time, emotion)
                for slot, value in slot_bindings[0].items():
                    if slot not in current_bindings:
                        text = text.replace(f"[{slot}]", value)
                        text = text.replace(f"[?{slot}]", value)

            # Clean up unfilled optional slots
            text = re.sub(r"\[\?[^\]]+\]", "", text)  # Remove [?slot]
            text = re.sub(r"\[[^\]]+\]", "", text)     # Remove [slot]
            text = re.sub(r"\s+", " ", text).strip()
            text = self._limit_sentences(text, max_sentences_per_step)

            # Basic deduplication (sentence and snippet level)
            if not text:
                continue

            is_redundant = False
            text_norm = text.lower().strip()
            for seen in seen_segments:
                seen_norm = seen.lower().strip()
                # Block only if significantly long segment is a subset
                if len(text_norm) > 10 and (text_norm in seen_norm or seen_norm in text_norm):
                    is_redundant = True
                    break

            if not is_redundant:
                sentences.append(text)
                seen_segments.add(text)

        return " ".join(sentences)

# ── Utility Functions ──────────────────────────────────────────────────────

def create_mvp_transitions() -> Dict[str, Any]:
    """
    Create MVP transition table for testing.

    These are hand-curated edges that demonstrate chaining capability.
    Real deployment would have 1000s of edges extracted from dialogue logs.
    """
    return {
        "transitions": {
            # Greeting → follow-up patterns
            "cloud_greeting": {
                "cloud_dragon": {"weight": 0.7, "context_buckets": ["inquiry", "narrative"]},
                "cloud_quest": {"weight": 0.6, "context_buckets": ["narrative"]},
            },
            # Dragon → related entities
            "cloud_dragon": {
                "cloud_castle": {"weight": 0.8, "context_buckets": ["lore", "narrative"]},
                "cloud_treasure": {"weight": 0.7, "context_buckets": ["commerce", "lore"]},
                "cloud_fire_magic": {"weight": 0.6, "context_buckets": ["combat", "lore"]},
            },
            # Castle → related
            "cloud_castle": {
                "cloud_ruler": {"weight": 0.9, "context_buckets": ["lore", "social"]},
                "cloud_dungeon": {"weight": 0.7, "context_buckets": ["lore", "narrative"]},
            },
            # Quest patterns
            "cloud_quest": {
                "cloud_reward": {"weight": 0.8, "context_buckets": ["commerce", "narrative"]},
                "cloud_danger": {"weight": 0.7, "context_buckets": ["combat", "narrative"]},
            },
        },
        "metadata": {
            "version": "MVP-1.0",
            "description": "Hand-curated transitions for hypothesis testing",
            "created": "2026-04-02",
            "num_edges": 10,
        }
    }

# ── Module Test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Quick sanity test
    logging.basicConfig(level=logging.INFO)

    # Create test data
    test_results = [
        {"entity_id": "dragon", "response": "Dragons are ancient creatures of great power.", "confidence": 0.9, "slots": []},
        {"entity_id": "castle", "response": "The castle stands on the hill overlooking the valley.", "confidence": 0.8, "slots": []},
        {"entity_id": "ruler", "response": "The ruler governs with an iron fist.", "confidence": 0.7, "slots": ["[emotion]"]},
    ]

    context = {"intent": "ask_about", "emotion": "curious"}
    world = {"entities": ["dragon", "castle", "ruler"], "emotion": "curious"}

    # Build and print chain
    linker = SequenceLinker()
    plan = linker.build_chain(test_results, context, world)

    print(f"\nChain Plan:")
    print(f"  Context bucket: {plan.context_bucket}")
    print(f"  Stop reason: {plan.stop_reason}")
    print(f"  Avg confidence: {plan.total_confidence:.2f}")
    print(f"  Steps ({len(plan.steps)}):")
    for i, step in enumerate(plan.steps):
        print(f"    {i+1}. {step.pattern_id} (conf={step.confidence:.2f})")
        print(f"       Text: {step.pattern_text[:50]}...")

    # Render with dummy bindings
    bindings = {"emotion": "curious"}
    rendered = linker.render_chain_text(plan, bindings)
    print(f"\nRendered:\n  {rendered}")
