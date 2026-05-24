import asyncio
import time
import logging
from typing import Any, Dict, List, Optional
from .conscious_state import ConsciousState, FluidState, CrystallizedState, NarrativeState, IntegratedConsciousnessState
from .consciousness_integrator import ConsciousnessIntegrator
from .cognitive_core import CognitiveCore
from .synth_runtime import get_runtime

# Reasoning tracer integration
try:
    from .reasoning_tracer import get_tracer, Hemisphere, TraceEventType
    _tracer = get_tracer(enable_streaming=True)
    _TRACING_ENABLED = True
except ImportError:
    _tracer = None
    _TRACING_ENABLED = False

logger = logging.getLogger(__name__)

class QuadbrainMaster:
    """
    The Quadbrain Architecture implementation using the formal Consciousness API.
    C(t) = Psi_f(t) ⊕ M_c(t) ⊕ N_s(t)
    """
    def __init__(self):
        self.runtime = get_runtime()
        self.brain_cognitive = CognitiveCore()
        
        self.shared_state = ConsciousState()
        self.integrator = ConsciousnessIntegrator()
        
        # ML Swarm Integration
        from ml.intent_classifier import IntentClassifier
        from ml.sentiment_analyzer import SentimentAnalyzer
        self.intent_clf = IntentClassifier()
        self.sentiment_clf = SentimentAnalyzer()
        
        # Parameter Cloud Integration
        from api.parameter_cloud import ParameterCloudStore
        self.param_cloud = ParameterCloudStore()
        
        # Tooling
        from .tools.baseliner import Baseliner
        self.baseliner = Baseliner()
        
        from .tools.immune_system import ImmuneSystem
        self.immune_system = ImmuneSystem()
        
        from .tools.ghost_net import GhostNetNode
        self.ghost_net = GhostNetNode()
        # Start the P2P listener
        self.ghost_net.start()
        
        # Initial training (lightweight)
        try:
            self.intent_clf.train(run_cv=False)
            self.sentiment_clf.train()
        except Exception as e:
            logger.error(f"Failed to train ML Swarm: {e}")

    async def compute_crystal_state(self, query: str, state: ConsciousState) -> CrystallizedState:
        """Brain 1 (Memory Brain): Updates M_c(t) from Parameter Cloud"""
        await asyncio.sleep(0.01)
        crystal = state.crystallized
        
        # Fetch latest traits from cloud
        cloud_data = self.param_cloud.fetch()
        if cloud_data.parameters:
            # Update traits and facts from cloud
            for k, v in cloud_data.parameters.items():
                if k.startswith("trait_"):
                    crystal.traits[k.replace("trait_", "")] = float(v)
                elif k.startswith("fact_"):
                    crystal.facts[k.replace("fact_", "")] = v
        
        if "security_rules_loaded" not in crystal.facts:
            crystal.facts["security_rules_loaded"] = True
            crystal.candidate_rules["unauthorized_port=>anomaly"] = {"positive": 10, "negative": 0}
            crystal.candidate_rules["high_cpu=>anomaly"] = {"positive": 5, "negative": 0}
            
        return crystal

    async def compute_fluid_state(self, query: str, state: ConsciousState) -> FluidState:
        """
        Brain 3 (Pattern Brain): Updates Psi_f(t) using Transformer Attention + Sentiment.
        
        Integrates ConsciousLlmAi's lightweight transformer for deep pattern recognition,
        providing attention-based analysis alongside traditional sentiment detection.
        """
        await asyncio.sleep(0.01)
        fluid = state.fluid
        query_lc = query.lower()
        
        # === NEW: Transformer Attention Analysis ===
        try:
            from core.psi_transformer_attention import get_psi_transformer
            psi_transformer = get_psi_transformer(num_layers=3, d_model=256, num_heads=4)
            
            # Convert query to simple tokens (word-based)
            tokens = query_lc.split()
            token_ids = [hash(word) % 10000 for word in tokens]  # Simple hashing for demo
            
            # Process through transformer
            attention_analysis = psi_transformer.process(
                text_tokens=token_ids,
                query_context=query,
            )
            
            # Update fluid state with transformer insights
            fluid.attention_maps = [a.tolist() for a in attention_analysis.attention_maps]
            fluid.attention_focus_tokens = attention_analysis.focus_tokens
            fluid.attention_entropy = attention_analysis.entropy
            fluid.pattern_confidence = attention_analysis.confidence
            fluid.novelty_score = max(fluid.novelty_score, attention_analysis.novelty_score)
            fluid.uncertainty = max(fluid.uncertainty, attention_analysis.uncertainty)
            
            # Add transformer-based hypotheses
            for hypothesis in attention_analysis.active_hypotheses:
                if hypothesis not in fluid.active_hypotheses:
                    fluid.active_hypotheses.append(f"[Transformer] {hypothesis}")
            
            # Store pattern detection result
            fluid.active_patterns.append({
                "pattern_type": attention_analysis.pattern_detected,
                "confidence": attention_analysis.confidence,
                "focus_tokens": attention_analysis.focus_tokens[:3],
                "entropy": attention_analysis.entropy,
            })
            
        except Exception as e:
            # Graceful fallback if transformer unavailable
            logger.warning(f"Psi transformer analysis failed: {e}")
            fluid.active_hypotheses.append("[Transformer] Pattern analysis unavailable")
        
        # === LEGACY: Sentiment Analysis (preserved) ===
        sentiment_label, sentiment_conf = self.sentiment_clf.predict(query)
        if sentiment_label == "threatening":
            fluid.uncertainty = max(fluid.uncertainty, 0.6)
            fluid.active_hypotheses.append(f"[Sentiment] Threat detected (conf={sentiment_conf:.2f})")
        elif sentiment_label == "negative":
            fluid.novelty_score = max(fluid.novelty_score, 0.4)
            fluid.active_hypotheses.append("[Sentiment] Negative sentiment detected")

        # Update baseline if auditing
        if "[Context from analyzer: audit]" in query:
            import re
            ports = [int(p) for p in re.findall(r'"port": (\d+)', query)]
            processes = re.findall(r'"name": "([^"]+)"', query)
            self.baseliner.record_sample(ports, processes)
            fluid.novelty_score = 0.8
            fluid.active_hypotheses.append("[System] Audit context detected")
            
        # Digital Immune System Check
        immune_anomalies = self.immune_system.check_integrity()
        if immune_anomalies:
            fluid.uncertainty = 1.0
            for anomaly in immune_anomalies:
                fluid.active_hypotheses.append(f"[Immune] Alert: {anomaly}")

        # GhostNet P2P Threat Ingestion
        p2p_threats = self.ghost_net.get_recent_external_threats()
        if p2p_threats:
            fluid.novelty_score = max(fluid.novelty_score, 0.7)
            for threat in p2p_threats:
                fluid.active_hypotheses.append(f"[GhostNet] Alert: {threat}")

        return fluid

    async def compute_narrative_state(self, query: str, state: ConsciousState) -> NarrativeState:
        """Brain 4 pre-processing (Meta Brain): Updates N_s(t) using Intent classification"""
        await asyncio.sleep(0.01)
        narrative = state.narrative
        
        # Use ML Intent Classifier
        intent_label, intent_conf = self.intent_clf.predict(query)
        
        if intent_label == "combat" or "security" in query.lower() or "scan" in query.lower():
            narrative.current_role = "vigilant_sentinel"
            narrative.emotional_tone["arousal"] = 0.8
        elif intent_label == "question":
            narrative.current_role = "analytical_sentinel"
            narrative.emotional_tone["arousal"] = 0.6
        else:
            narrative.current_role = "sentinel"
            narrative.emotional_tone["arousal"] = 0.5
            
        return narrative

    async def execute_action(self, query: str, integrated_state: IntegratedConsciousnessState, state: ConsciousState, character_id: str, trace_id: Optional[str] = None) -> Dict[str, Any]:
        """Brain 2 & 4 (Cognitive/Executive): Takes C(t) and produces actions and rendering."""
        from .generation.llm_bridge import LLMBridge, FallbackGenerator
        llm = LLMBridge()
        fallback = FallbackGenerator()
        
        # We run the query through CognitiveCore to generate timeline events and tool calls
        temp_state = await self.brain_cognitive.process(query=query, cs=state, character_id=character_id)
        
        event = temp_state.narrative.timeline[-1] if temp_state.narrative.timeline else None
        
        # Autonomous Threat Mitigation based on C(t) biases
        summary_modifier = ""
        if integrated_state.dominant_emotion == "alert" or any(b["action"] == "investigate_anomaly" for b in integrated_state.action_biases):
            if event and any("alert" in e.lower() or "threat" in e.lower() for e in event.explanations):
                # Autonomously dispatch mitigation (simulated)
                summary_modifier = " [AUTONOMOUS MITIGATION ENGAGED]"
                
                # Broadcast the threat to Ghost-Net
                for explanation in event.explanations:
                    if "alert" in explanation.lower() or "threat" in explanation.lower():
                        self.ghost_net.broadcast_threat("autonomous_action", explanation)

        # Update traits in Parameter Cloud based on interaction
        if state.t % 5 == 0:
            self.param_cloud.update({
                "trait_vigilance": integrated_state.confidence,
                "fact_last_query_t": state.t,
                "fact_dominant_emotion": integrated_state.dominant_emotion
            })

        plan = {
            "query": query,
            "summary": (event.summary if event else "Nominal.") + summary_modifier,
            "key_points": event.explanations if event else [],
            "tone": integrated_state.dominant_emotion,
            "role": integrated_state.dominant_motive,
            "confidence": integrated_state.confidence
        }

        # Enrich prompt with ML signals
        prompt = (f"[SIGNAL - EMOTION: {plan['tone'].upper()} | CONFIDENCE: {plan['confidence']:.2f}]\n"
                  f"System Report: {plan['summary']}\n"
                  f"Reasoning: {', '.join(plan['key_points'])}\n"
                  f"User Query: {query}\n"
                  f"Response (Stay in character as Ghostkey, be fluent and precise):")
        
        # Trace LLM generation start
        if trace_id:
            _tracer.add_event(
                trace_id=trace_id,
                event_type=TraceEventType.EXECUTION_START,
                hemisphere=Hemisphere.VO,
                data={
                    "prompt_length": len(prompt),
                    "tone": plan['tone'],
                    "confidence": plan['confidence'],
                },
            )
        
        llm_start = time.time()
        answer = await llm.generate(prompt)
        llm_latency_ms = (time.time() - llm_start) * 1000
        
        if not answer:
            answer = fallback.generate(plan)
        
        # Trace LLM completion
        if trace_id:
            _tracer.capture_hemisphere_state(
                trace_id=trace_id,
                hemisphere=Hemisphere.VO,
                inputs={"prompt": prompt[:200]},
                outputs={"answer_length": len(answer), "used_fallback": not answer},
                confidence=plan['confidence'],
                latency_ms=llm_latency_ms,
                metadata={"llm_latency_ms": llm_latency_ms},
            )
        
        await llm.close()

        return {
            "t": state.t,
            "answer": answer,
            "context": state.to_context_dict(),
            "event": event,
            "quadbrain_metrics": {
                "c_t_confidence": integrated_state.confidence,
                "c_t_emotion": integrated_state.dominant_emotion,
                "intent": self.intent_clf.predict(query)[0]
            }
        }

    async def think(self, query: str, character_id: str = "ghostkey", **kwargs) -> Dict[str, Any]:
        """Executes the formalized Quadbrain integration cycle with full reasoning traces."""
        # Start reasoning trace if enabled
        trace_id = None
        if _TRACING_ENABLED and _tracer:
            trace_id = _tracer.start_trace(
                query=query,
                character_id=character_id,
                enable_streaming=kwargs.get("stream_reasoning", False),
            )
            _tracer.add_event(
                trace_id=trace_id,
                event_type=TraceEventType.EXECUTION_START,
                data={"query": query, "character_id": character_id},
            )
        
        self.shared_state.next_tick()
        t = self.shared_state.t
        
        # Record start time for hemisphere timing
        hemisphere_start_times = {}
        
        # 1. Parallel Generation of Sub-states with tracing
        
        # NS (Crystal/Memory Brain)
        if trace_id:
            hemisphere_start_times[Hemisphere.NS] = time.time()
            _tracer.add_event(
                trace_id=trace_id,
                event_type=TraceEventType.HEMISPHERE_START,
                hemisphere=Hemisphere.NS,
                data={"inputs": {"query": query, "state": "crystallized"}},
            )
        
        crystal_task = asyncio.create_task(self.compute_crystal_state(query, self.shared_state))
        
        # Psi (Fluid/Pattern Brain)
        if trace_id:
            hemisphere_start_times[Hemisphere.PSI] = time.time()
            _tracer.add_event(
                trace_id=trace_id,
                event_type=TraceEventType.HEMISPHERE_START,
                hemisphere=Hemisphere.PSI,
                data={"inputs": {"query": query, "state": "fluid"}},
            )
        
        fluid_task = asyncio.create_task(self.compute_fluid_state(query, self.shared_state))
        
        # MC/Narrative (Meta Brain)
        if trace_id:
            hemisphere_start_times[Hemisphere.MC] = time.time()
            _tracer.add_event(
                trace_id=trace_id,
                event_type=TraceEventType.HEMISPHERE_START,
                hemisphere=Hemisphere.MC,
                data={"inputs": {"query": query, "state": "narrative"}},
            )
        
        narrative_task = asyncio.create_task(self.compute_narrative_state(query, self.shared_state))
        
        # Collect results
        M_c = await crystal_task
        if trace_id:
            latency_ms = (time.time() - hemisphere_start_times[Hemisphere.NS]) * 1000
            _tracer.capture_hemisphere_state(
                trace_id=trace_id,
                hemisphere=Hemisphere.NS,
                inputs={"query": query},
                outputs=M_c.to_dict(),
                confidence=0.7 if M_c.facts else 0.5,
                latency_ms=latency_ms,
                metadata={"facts_count": len(M_c.facts), "traits_count": len(M_c.traits)},
            )
        
        Psi_f = await fluid_task
        if trace_id:
            latency_ms = (time.time() - hemisphere_start_times[Hemisphere.PSI]) * 1000
            _tracer.capture_hemisphere_state(
                trace_id=trace_id,
                hemisphere=Hemisphere.PSI,
                inputs={"query": query},
                outputs=Psi_f.to_dict(),
                confidence=1.0 - Psi_f.uncertainty,
                latency_ms=latency_ms,
                metadata={
                    "hypotheses": len(Psi_f.active_hypotheses),
                    "uncertainty": Psi_f.uncertainty,
                    "novelty": Psi_f.novelty_score,
                    "attention_entropy": Psi_f.attention_entropy,
                    "pattern_confidence": Psi_f.pattern_confidence,
                    "has_attention_maps": len(Psi_f.attention_maps) > 0,
                    "active_patterns": len(Psi_f.active_patterns),
                },
            )
        
        N_s = await narrative_task
        if trace_id:
            latency_ms = (time.time() - hemisphere_start_times[Hemisphere.MC]) * 1000
            _tracer.capture_hemisphere_state(
                trace_id=trace_id,
                hemisphere=Hemisphere.MC,
                inputs={"query": query},
                outputs=N_s.to_dict(),
                confidence=0.8 if N_s.timeline else 0.6,
                latency_ms=latency_ms,
                metadata={
                    "role": N_s.current_role,
                    "arousal": N_s.emotional_tone.get("arousal", 0.5),
                },
            )
        
        self.shared_state.crystallized = M_c
        self.shared_state.fluid = Psi_f
        self.shared_state.narrative = N_s
        
        # 2. Integration: Compute C(t)
        if trace_id:
            _tracer.add_event(
                trace_id=trace_id,
                event_type=TraceEventType.INTEGRATION,
                data={
                    "inputs": {
                        "Psi_f_confidence": 1.0 - Psi_f.uncertainty,
                        "M_c_facts": len(M_c.facts),
                        "N_s_role": N_s.current_role,
                    },
                },
            )
        
        C_t = self.integrator.integrate(Psi_f, M_c, N_s, t)
        self.shared_state.integrated = C_t
        
        if trace_id:
            _tracer.add_event(
                trace_id=trace_id,
                event_type=TraceEventType.CONFIDENCE_UPDATE,
                data={
                    "integrated_confidence": C_t.confidence,
                    "dominant_emotion": C_t.dominant_emotion,
                    "action_biases": len(C_t.action_biases),
                },
            )
        
        # 3. Execution based on C(t)
        final_result = await self.execute_action(query, C_t, self.shared_state, character_id, trace_id)
        
        # End trace
        if trace_id and _tracer:
            trace = _tracer.end_trace(
                trace_id=trace_id,
                final_answer=final_result.get("answer", ""),
                overall_confidence=final_result.get("quadbrain_metrics", {}).get("c_t_confidence", 0.5),
            )
            final_result["trace_id"] = trace_id
            final_result["reasoning_summary"] = trace.to_dict()
        
        return final_result
