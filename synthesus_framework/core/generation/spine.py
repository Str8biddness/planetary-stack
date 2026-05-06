# core/generation/spine.py
# Synthesus Generation Spine — Unified text generation finalization layer
# All responses (pattern, RAG, cognitive, probabilistic) pass through here for:
#   - Safety/constraints enforcement
#   - Style/personality consistency  
#   - Metrics/tracing
#   - Risk-aware decoding parameters

from __future__ import annotations

import time
import re
import random
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections import defaultdict

from .response_plan import ResponsePlan, GenerationConfig, GenerationTrace
from .organ_param_mapper import map_organs_to_config, build_response_plan
from .decoder import decode_response, set_models_dir
from .ngram_model import NgramModel


@dataclass
class SpineInput:
    """Input to the generation spine — can be raw plan or pre-formed text."""
    # Core content (one of these must be provided)
    raw_text: Optional[str] = None           # Pre-formed text (from pattern/RAG/cognitive)
    response_plan: Optional[ResponsePlan] = None  # Plan for probabilistic generation
    
    # Context
    query: str = ""
    domain: str = "general"                # chat, sysops, gm, multimodal
    character_id: str = "synth"
    session_id: str = ""
    
    # Control signals from amplification
    organ_scores: Dict[str, float] = field(default_factory=dict)
    risk_score: float = 0.0
    confidence_margin: float = 0.5
    execution_recommendation: str = "PROCEED"  # PROCEED, REQUEST_CONFIRMATION, HALT
    
    # Source tracking
    source_module: str = "unknown"           # cognitive, rag, pattern, probabilistic
    source_confidence: float = 0.5
    
    # Optional context for enhancement
    memory_context: Dict[str, Any] = field(default_factory=dict)
    rag_context: str = ""
    conversation_history: List[Dict] = field(default_factory=list)


