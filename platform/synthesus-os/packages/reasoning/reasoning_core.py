# core/reasoning_core.py
# Synthesus 2.0 - Reasoning Core
# Orchestrates multi-step reasoning chains using hemisphere bridge + pattern engine

from __future__ import annotations

import asyncio
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from hemisphere_bridge import HemisphereBridge
from pattern_engine import PatternEngine, PatternMatch
from els_bridge import ELSBridge


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class ReasoningStep:
    """A single step in a multi-step reasoning chain.
    
    Records the input, output, type, confidence, and latency for each
    reasoning pass through the dual-hemisphere pipeline.
    
    Attributes:
        step_id: Unique identifier for this step.
        step_type: Type of reasoning — "left", "right", "synthesis", "pattern_recall".
        input_text: Raw input text to this reasoning step.
        output_text: Output produced by this step.
        confidence: Confidence score [0.0, 1.0] for this step's output.
        latency_ms: Wall-clock time in milliseconds for this step.
        metadata: Additional step-specific data (e.g., engine name, tokens used).
    """
    step_id: str
    step_type: str           # "left", "right", "synthesis", "pattern_recall"
    input_text: str
    output_text: str
    confidence: float = 0.0
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReasoningResult:
    """Complete result of a multi-step reasoning session.
    
    Contains the final response, all intermediate reasoning steps,
    aggregate metrics, and success/error state.
    
    Attributes:
        session_id: Unique session identifier for this reasoning run.
        character_id: Character whose reasoning core processed the query.
        query: The original user query string.
        final_response: The synthesized final response string.
        steps: Ordered list of ReasoningSteps in the pipeline.
        total_latency_ms: Total wall-clock time for the entire session.
        success: Whether the session completed without errors.
        error: Error message string if success=False.
    """
    session_id: str
    character_id: str
    query: str
    final_response: str
    steps: List[ReasoningStep] = field(default_factory=list)
    total_latency_ms: float = 0.0
    success: bool = True
    error: Optional[str] = None
    monologue: str = ""      # Hidden internal thought process
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# ReasoningCore
# ---------------------------------------------------------------------------

