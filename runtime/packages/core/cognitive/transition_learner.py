#!/usr/bin/env python3
"""
TransitionLearner — Online learning of transition probabilities from player feedback.
AIVM Synthesus 2.0 — Adapts pattern chaining based on user interactions.

WHAT THIS MODULE DOES:
  Learns and updates transition probabilities in real-time based on player feedback.
  Tracks successful chains, failed fills, and user satisfaction to reinforce good transitions.
  Persists learned transitions to improve future chaining performance.

INTEGRATION POINTS:
  - SequenceLinker._score_transition() — Uses learned weights
  - CognitiveEngine — Records feedback after responses
  - DialogueMemory — Tracks conversation outcomes

LEARNING MECHANISM:
  - Positive reinforcement: Successful chains increase transition weights
  - Negative reinforcement: Failed chains decrease problematic transitions
  - Decay: Old transitions lose weight over time
  - Context awareness: Learns different weights for different emotions/intents

FEEDBACK SOURCES:
  - Chain success (all slots filled, no fallbacks)
  - Player satisfaction (from UI feedback, if available)
  - Dialogue continuation (follow-up queries reference previous entities)
  - Error rates (slot fill failures, chain timeouts)

AUTHOR: Cascade
DATE: 2026-04-06
VERSION: v1.0 - Online transition learning from player interactions
"""

from __future__ import annotations

import json
import time
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ── Data Classes ──────────────────────────────────────────────────────────

@dataclass
class TransitionFeedback:
    """Feedback for a specific transition in a chain."""
    from_entity: str
    to_entity: str
    context_bucket: str
    timestamp: str
    success_score: float  # 0.0 (failure) to 1.0 (perfect)
    weight_delta: float = 0.0  # How much to adjust the transition weight

@dataclass
class LearnedTransition:
    """Learned transition with statistics."""
    from_entity: str
    to_entity: str
    context_bucket: str
    base_weight: float = 0.5
    learned_weight: float = 0.0
    sample_count: int = 0
    success_rate: float = 0.0
    last_updated: str = ""
    decay_factor: float = 0.95  # Monthly decay

# ── TransitionLearner Class ──────────────────────────────────────────────