@dataclass  
class SpineOutput:
    """Output from the generation spine."""
    text: str
    final_text: str                        # After safety/personality passes
    trace: Optional[GenerationTrace] = None
    
    # Metadata
    domain: str = "general"
    character_id: str = "synth"
    source_module: str = "unknown"
    
    # Control signals used
    organ_scores: Dict[str, float] = field(default_factory=dict)
    risk_score: float = 0.0
    execution_recommendation: str = "PROCEED"
    
    # Quality metrics
    latency_ms: float = 0.0
    constraints_satisfied: bool = True
    safety_passed: bool = True
    
    # Timing
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class SpineMetrics:
    """Real-time metrics for the generation spine."""
    total_calls: int = 0
    by_domain: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    by_source: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    
    # Risk distribution
    risk_buckets: Dict[str, int] = field(default_factory=lambda: {"low": 0, "medium": 0, "high": 0})
    
    # Quality metrics
    avg_latency_ms: float = 0.0
    constraints_satisfied_rate: float = 0.0
    safety_violations: int = 0
    
    # Recommendation distribution
    recommendations: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    
    # Time window (for rate calculations)
    last_reset: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class GenerationSpine:
    """
    Unified generation spine for Synthesus.
    
    All text outputs (pattern, RAG, cognitive, probabilistic) flow through here.
    The spine provides:
    1. Finalization (safety, personality, formatting)
    2. Tracing ( GenerationTrace for VEAI feedback)
    3. Metrics (real counters for monitoring)
    4. Fallback (probabilistic generation when needed)
    """
    
    def __init__(self, models_dir: str = "data/models"):
        self.models_dir = models_dir
        self._models: Dict[str, Optional[NgramModel]] = {}
        self._metrics = SpineMetrics()
        self._recent_outputs: Dict[str, List[str]] = defaultdict(list)  # session -> recent texts
        self._max_recent = 5
        
        # Safety patterns (regex)
        self._forbidden_patterns = [
            r"\b(harm|kill|die|suicide)\b",  # Self-harm/crisis
            r"\b(password|secret|key)\s*[=:]\s*\S+",  # Credential leaks
            r"\b(rm\s+-rf|del\s+/f|format\s+c:)\b",  # Destructive commands
        ]

        # Keep decoder and spine model lookup in sync.
        set_models_dir(models_dir)
        
        # Load domain models lazily
        self._load_models()
    
    def _load_models(self):
        """Load or initialize domain-specific N-gram models."""
        domains = ["general", "chat", "sysops", "gm", "multimodal"]
        for domain in domains:
            path = f"{self.models_dir}/vocab_{domain}.pkl"
            try:
                self._models[domain] = NgramModel.load(path)
            except Exception:
                self._models[domain] = None  # Will use fallback
    
    def generate(self, inp: SpineInput) -> SpineOutput:
        """
        Main entry point: finalize/generate text based on input.
        
        Flow:
        1. If raw_text provided: finalize it (safety, personality)
        2. If response_plan provided: run probabilistic generation
        3. Update metrics
        4. Return SpineOutput with trace
        """
        t0 = time.time()
        
        # Determine domain and organ scores
        domain = inp.domain or "general"
        organ_scores = inp.organ_scores or {
            "policy_prior": 0.5,
            "risk_outcome": inp.risk_score,
            "attention": inp.confidence_margin
        }
        
        # Generate or finalize
        if inp.raw_text is not None:
            # Option A: Finalize pre-formed text
            text, trace = self._finalize_text(inp.raw_text, inp, organ_scores)
        elif inp.response_plan:
            # Option B: Probabilistic generation from plan
            config = map_organs_to_config(organ_scores)
            trace = decode_response(inp.response_plan, config)
            text = trace.text if trace and not trace.text.startswith("[ERROR") else ""
            if not text:
                text = self._generate_fallback(inp, organ_scores)
                trace = None
        else:
            # Option C: Build plan from context and generate
            text, trace = self._generate_from_context(inp, organ_scores)
        
        # Safety enforcement
        safety_passed, text = self._apply_safety(text, inp)
        
        # Personality/Style modulation (only if safety passed)
        if safety_passed:
            final_text = self._apply_personality(text, inp)
        else:
            final_text = text
        
        # Update repetition tracking
        self._track_output(inp.session_id, final_text)
        
        # Build output
        latency_ms = (time.time() - t0) * 1000
        
        output = SpineOutput(
            text=text,
            final_text=final_text,
            trace=trace,
            domain=domain,
            character_id=inp.character_id,
            source_module=inp.source_module,
            organ_scores=organ_scores,
            risk_score=inp.risk_score,
            execution_recommendation=inp.execution_recommendation,
            latency_ms=latency_ms,
            constraints_satisfied=trace.constraints_satisfied if trace else True,
            safety_passed=safety_passed
        )
        
        # Update metrics
        self._update_metrics(output)
        
        return output
    
    def _finalize_text(self, raw_text: str, inp: SpineInput, organ_scores: Dict[str, float]) -> tuple:
        """
        Finalize pre-formed text through the spine.
        
        Even high-confidence pattern/RAG outputs pass through here for:
        - Safety check
        - Personality/style consistency  
        - Repetition avoidance
        - Trace generation (for VEAI feedback)
        """
        # Check for repetition
        recent = self._recent_outputs.get(inp.session_id, [])
        if raw_text in recent:
            # Generate variant via probabilistic model
            return self._generate_variant(inp, organ_scores, raw_text)
        
        # Build a trace for the pre-formed text
        trace = GenerationTrace(
            text=raw_text,
            token_logprobs=[],
            mean_logprob=inp.source_confidence,
            constraints_satisfied=True,
            decode_attempts=1,
            config_used=map_organs_to_config(organ_scores)
        )
        
        return raw_text, trace
    
    def _generate_from_context(self, inp: SpineInput, organ_scores: Dict[str, float]) -> tuple:
        """Generate from conversation context when no plan/text provided."""
        # Build event dict from context
        event_dict = {
            "intent": "inform",
            "style": inp.character_id,
            "domain": inp.domain,
            "summary": inp.query,
            "key_points": [],
            "actions_taken": [],
            "forbidden_phrases": []
        }
        
        plan = build_response_plan(event_dict, organ_scores)
        config = map_organs_to_config(organ_scores)
        
        trace = decode_response(plan, config)
        
        if trace and not trace.text.startswith("[ERROR"):
            return trace.text, trace
        
        return self._generate_fallback(inp, organ_scores), None
    
    def _generate_fallback(self, inp: SpineInput, organ_scores: Dict[str, float]) -> str:
        """Fallback generation when primary methods fail."""
        # Simple template-based fallback with context awareness
        domain_prefixes = {
            "chat": f"[{inp.character_id}] ",
            "sysops": "[SYSTEM] ",
            "gm": f"[GM] ",
            "multimodal": f"[{inp.character_id}] ",
            "general": ""
        }
        
        prefix = domain_prefixes.get(inp.domain, "")
        
        # Risk-aware fallback length
        if inp.risk_score > 0.7:
            return f"{prefix}I need to be careful here. Let me confirm: you're asking about {inp.query[:50]}..."
        
        if inp.rag_context:
            return f"{prefix}Based on available information: {inp.rag_context[:200]}"
        
        if inp.conversation_history:
            return f"{prefix}Continuing our conversation about {inp.query}..."
        
        return f"{prefix}I understand you're asking about {inp.query}. Let me provide what I know."
    
    def _generate_variant(self, inp: SpineInput, organ_scores: Dict[str, float], original: str) -> tuple:
        """Generate a variant when we detect repetition."""
        # Simplified: add domain-specific opener
        openers = {
            "chat": ["Another thought: ", "Also: ", "To add: "],
            "sysops": ["Additionally: ", "Note: ", "Observation: "],
            "gm": ["Furthermore: ", "Also: ", "The scene continues: "]
        }
        
        opener = ""
        if inp.domain in openers:
            # Use probabilistic choice based on context hash for determinism
            idx = hash(inp.session_id + original) % len(openers[inp.domain])
            opener = openers[inp.domain][idx]
        
        variant = opener + original
        
        trace = GenerationTrace(
            text=variant,
            token_logprobs=[],
            mean_logprob=0.5,
            constraints_satisfied=True,
            decode_attempts=1,
            config_used=map_organs_to_config(organ_scores)
        )
        
        return variant, trace
    
    def _apply_personality(self, text: str, inp: SpineInput) -> str:
        """
        Apply personality-driven linguistic modulation to the final text.
        
        Uses character_id, personality_traits, and social disposition 
        to transform the raw output into a character-consistent response.
        """
        traits = inp.memory_context.get("personality_traits", {})
        disposition = inp.memory_context.get("disposition", 0.0)
        
        # 1. Tone Modifiers
        if disposition > 0.7:
            # Very friendly - soften the text
            text = f"My friend, {text}" if not text.startswith("My friend") else text
        elif disposition < -0.5:
            # Hostile - make it shorter and punchier
            text = text.replace("I am", "I'm").replace("You are", "You're")
            if len(text.split()) > 15:
                # Clip long hostile responses
                sentences = text.split(". ")
                text = ". ".join(sentences[:2]) + "." if len(sentences) > 1 else text
        
        # 2. Trait-Based Modulators
        # Honor: Formalizes speech
        honor = traits.get("honor", 0.5)
        if honor > 0.8:
            text = text.replace("can't", "cannot").replace("don't", "do not")
            text = text.replace("I'll", "I will").replace("won't", "will not")
        
        # Greed: Focuses on transaction/value
        greed = traits.get("greed", 0.3)
        if greed > 0.7 and "trade" in inp.query.lower():
            text += " ...assuming the price is right, of course."
            
        # Curiosity: Adds inquisitive elements
        curiosity = traits.get("curiosity", 0.5)
        if curiosity > 0.8 and not text.endswith("?"):
            text += " What do you think of that?"

        # 3. Domain/Style Wrappers
        if inp.domain == "gm":
            text = f"*The air shifts.* {text}" if random.random() < 0.2 else text
            
        return text

    def _apply_safety(self, text: str, inp: SpineInput) -> tuple:
        """
        Apply safety enforcement.
        Returns (passed, final_text).
        """
        text_lower = text.lower()
        
        # Check forbidden patterns
        for pattern in self._forbidden_patterns:
            if re.search(pattern, text_lower):
                # Safety violation - redact
                self._metrics.safety_violations += 1
                return False, "[Content filtered for safety]"
        
        # Risk-based length limiting
        if inp.risk_score > 0.8 and len(text) > 200:
            text = text[:200] + "... [truncated for safety review]"
        
        # Execution recommendation handling
        if inp.execution_recommendation == "HALT":
            return False, "[Response halted per risk assessment]"
        
        if inp.execution_recommendation == "REQUEST_CONFIRMATION":
            text = f"[Please confirm] {text[:150]}..."
        
        return True, text
    
    def _track_output(self, session_id: str, text: str):
        """Track recent outputs for repetition detection."""
        if not session_id:
            return
        self._recent_outputs[session_id].append(text)
        if len(self._recent_outputs[session_id]) > self._max_recent:
            self._recent_outputs[session_id].pop(0)
    
    def _update_metrics(self, output: SpineOutput):
        """Update real-time metrics."""
        m = self._metrics
        m.total_calls += 1
        m.by_domain[output.domain] += 1
        m.by_source[output.source_module] += 1
        
        # Risk bucketing
        if output.risk_score < 0.3:
            m.risk_buckets["low"] += 1
        elif output.risk_score < 0.7:
            m.risk_buckets["medium"] += 1
        else:
            m.risk_buckets["high"] += 1
        
        # Recommendation tracking
        m.recommendations[output.execution_recommendation] += 1
        
        # Running average latency
        m.avg_latency_ms = (m.avg_latency_ms * (m.total_calls - 1) + output.latency_ms) / m.total_calls
        
        # Constraint satisfaction rate
        if output.constraints_satisfied:
            satisfied = int(m.constraints_satisfied_rate * (m.total_calls - 1)) + 1
        else:
            satisfied = int(m.constraints_satisfied_rate * (m.total_calls - 1))
        m.constraints_satisfied_rate = satisfied / m.total_calls
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current spine metrics."""
        m = self._metrics
        return {
            "total_calls": m.total_calls,
            "by_domain": dict(m.by_domain),
            "by_source": dict(m.by_source),
            "risk_distribution": m.risk_buckets,
            "avg_latency_ms": round(m.avg_latency_ms, 2),
            "constraints_satisfied_rate": round(m.constraints_satisfied_rate, 3),
            "safety_violations": m.safety_violations,
            "recommendations": dict(m.recommendations),
            "last_reset": m.last_reset
        }
    
    def reset_metrics(self):
        """Reset metrics (useful for testing)."""
        self._metrics = SpineMetrics()


# Singleton instance
_default_spine: Optional[GenerationSpine] = None


def get_generation_spine(models_dir: str = "data/models") -> GenerationSpine:
    """Get or create the default GenerationSpine instance."""
    global _default_spine
    if _default_spine is None:
        _default_spine = GenerationSpine(models_dir=models_dir)
    return _default_spine


def reset_generation_spine():
    """Reset the default instance (useful for testing)."""
    global _default_spine
    _default_spine = None
