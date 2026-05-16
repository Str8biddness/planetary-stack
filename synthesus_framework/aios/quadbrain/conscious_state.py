from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone


@dataclass
class FluidState:
    """Psi_f(t): Fluid Intelligence / Pattern State"""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    context_id: str = "default_session"
    novelty_score: float = 0.0
    uncertainty: float = 0.0
    active_patterns: List[Dict[str, Any]] = field(default_factory=list)
    working_memory: List[Dict[str, Any]] = field(default_factory=list)
    embedding_state: Dict[str, Any] = field(default_factory=lambda: {
        "situation_vector": [],
        "recent_event_vectors": []
    })
    # Legacy fields mapping
    active_hypotheses: List[str] = field(default_factory=list)
    belief_scores: Dict[str, float] = field(default_factory=dict)
    policy_prior: float = 0.5
    risk_outcome: float = 0.1
    attention: float = 0.5
    current_domain: str = "sysops"
    
    # Transformer attention fields (from ConsciousLlmAi integration)
    attention_maps: List[Any] = field(default_factory=list)
    transformer_output: Optional[Any] = None
    attention_focus_tokens: List[int] = field(default_factory=list)
    attention_entropy: float = 0.0
    pattern_confidence: float = 0.0

    def to_dict(self):
        return {
            "timestamp": self.timestamp,
            "context_id": self.context_id,
            "novelty_score": self.novelty_score,
            "uncertainty": self.uncertainty,
            "active_patterns": self.active_patterns,
            "working_memory": self.working_memory,
            "active_hypotheses": self.active_hypotheses,
            "belief_scores": self.belief_scores,
            "attention_entropy": self.attention_entropy,
            "pattern_confidence": self.pattern_confidence,
        }


@dataclass
class CrystallizedState:
    """M_c(t): Crystallized Intelligence / Knowledge State"""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    traits: Dict[str, float] = field(default_factory=dict)
    semantic_knowledge_refs: List[str] = field(default_factory=list)
    graph_context: Dict[str, Any] = field(default_factory=lambda: {
        "focus_nodes": [],
        "important_edges": []
    })
    skills: Dict[str, Any] = field(default_factory=dict)
    
    # Legacy fields
    facts: Dict[str, bool] = field(default_factory=dict)
    candidate_rules: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self):
        return {
            "timestamp": self.timestamp,
            "traits": self.traits,
            "semantic_knowledge_refs": self.semantic_knowledge_refs,
            "graph_context": self.graph_context,
            "skills": self.skills,
            "facts": self.facts
        }


@dataclass
class NarrativeState:
    """N_s(t): Narrative Simulation / Identity State"""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    identity: str = "ghostkey"
    current_role: str = "sentinel"
    scene_tag: str = "system_monitoring"
    goals: List[Dict[str, Any]] = field(default_factory=lambda: [
        {"id": "protect_host", "priority": 0.9}
    ])
    emotional_tone: Dict[str, float] = field(default_factory=lambda: {"valence": 0.0, "arousal": 0.5})
    continuity_summary: str = "Monitoring system integrity."
    narrative_constraints: List[str] = field(default_factory=lambda: [
        "never_leak_device_metadata",
        "prioritize_local_compute"
    ])
    
    # Legacy fields
    timeline: List[Any] = field(default_factory=list)

    def to_dict(self):
        return {
            "timestamp": self.timestamp,
            "identity": self.identity,
            "current_role": self.current_role,
            "scene_tag": self.scene_tag,
            "goals": self.goals,
            "emotional_tone": self.emotional_tone,
            "continuity_summary": self.continuity_summary,
            "narrative_constraints": self.narrative_constraints
        }


@dataclass
class IntegratedConsciousnessState:
    """C(t): The fused, actionable self-state"""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    context_id: str = "default_session"
    self_vector: List[float] = field(default_factory=list)
    dominant_motive: str = "protect_host"
    dominant_emotion: str = "vigilant"
    action_biases: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.8
    update_directives: Dict[str, Any] = field(default_factory=lambda: {
        "memory": {},
        "parameters": {}
    })
    t: int = 0

    def to_dict(self):
        return {
            "timestamp": self.timestamp,
            "context_id": self.context_id,
            "dominant_motive": self.dominant_motive,
            "dominant_emotion": self.dominant_emotion,
            "action_biases": self.action_biases,
            "confidence": self.confidence,
            "update_directives": self.update_directives,
            "t": self.t
        }


@dataclass
class NarrativeEvent:
    """A single reasoning event on the narrative timeline.
    
    Records the query, engines used, summary, explanations, and actions
    for each cognitive tick. Forms the episodic trace of the character's
    reasoning process.
    
    Attributes:
        t: Discrete cognitive time step.
        query: The original user/system query.
        engines_used: List of reasoning engine names that contributed.
        summary: Human-readable summary of the reasoning outcome.
        role: Narrative role — "analyst", "investigator", "observer", "default".
        emotional_tone: Affective tone label — "neutral", "curious", "alarmed", etc.
        proof_trace: Formal proof or reasoning trace string.
        explanations: List of abductive/deductive explanations with confidence.
        actions_taken: List of system actions taken in response to the query.
        generation_trace: GenerationTrace from probabilistic decoder (if used).
    """
    t: int
    query: str
    engines_used: List[str]
    summary: str
    role: str = "default"
    emotional_tone: str = "neutral"
    proof_trace: str = ""
    explanations: List[str] = field(default_factory=list)
    actions_taken: List[Dict[str, Any]] = field(default_factory=list)
    generation_trace: Optional[Any] = None


@dataclass
class ConsciousState:
    """Legacy wrapper to maintain compatibility while transitioning to the formal C(t) model."""
    t: int = 0
    fluid: FluidState = field(default_factory=FluidState)
    crystallized: CrystallizedState = field(default_factory=CrystallizedState)
    narrative: NarrativeState = field(default_factory=NarrativeState)
    integrated: Optional[IntegratedConsciousnessState] = None

    def next_tick(self) -> "ConsciousState":
        self.t += 1
        return self

    def to_context_dict(self) -> Dict[str, Any]:
        if self.integrated:
            return self.integrated.to_dict()
        return {
            "t": self.t,
            "role": self.narrative.current_role,
            "tone": str(self.narrative.emotional_tone),
            "n_events": len(self.narrative.timeline),
            "beliefs": self.fluid.belief_scores
        }