class ReasoningCore:
    """
    Orchestrates reasoning for a Synthesus character.

    Pipeline:
      1. Recall relevant patterns
      2. Left-hemisphere analytical pass
      3. Right-hemisphere creative/intuitive pass
      4. Synthesis via HemisphereBridge
      5. Log interaction via ELSBridge
      6. Discover new patterns from successful interactions
    """

    def __init__(
        self,
        character_id: str,
        hemisphere_bridge: Optional[HemisphereBridge] = None,
        pattern_engine: Optional[PatternEngine] = None,
        els_bridge: Optional[ELSBridge] = None,
        left_model: str = "left",
        right_model: str = "right",
    ):
        """Initializes the ReasoningCore.

        Args:
            character_id: The ID of the character using this core.
            hemisphere_bridge: Bridge for dual-hemisphere reasoning. Defaults to None.
            pattern_engine: Engine for pattern matching and discovery. Defaults to None.
            els_bridge: Bridge for interaction logging (Experience Learning System). Defaults to None.
            left_model: Model ID for the left hemisphere. Defaults to "left".
            right_model: Model ID for the right hemisphere. Defaults to "right".
        """
        self.character_id = character_id
        self.hb = hemisphere_bridge or HemisphereBridge()
        self.pe = pattern_engine or PatternEngine()
        self.els = els_bridge or ELSBridge()
        self.left_model = left_model
        self.right_model = right_model
        
        # Patent-Aligned State: Narrative Simulation Layer (Ns)
        self.self_narrative: str = f"I am {character_id}. My story begins now."
        self.consciousness_history: List[float] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reason(
        self,
        query: str,
        context: Optional[str] = None,
        session_id: Optional[str] = None,
        top_k_patterns: int = 3,
    ) -> ReasoningResult:
        """Processes a query through the full multi-step reasoning pipeline.

        Args:
            query: The user query string.
            context: Additional context for the query. Defaults to None.
            session_id: Unique session identifier. Defaults to a random UUID.
            top_k_patterns: Number of patterns to recall. Defaults to 3.

        Returns:
            A ReasoningResult containing the final response and pipeline steps.
        """
        session_id = session_id or str(uuid.uuid4())
        steps: List[ReasoningStep] = []
        t_start = time.perf_counter()

        pattern_context = self._recall_patterns(query, top_k_patterns, steps)
        
        # Phase 1: Fluid Intelligence (Thinking/Monologue)
        monologue = self._generate_internal_monologue(query, context, pattern_context)
        
        # Phase 2: Narrative Simulation (Updating Sense of Self - Ns)
        self._update_narrative_simulation(query, monologue)
        
        # Phase 3: Recursive Integration (Dual-Hemisphere pass)
        enriched = self._build_prompt(query, context, pattern_context, monologue, self.self_narrative)
        bridge_result = self._run_dual_hemisphere(enriched, context, pattern_context)
        
        final = bridge_result.get("response", "")
        
        # Phase 3: Persona Critic (Self-Correction)
        critique = self._critique_response(final, monologue)
        if critique.get("retry_needed") and bridge_result.get("execution_mode") != "sequential_fallback":
            # Force a more creative Right-Hemisphere retry
            steps.append(ReasoningStep(
                step_id=str(uuid.uuid4()),
                step_type="critic_feedback",
                input_text=final[:100],
                output_text=critique.get("reason", "Too generic"),
                confidence=0.1
            ))
            retry_prompt = f"{enriched}\n--- Critic Feedback ---\n{critique.get('instruction')}"
            final = self.hb.right(retry_prompt)

        left_response = bridge_result.get("left_response") or ""
        right_response = bridge_result.get("right_response") or ""
        left_confidence = float(bridge_result.get("left_confidence", 0.0))
        right_confidence = float(bridge_result.get("right_confidence", 0.0))
        raw_confidence = float(bridge_result.get("raw_confidence", max(left_confidence, right_confidence)))
        agreement_score = bridge_result.get("agreement_score")
        execution_mode = bridge_result.get("execution_mode", "parallel")
        state_handoff = bridge_result.get("state_handoff")

        if left_response:
            steps.append(ReasoningStep(
                step_id=str(uuid.uuid4()),
                step_type="left",
                input_text=enriched[:200],
                output_text=left_response[:500],
                confidence=left_confidence,
                latency_ms=float(bridge_result.get("left_latency_ms", 0.0)),
                metadata={
                    "model": self.left_model,
                    "execution_mode": execution_mode,
                    "agreement_score": agreement_score,
                    "state_handoff": state_handoff,
                },
            ))

        if right_response:
            steps.append(ReasoningStep(
                step_id=str(uuid.uuid4()),
                step_type="right",
                input_text=enriched[:200],
                output_text=right_response[:500],
                confidence=right_confidence,
                latency_ms=float(bridge_result.get("right_latency_ms", 0.0)),
                metadata={
                    "model": self.right_model,
                    "execution_mode": execution_mode,
                    "agreement_score": agreement_score,
                    "state_handoff": state_handoff,
                },
            ))

        steps.append(ReasoningStep(
            step_id=str(uuid.uuid4()),
            step_type="synthesis",
            input_text=f"left={left_response[:100]} | right={right_response[:100]}",
            output_text=final[:500],
            confidence=raw_confidence,
            latency_ms=float(bridge_result.get("latency_ms", 0.0)),
            metadata={
                "hemisphere_used": bridge_result.get("hemisphere_used", "both"),
                "agreement_score": agreement_score,
                "execution_mode": execution_mode,
                "state_handoff": state_handoff,
            },
        ))

        total_ms = (time.perf_counter() - t_start) * 1000

        result = ReasoningResult(
            session_id=session_id,
            character_id=self.character_id,
            query=query,
            final_response=final,
            steps=steps,
            total_latency_ms=round(total_ms, 2),
            success=True,
            monologue=monologue,
            metadata={
                "consciousness_score": self._calculate_consciousness_score(bridge_result),
                "narrative_drift": len(self.self_narrative) / 1000.0
            }
        )

        self._log_and_learn(query, final, result.success)

        return result

    def _run_dual_hemisphere(
        self,
        prompt: str,
        context: Optional[str],
        pattern_context: str,
    ) -> Dict[str, Any]:
        """Route the query through HemisphereBridge so both hemispheres share one contract."""
        character_context = {
            "character_id": self.character_id,
            "original_query": prompt,
            "explicit_context": context or "",
            "pattern_context": pattern_context,
        }

        async def _invoke() -> Dict[str, Any]:
            return await self.hb.route_query(
                prompt,
                hemisphere="both",
                character_context=character_context,
                rag_context=pattern_context,
            )

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(_invoke())

        with ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(asyncio.run, _invoke()).result()

    def _generate_internal_monologue(self, query: str, context: Optional[str], patterns: str) -> str:
        """Simulates an NPC's hidden internal thought process."""
        # This is a 'fast' monologue generator using pattern heuristics
        # In a high-latency mode, this could be a small local model pass.
        tokens = query.lower().split()
        
        # Look for emotional cues
        is_question = "?" in query
        is_aggressive = any(t in tokens for t in ["why", "stop", "no", "hate", "fight"])
        
        thought_parts = [f"[Thinking about: {query[:30]}...]"]
        
        if is_aggressive:
            thought_parts.append("The player seems pushy. I should stay guarded.")
        elif is_question:
            thought_parts.append("They want information. How much should I actually reveal?")
        else:
            thought_parts.append("A casual remark. I'll maintain the current vibe.")
            
        if "trade" in tokens or "gold" in tokens:
            thought_parts.append("There's money involved. I need to be smart here.")
            
        return " ".join(thought_parts)

    def _critique_response(self, response: str, monologue: str) -> Dict[str, Any]:
        """Evaluates if the response matches the internal monologue and persona."""
        if not response:
            return {"retry_needed": True, "reason": "Empty response", "instruction": "You said nothing. Speak!"}

        words = response.split()
        if len(words) < 5:
            return {
                "retry_needed": True,
                "reason": "Too short",
                "instruction": "Be more descriptive and elaborate on your thoughts.",
            }

        response_lower = response.lower()
        if "i am an ai" in response_lower or "as a language model" in response_lower:
            return {
                "retry_needed": True,
                "reason": "Out of character (AI leakage)",
                "instruction": "Stop speaking like a machine. Stay in character!",
            }

        if any(token in response_lower for token in ("friendly", "cheerful", "casual")) and "guarded" in monologue.lower():
            return {
                "retry_needed": True,
                "reason": "Tonal mismatch",
                "instruction": "Match the internal tone more closely; be less breezy and more aligned with the monologue.",
            }

        return {"retry_needed": False}

    def _update_narrative_simulation(self, query: str, monologue: str):
        """Updates the Narrative Simulation Layer (Ns) to maintain identity continuity."""
        # Recursive update: current narrative + new experience = next narrative
        summary = f"User asked '{query[:20]}'. I thought: {monologue[:30]}."
        
        # Keep narrative concise but cumulative
        max_narrative_len = 500
        new_narrative = f"{self.self_narrative} | Recently: {summary}"
        if len(new_narrative) > max_narrative_len:
            # Shift the window (preserving core identity)
            identity_prefix = self.self_narrative.split('|')[0]
            recent_events = new_narrative.split('|')[-2:]
            new_narrative = f"{identity_prefix} | {' | '.join(recent_events)}"
            
        self.self_narrative = new_narrative

    def _calculate_consciousness_score(self, bridge_result: Dict[str, Any]) -> float:
        """Implements the C(t) = Pf(t) + Mc(t) + Ns(t) patent equation."""
        pf = float(bridge_result.get("raw_confidence", 0.0))  # Fluid Intelligence
        mc = 0.8  # Crystallized (Stable knowledge baseline)
        ns = 1.0 if len(self.self_narrative) > 50 else 0.5   # Narrative Continuity
        
        # Calculate alignment score [0.0 - 1.0]
        score = (pf + mc + ns) / 3.0
        self.consciousness_history.append(score)
        return round(score, 3)

    # ------------------------------------------------------------------
    # Internal pipeline stages
    # ------------------------------------------------------------------

    def _recall_patterns(
        self,
        query: str,
        top_k: int,
        steps: List[ReasoningStep],
    ) -> str:
        """Recalls relevant patterns for the query.

        Args:
            query: The search query.
            top_k: Number of patterns to recall.
            steps: List of reasoning steps to append to.

        Returns:
            A formatted string of recalled patterns.
        """
        t0 = time.perf_counter()
        matches: List[PatternMatch] = self.pe.match(
            self.character_id, query, top_k=top_k
        )
        latency = (time.perf_counter() - t0) * 1000

        if not matches:
            return ""

        recalled = "\n".join(
            f"[Pattern {i+1} | score={m.score:.3f}]: {m.pattern.response_template[:120]}"
            for i, m in enumerate(matches)
        )

        steps.append(ReasoningStep(
            step_id=str(uuid.uuid4()),
            step_type="pattern_recall",
            input_text=query,
            output_text=recalled,
            confidence=matches[0].score if matches else 0.0,
            latency_ms=round(latency, 2),
            metadata={"num_patterns": len(matches)},
        ))
        return recalled

    def _run_hemisphere(
        self,
        side: str,
        prompt: str,
        model: str,
        steps: Optional[List[ReasoningStep]] = None,
    ) -> str:
        """Executes a single hemisphere pass.

        Args:
            side: Hemisphere side ("left" or "right").
            prompt: The input prompt.
            steps: Optional list of reasoning steps to append to.
            model: The model ID to use.

        Returns:
            The output string from the hemisphere pass.
        """
        t0 = time.perf_counter()
        if side == "left":
            out = self.hb.left(prompt)
        else:
            out = self.hb.right(prompt)
        latency = (time.perf_counter() - t0) * 1000

        if steps is not None:
            steps.append(ReasoningStep(
                step_id=str(uuid.uuid4()),
                step_type=side,
                input_text=prompt[:200],
                output_text=out[:500],
                confidence=0.0,
                latency_ms=round(latency, 2),
                metadata={"model": model},
            ))
        return out

    def _synthesize(
        self,
        left_out: str,
        right_out: str,
        steps: List[ReasoningStep],
    ) -> str:
        """Synthesizes the outputs from both hemispheres.

        Args:
            left_out: Output from the left hemisphere.
            right_out: Output from the right hemisphere.
            steps: List of reasoning steps to append to.

        Returns:
            The synthesized final response string.
        """
        t0 = time.perf_counter()
        combined = self.hb.synthesize(left_out, right_out)
        latency = (time.perf_counter() - t0) * 1000

        steps.append(ReasoningStep(
            step_id=str(uuid.uuid4()),
            step_type="synthesis",
            input_text=f"left={left_out[:100]} | right={right_out[:100]}",
            output_text=combined[:500],
            latency_ms=round(latency, 2),
        ))
        return combined

    def _build_prompt(
        self,
        query: str,
        context: Optional[str],
        pattern_context: str,
        monologue: str = "",
        narrative: str = "",
    ) -> str:
        """Constructs the final enriched prompt for the hemispheres.

        Args:
            query: The original user query.
            context: Additional user-provided context.
            pattern_context: String of recalled patterns.
            monologue: The hidden internal thought process.
            narrative: The recursive self-narrative (Ns).

        Returns:
            The complete prompt string.
        """
        parts = []
        if narrative:
            parts.append(f"--- Narrative Identity (Ns) ---\n{narrative}\n")
        if monologue:
            parts.append(f"--- Internal Thought ---\n{monologue}\n")
        if pattern_context:
            parts.append(f"--- Recalled Patterns ---\n{pattern_context}\n")
        if context:
            parts.append(f"--- Context ---\n{context}\n")
        parts.append(f"--- Query ---\n{query}")
        return "\n".join(parts)

    def _log_and_learn(
        self, query: str, response: str, success: bool
    ) -> None:
        """Logs the interaction to ELS and triggers pattern discovery.

        Args:
            query: The user query.
            response: The generated response.
            success: Whether the reasoning pass was successful.
        """
        try:
            self.els.capture(
                character_id=self.character_id,
                user_input=query,
                character_response=response,
                outcome_success=success,
            )
            self.pe.discover(
                character_id=self.character_id,
                interaction_text=f"{query} {response}",
                outcome_success=success,
            )
        except Exception:
            pass  # Non-fatal: logging/learning failures should not break reasoning

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        """Returns aggregate statistics for the reasoning core.

        Returns:
            A dictionary containing pattern and ELS metrics.
        """
        return {
            "character_id": self.character_id,
            "pattern_stats": self.pe.stats(self.character_id),
            "els_stats": self.els.stats(self.character_id),
        }
