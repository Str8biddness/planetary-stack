import asyncio
import time
from typing import Any, Dict, List, Optional
from .conscious_state import ConsciousState, FluidState, CrystallizedState, NarrativeState, IntegratedConsciousnessState
from .consciousness_integrator import ConsciousnessIntegrator
from .cognitive_core import CognitiveCore

class QuadbrainMaster:
    """
    The Quadbrain Architecture implementation using the formal Consciousness API.
    C(t) = Psi_f(t) ⊕ M_c(t) ⊕ N_s(t)
    """
    def __init__(self):
        self.brain_memory = CognitiveCore()
        self.brain_cognitive = CognitiveCore()
        self.brain_pattern = CognitiveCore()
        self.brain_executive = CognitiveCore()
        
        self.shared_state = ConsciousState()
        self.integrator = ConsciousnessIntegrator()
        
        from .tools.baseliner import Baseliner
        self.baseliner = Baseliner()
        
        from .tools.immune_system import ImmuneSystem
        self.immune_system = ImmuneSystem()
        
        from .tools.ghost_net import GhostNetNode
        self.ghost_net = GhostNetNode()
        # Start the P2P listener
        self.ghost_net.start()

    async def compute_crystal_state(self, query: str, state: ConsciousState) -> CrystallizedState:
        """Brain 1 (Memory Brain): Updates M_c(t)"""
        await asyncio.sleep(0.01)
        crystal = state.crystallized
        
        if "security_rules_loaded" not in crystal.facts:
            crystal.facts["security_rules_loaded"] = True
            crystal.candidate_rules["unauthorized_port=>anomaly"] = {"positive": 10, "negative": 0}
            crystal.candidate_rules["high_cpu=>anomaly"] = {"positive": 5, "negative": 0}
            
        return crystal

    async def compute_fluid_state(self, query: str, state: ConsciousState) -> FluidState:
        """Brain 3 (Pattern Brain): Updates Psi_f(t)"""
        await asyncio.sleep(0.01)
        fluid = state.fluid
        query_lc = query.lower()

        # Update baseline if auditing
        if "[Context from analyzer: audit]" in query:
            import re
            ports = [int(p) for p in re.findall(r'"port": (\d+)', query)]
            processes = re.findall(r'"name": "([^"]+)"', query)
            self.baseliner.record_sample(ports, processes)
            fluid.novelty_score = 0.8
            fluid.active_hypotheses.append("system_audited")
            
        # Digital Immune System Check
        immune_anomalies = self.immune_system.check_integrity()
        if immune_anomalies:
            fluid.uncertainty = 1.0
            for anomaly in immune_anomalies:
                fluid.active_hypotheses.append(f"Immune Alert: {anomaly}")

        # GhostNet P2P Threat Ingestion
        p2p_threats = self.ghost_net.get_recent_external_threats()
        if p2p_threats:
            fluid.novelty_score = max(fluid.novelty_score, 0.7)
            for threat in p2p_threats:
                fluid.active_hypotheses.append(f"GhostNet Alert: {threat}")

        # PPBRS Anomaly detection
        if "audit" in query_lc or "scan" in query_lc:
            # Let's say we found something
            if any("unauthorized" in h.lower() for h in fluid.active_hypotheses) or immune_anomalies:
                fluid.uncertainty = 0.9

        return fluid

    async def compute_narrative_state(self, query: str, state: ConsciousState) -> NarrativeState:
        """Brain 4 pre-processing (Meta Brain): Updates N_s(t)"""
        await asyncio.sleep(0.01)
        narrative = state.narrative
        
        if "security" in query.lower() or "scan" in query.lower() or "audit" in query.lower():
            narrative.current_role = "vigilant_sentinel"
            narrative.emotional_tone["arousal"] = 0.8
        else:
            narrative.current_role = "sentinel"
            narrative.emotional_tone["arousal"] = 0.5
            
        return narrative

    async def execute_action(self, query: str, integrated_state: IntegratedConsciousnessState, state: ConsciousState, character_id: str) -> Dict[str, Any]:
        """Brain 2 & 4 (Cognitive/Executive): Takes C(t) and produces actions and rendering."""
        from .generation.llm_bridge import LLMBridge, FallbackGenerator
        llm = LLMBridge()
        fallback = FallbackGenerator()
        
        # We run the query through CognitiveCore to generate timeline events and tool calls
        # (This is where AgentDispatcher lives)
        temp_state = await self.brain_cognitive.process(query=query, cs=state, character_id=character_id)
        
        event = temp_state.narrative.timeline[-1] if temp_state.narrative.timeline else None
        
        # Autonomous Threat Mitigation based on C(t) biases
        summary_modifier = ""
        if integrated_state.dominant_emotion == "anxious" or any(b["action"] == "investigate_anomaly" for b in integrated_state.action_biases):
            if event and any("unauthorized" in e.lower() or "immune alert" in e.lower() for e in event.explanations):
                # Autonomously dispatch mitigation
                mitigation_query = "Ghostkey Internal Directive: Mitigate security anomaly"
                await self.brain_executive.process(mitigation_query, state, character_id=character_id)
                summary_modifier = " [AUTONOMOUS MITIGATION ENGAGED]"
                
                # Broadcast the threat to Ghost-Net
                for explanation in event.explanations:
                    if "unauthorized" in explanation.lower() or "immune alert" in explanation.lower():
                        self.ghost_net.broadcast_threat("autonomous_action", explanation)

        plan = {
            "query": query,
            "summary": (event.summary if event else "Nominal.") + summary_modifier,
            "key_points": event.explanations if event else [],
            "tone": integrated_state.dominant_emotion,
            "role": integrated_state.dominant_motive
        }

        prompt = f"System Report: {plan['summary']}\nReasoning: {', '.join(plan['key_points'])}\nUser Query: {query}\nResponse (Stay in character as Ghostkey):"
        
        answer = await llm.generate(prompt)
        if not answer:
            answer = fallback.generate(plan)
        await llm.close()

        return {
            "t": state.t,
            "answer": answer,
            "context": state.to_context_dict(),
            "event": event,
            "quadbrain_metrics": {
                "c_t_confidence": integrated_state.confidence,
                "c_t_emotion": integrated_state.dominant_emotion
            }
        }

    async def think(self, query: str, character_id: str = "ghostkey", **kwargs) -> Dict[str, Any]:
        """Executes the formalized Quadbrain integration cycle."""
        self.shared_state.next_tick()
        t = self.shared_state.t
        
        # 1. Parallel Generation of Sub-states
        crystal_task = asyncio.create_task(self.compute_crystal_state(query, self.shared_state))
        fluid_task = asyncio.create_task(self.compute_fluid_state(query, self.shared_state))
        narrative_task = asyncio.create_task(self.compute_narrative_state(query, self.shared_state))
        
        M_c = await crystal_task
        Psi_f = await fluid_task
        N_s = await narrative_task
        
        self.shared_state.crystallized = M_c
        self.shared_state.fluid = Psi_f
        self.shared_state.narrative = N_s
        
        # 2. Integration: Compute C(t)
        C_t = self.integrator.integrate(Psi_f, M_c, N_s, t)
        self.shared_state.integrated = C_t
        
        # 3. Execution based on C(t)
        final_result = await self.execute_action(query, C_t, self.shared_state, character_id)
        
        return final_result