class TransitionLearner:
    """
    Learns transition probabilities from player feedback and dialogue outcomes.

    Usage:
        learner = TransitionLearner("data/knowledge_cloud/learned_transitions.json")
        learner.record_feedback(chain_plan, success_score=0.8, player_emotion="curious")
        learner.update_transitions()
    """

    def __init__(self, transitions_path: str = "data/knowledge_cloud/learned_transitions.json"):
        """Initialize learner with persistent storage."""
        self.transitions_path = Path(transitions_path)
        self.transitions_path.parent.mkdir(parents=True, exist_ok=True)

        # In-memory transition database
        self.learned_transitions: Dict[str, LearnedTransition] = {}
        self.feedback_queue: List[TransitionFeedback] = []

        # Learning parameters
        self.learning_rate = 0.1
        self.decay_rate = 0.95  # Monthly decay
        self.min_samples = 3  # Minimum samples before using learned weights
        self.max_feedback_queue = 100  # Max queued feedback before processing

        # Load existing learned transitions
        self._load_transitions()

    def record_feedback(
        self,
        chain_plan: Any,  # ChainPlan from SequenceLinker
        success_score: float,
        player_emotion: str = "neutral",
        context_vector: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Record feedback for transitions used in a chain.

        Args:
            chain_plan: ChainPlan that was executed
            success_score: 0.0-1.0 rating of how well the chain worked
            player_emotion: Player's emotional state
            context_vector: Additional context (intent, etc.)
        """
        context_vector = context_vector or {}

        # Determine context bucket
        context_bucket = self._get_context_bucket(context_vector, player_emotion)

        # Extract transitions from chain
        if hasattr(chain_plan, 'steps') and len(chain_plan.steps) > 1:
            for i in range(len(chain_plan.steps) - 1):
                from_step = chain_plan.steps[i]
                to_step = chain_plan.steps[i + 1]

                feedback = TransitionFeedback(
                    from_entity=from_step.pattern_id,
                    to_entity=to_step.pattern_id,
                    context_bucket=context_bucket,
                    timestamp=datetime.now().isoformat(),
                    success_score=success_score,
                    weight_delta=self._calculate_weight_delta(success_score)
                )

                self.feedback_queue.append(feedback)

        # Process feedback if queue is full
        if len(self.feedback_queue) >= self.max_feedback_queue:
            self.update_transitions()

    def record_dialogue_feedback(
        self,
        conversation_id: str,
        dialogue_memory: Any,  # DialogueMemory instance
        player_feedback: Optional[float] = None
    ) -> None:
        """
        Record feedback from dialogue outcomes and player satisfaction.

        Args:
            conversation_id: Player conversation ID
            dialogue_memory: DialogueMemory instance with conversation history
            player_feedback: Optional explicit player rating (0.0-1.0)
        """
        try:
            # Get recent conversation turns
            recent_turns = dialogue_memory.get_recent_turns(
                dialogue_memory.load_context(conversation_id),
                limit=5
            )

            if len(recent_turns) < 2:
                return  # Not enough turns to learn from

            # Calculate dialogue coherence score
            coherence_score = self._calculate_dialogue_coherence(recent_turns)

            # Use player feedback if available, otherwise coherence score
            success_score = player_feedback if player_feedback is not None else coherence_score

            # Extract entity transitions from dialogue
            entities_mentioned = set()
            for turn in recent_turns:
                entities_mentioned.update(turn.get("entities", []))

            entities_list = list(entities_mentioned)
            if len(entities_list) >= 2:
                # Create feedback for entity transitions
                for i in range(len(entities_list) - 1):
                    feedback = TransitionFeedback(
                        from_entity=f"cloud_{entities_list[i]}",
                        to_entity=f"cloud_{entities_list[i+1]}",
                        context_bucket="general",  # Could be more sophisticated
                        timestamp=datetime.now().isoformat(),
                        success_score=success_score,
                        weight_delta=self._calculate_weight_delta(success_score)
                    )
                    self.feedback_queue.append(feedback)

        except Exception as e:
            logger.warning(f"Failed to record dialogue feedback: {e}")

    def update_transitions(self) -> None:
        """
        Process queued feedback and update learned transition weights.
        """
        if not self.feedback_queue:
            return

        logger.info(f"Processing {len(self.feedback_queue)} feedback items...")

        # Group feedback by transition
        transition_feedback: Dict[str, List[TransitionFeedback]] = {}

        for feedback in self.feedback_queue:
            key = f"{feedback.from_entity}→{feedback.to_entity}@{feedback.context_bucket}"
            if key not in transition_feedback:
                transition_feedback[key] = []
            transition_feedback[key].append(feedback)

        # Update transitions
        for transition_key, feedbacks in transition_feedback.items():
            from_entity, to_entity, context_bucket = self._parse_transition_key(transition_key)

            # Get or create learned transition
            trans_key = f"{from_entity}→{to_entity}@{context_bucket}"
            if trans_key not in self.learned_transitions:
                self.learned_transitions[trans_key] = LearnedTransition(
                    from_entity=from_entity,
                    to_entity=to_entity,
                    context_bucket=context_bucket,
                    base_weight=0.5,
                    learned_weight=0.0,
                    sample_count=0,
                    success_rate=0.0,
                    last_updated=datetime.now().isoformat()
                )

            transition = self.learned_transitions[trans_key]

            # Apply learning updates
            total_delta = sum(f.weight_delta for f in feedbacks)
            avg_success = sum(f.success_score for f in feedbacks) / len(feedbacks)

            # Update learned weight using learning rate
            transition.learned_weight += self.learning_rate * total_delta
            transition.sample_count += len(feedbacks)
            transition.success_rate = (transition.success_rate * (transition.sample_count - len(feedbacks)) +
                                     avg_success * len(feedbacks)) / transition.sample_count
            transition.last_updated = datetime.now().isoformat()

            # Apply decay to old transitions
            self._apply_decay(transition)

        # Clear processed feedback
        self.feedback_queue.clear()

        # Save updated transitions
        self._save_transitions()

        logger.info(f"Updated {len(transition_feedback)} transitions")

    def get_learned_weight(self, from_entity: str, to_entity: str, context_bucket: str) -> float:
        """
        Get the learned transition weight, or base weight if not learned.

        Returns:
            Learned weight if enough samples, otherwise base weight
        """
        trans_key = f"{from_entity}→{to_entity}@{context_bucket}"
        transition = self.learned_transitions.get(trans_key)

        if transition and transition.sample_count >= self.min_samples:
            # Combine base weight with learned adjustment
            combined_weight = transition.base_weight + transition.learned_weight
            # Clamp to reasonable range
            return max(0.1, min(1.0, combined_weight))
        else:
            return 0.5  # Neutral fallback

    def get_transition_stats(self) -> Dict[str, Any]:
        """Get statistics about learned transitions."""
        total_transitions = len(self.learned_transitions)
        well_learned = sum(1 for t in self.learned_transitions.values()
                          if t.sample_count >= self.min_samples)

        avg_success_rate = (sum(t.success_rate for t in self.learned_transitions.values())
                           / total_transitions) if total_transitions > 0 else 0.0

        return {
            "total_learned_transitions": total_transitions,
            "well_learned_transitions": well_learned,
            "average_success_rate": round(avg_success_rate, 3),
            "queued_feedback": len(self.feedback_queue),
            "learning_rate": self.learning_rate,
            "decay_rate": self.decay_rate
        }

    def _get_context_bucket(self, context_vector: Dict[str, Any], player_emotion: str) -> str:
        """Determine context bucket from context and emotion."""
        # Simple mapping - could be more sophisticated
        intent = context_vector.get("intent", "")
        emotion = player_emotion.lower()

        if intent == "combat":
            return "combat"
        elif intent in ["trade", "shop_buy", "shop_sell"]:
            return "commerce"
        elif intent in ["ask_lore", "ask_about"]:
            return "lore"
        elif emotion in ["afraid", "angry"]:
            return "tense"
        elif emotion in ["happy", "excited"]:
            return "social"
        else:
            return "general"

    def _calculate_weight_delta(self, success_score: float) -> float:
        """Calculate weight adjustment based on success score."""
        # Positive reinforcement for success, negative for failure
        if success_score > 0.7:
            return 0.1  # Reward good transitions
        elif success_score < 0.3:
            return -0.1  # Penalize bad transitions
        else:
            return 0.0  # Neutral

    def _calculate_dialogue_coherence(self, turns: List[Dict[str, Any]]) -> float:
        """Calculate coherence score from dialogue turns."""
        if len(turns) < 2:
            return 0.5

        coherence_score = 0.0
        total_comparisons = 0

        for i in range(len(turns) - 1):
            current_turn = turns[i]
            next_turn = turns[i + 1]

            # Check entity continuity
            current_entities = set(current_turn.get("entities", []))
            next_entities = set(next_turn.get("entities", []))

            if current_entities & next_entities:  # Shared entities
                coherence_score += 0.3
            elif next_entities:  # Some entities in next turn
                coherence_score += 0.1

            # Check slot consistency
            current_slots = set(current_turn.get("slots", {}).keys())
            next_slots = set(next_turn.get("slots", {}).keys())

            if current_slots & next_slots:  # Shared slot types
                coherence_score += 0.2

            total_comparisons += 1

        return coherence_score / total_comparisons if total_comparisons > 0 else 0.5

    def _parse_transition_key(self, key: str) -> Tuple[str, str, str]:
        """Parse transition key into components."""
        parts = key.split("@")
        entities = parts[0].split("→")
        context_bucket = parts[1] if len(parts) > 1 else "general"
        return entities[0], entities[1], context_bucket

    def _apply_decay(self, transition: LearnedTransition) -> None:
        """Apply time-based decay to learned weights."""
        if not transition.last_updated:
            return

        last_update = datetime.fromisoformat(transition.last_updated)
        days_since_update = (datetime.now() - last_update).days

        if days_since_update > 30:  # Decay monthly
            months_passed = days_since_update / 30.0
            decay_factor = self.decay_rate ** months_passed
            transition.learned_weight *= decay_factor

    def _load_transitions(self) -> None:
        """Load learned transitions from disk."""
        if not self.transitions_path.exists():
            return

        try:
            with open(self.transitions_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.learned_transitions = {}
            for key, trans_data in data.get("learned_transitions", {}).items():
                self.learned_transitions[key] = LearnedTransition(**trans_data)

            logger.info(f"Loaded {len(self.learned_transitions)} learned transitions")

        except Exception as e:
            logger.error(f"Failed to load learned transitions: {e}")
            self.learned_transitions = {}

    def _save_transitions(self) -> None:
        """Save learned transitions to disk."""
        data = {
            "learned_transitions": {
                key: {
                    "from_entity": t.from_entity,
                    "to_entity": t.to_entity,
                    "context_bucket": t.context_bucket,
                    "base_weight": t.base_weight,
                    "learned_weight": t.learned_weight,
                    "sample_count": t.sample_count,
                    "success_rate": t.success_rate,
                    "last_updated": t.last_updated,
                    "decay_factor": t.decay_factor
                }
                for key, t in self.learned_transitions.items()
            },
            "metadata": {
                "version": "1.0",
                "created": datetime.now().isoformat(),
                "total_transitions": len(self.learned_transitions),
                "learning_rate": self.learning_rate,
                "decay_rate": self.decay_rate
            }
        }

        try:
            with open(self.transitions_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save learned transitions: {e}")

# ── Integration Functions ─────────────────────────────────────────────────

def integrate_learner_into_linker():
    """
    Example of how to integrate TransitionLearner into SequenceLinker.

    This would modify SequenceLinker._score_transition()
    """
    # Example integration code (not executed)
    """
    def __init__(self, ..., transition_learner: Optional[TransitionLearner] = None):
        # ...
        self.transition_learner = transition_learner

    def _score_transition(self, from_id: str, to_id: str, context_bucket: str) -> float:
        # Get learned weight if available
        if self.transition_learner:
            learned_weight = self.transition_learner.get_learned_weight(
                from_id, to_id, context_bucket
            )
            if learned_weight != 0.5:  # 0.5 is neutral fallback
                return learned_weight

        # Fall back to static transitions
        # ... existing code ...
    """
    pass

# ── Module Test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Test transition learning
    logging.basicConfig(level=logging.INFO)

    from dataclasses import dataclass, field

    @dataclass
    class MockStep:
        pattern_id: str

    @dataclass
    class MockChainPlan:
        steps: List[MockStep] = field(default_factory=list)

    learner = TransitionLearner("data/knowledge_cloud/learned_transitions.json")

    # Create mock chain plans
    successful_chain = MockChainPlan(steps=[
        MockStep("cloud_dragon"),
        MockStep("cloud_castle"),
        MockStep("cloud_quest")
    ])

    failed_chain = MockChainPlan(steps=[
        MockStep("cloud_dragon"),
        MockStep("cloud_treasure"),
        MockStep("cloud_unknown")
    ])

    # Record feedback
    learner.record_feedback(successful_chain, success_score=0.9, player_emotion="curious")
    learner.record_feedback(failed_chain, success_score=0.2, player_emotion="afraid")

    # Update transitions
    learner.update_transitions()

    # Check learned weights
    weight1 = learner.get_learned_weight("cloud_dragon", "cloud_castle", "general")
    weight2 = learner.get_learned_weight("cloud_dragon", "cloud_treasure", "general")

    print(f"Dragon→Castle weight: {weight1}")
    print(f"Dragon→Treasure weight: {weight2}")

    # Get stats
    stats = learner.get_transition_stats()
    print(f"Learning stats: {stats}")
