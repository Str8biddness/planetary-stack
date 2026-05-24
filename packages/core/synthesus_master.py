import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from conscious_state import ConsciousState, NarrativeEvent
from cognitive_core import CognitiveCore
try:
    from log_ingest import ingest_system_metric
except Exception:
    ingest_system_metric = None
from aios_kernel_tool import AIOSKernelTool
from generation.organ_param_mapper import map_organs_to_config, build_response_plan
from generation.decoder import decode_response


class SynthesusMaster:
    """Main orchestrator for the Synthesus reasoning engine.
    
    Coordinates the dual-hemisphere architecture by managing CognitiveCore
    (right hemisphere) and the C++ kernel via AIOSKernelTool (left hemisphere).
    Processes queries through the conscious state machine, emits live thought
    events for streaming responses, and renders final answers.
    
    Attributes:
        core: CognitiveCore instance handling right-hemisphere cognitive modules.
        state: ConsciousState tracking narrative timeline, beliefs, and emotional state.
        feedback_stats: Accumulated feedback for self-improvement.
        kernel_tool: Interface to the C++ PPBRS kernel (left hemisphere).
        allow_kernel_actions: Whether to permit kernel-side actions (default False).
    """
    def __init__(self):
        """Initialize the SynthesusMaster orchestrator with CognitiveCore and ConsciousState."""
        self.core = CognitiveCore()
        self.state = ConsciousState()
        self.feedback_stats = {"total": 0, "correct": 0, "incorrect": 0}
        self.kernel_tool = AIOSKernelTool()
        self.allow_kernel_actions = False

    async def think(self,
                    query: str,
                    system_logs: Optional[List[Dict]] = None,
                    current_state: Optional[Dict[str, Any]] = None,
                    character_id: str = "master",
                    on_thought: Optional[Any] = None) -> Dict[str, Any]:
        """Process a query and return a faceted answer, emitting live thought events if on_thought is provided."""
        self.state.next_tick()
        
        # 1. Emit Initial Thinking State
        if on_thought:
            await on_thought({
                "type": "cognitive_event",
                "character_id": character_id,
                "status": "thinking",
                "query": query,
                "t": self.state.t
            })

        # 2. Cognitive Processing
        self.state = await self.core.process(query=query,
                                       cs=self.state,
                                       system_logs=system_logs,
                                       current_state=current_state,
                                       character_id=character_id)
        
        event = self.state.narrative.timeline[-1]
        
        # 3. Emit Processed State (with reasoning engines and beliefs)
        if on_thought:
            await on_thought({
                "type": "cognitive_event",
                "character_id": character_id,
                "status": "reasoned",
                "engines": event.engines_used,
                "emotional_tone": event.emotional_tone,
                "narrative_role": event.role,
                "beliefs": [
                    {"hypothesis": h, "score": s} 
                    for h, s in list(self.state.fluid.belief_scores.items())[:5]
                ],
                "t": self.state.t
            })

        print(f"[MASTER] t={self.state.t} | query={query} | engines={event.engines_used}")
        
        # 4. Rendering
        answer = self._render_answer(event, character_id=character_id)
        
        # 5. Final Answer Event
        if on_thought:
            await on_thought({
                "type": "cognitive_event",
                "character_id": character_id,
                "status": "complete",
                "answer_preview": answer[:100],
                "t": self.state.t
            })

        return {
            "t": self.state.t,
            "answer": answer,
            "context": self.state.to_context_dict(),
            "event": event,
        }

    async def record_feedback(self, event_id: int, feedback_type: str):
        """Record feedback on an event to adjust learning."""
        if event_id >= len(self.state.narrative.timeline):
            return False
        
        event = self.state.narrative.timeline[event_id]
        delta = 0.1 if feedback_type in ("correct", "helpful") else -0.1
        
        # Adjust belief scores for abductive events
        if "abductive" in event.engines_used:
            for hyp in event.explanations:
                # Extract raw hypothesis text before " (post="
                hyp_text = hyp.split(" (post=")[0]
                # 1) adjust belief_scores
                old = self.state.fluid.belief_scores.get(hyp_text, 0.5)
                self.state.fluid.belief_scores[hyp_text] = max(0.0, min(1.0, old + delta))
                # 2) adjust domain priors if hypothesis mentions known domains
                if hasattr(self.core.abductive, 'explanation_ranker') and hasattr(self.core.abductive.explanation_ranker, 'domain_priors'):
                    for domain in self.core.abductive.explanation_ranker.domain_priors:
                        if domain in hyp_text.lower():
                            p_old = self.core.abductive.explanation_ranker.domain_priors[domain]
                            self.core.abductive.explanation_ranker.domain_priors[domain] = max(
                                0.1, min(0.9, p_old + delta * 0.2)
                            )
        
        # Update feedback stats
        self.feedback_stats["total"] += 1
        if feedback_type in ("correct", "helpful"):
            self.feedback_stats["correct"] += 1
        elif feedback_type in ("incorrect", "not helpful"):
            self.feedback_stats["incorrect"] += 1
        
        # Update candidate rule stats
        delta_sign = 1 if feedback_type in ("correct", "helpful") else -1
        # Link explanations / hypotheses to rules by matching text
        for expl in event.explanations:
            hyp_text = expl.split(" (post=")[0]
            # Try to reconstruct rule_key with simple mapping
            # e.g., "Hypothesis for slowdown caused by high_cpu_usage"
            if "caused by" in hyp_text:
                _, cause_part = hyp_text.split("caused by", 1)
                cause = cause_part.strip().split()[0]  # "high_cpu_usage"
                effect = hyp_text.split("Hypothesis for", 1)[1].split("caused by")[0].strip()
                rule_key = f"{cause}=>{effect.replace(' ', '_')}"
                rules = self.state.crystallized.candidate_rules
                if rule_key in rules:
                    if delta_sign > 0:
                        rules[rule_key]["positive"] += 1
                    else:
                        rules[rule_key]["negative"] += 1
        
        # For inductive, adjust prediction confidence
        for expl in event.explanations:
            hyp_text = expl.split(" (post=")[0]
            if "caused by" in hyp_text:
                _, cause_part = hyp_text.split("caused by", 1)
                cause = cause_part.strip().split()[0]
                effect = hyp_text.split("Hypothesis for", 1)[1].split("caused by")[0].strip()
                rule_key = f"{cause}=>{effect.replace(' ', '_')}"
                if hasattr(self.core.inductive, 'learn_from_feedback'):
                    self.core.inductive.learn_from_feedback(rule_key, feedback_type in ("correct", "helpful"))
        
        return True

    async def safe_kernel_action(self,
                                 action: str,
                                 params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Gated interface to the self-rooting kernel tool.

        Safety layers:
        1) Deductive security check (AIOSDeductiveModule rules).
        2) Abductive justification: require strong explanation for why action is needed.
        3) Log any action in NarrativeEvent.actions_taken.
        """
        params = params or {}

        # Environment flag check
        if not self.allow_kernel_actions and action != "analyze":
            return {"error": "Kernel actions disabled in this environment."}

        # 1. Deductive security check: are we in an authorized context?
        # Map current conscious state into security facts.
        facts = {
            "user_authenticated": self.state.crystallized.facts.get("user_authenticated", False),
            "admin_privileges_granted": self.state.crystallized.facts.get("admin_privileges_granted", False),
        }
        # Ask the deductive engine to re-evaluate; this updates its KB.
        await self.think(
            "Given that user_authenticated and admin_privileges_granted, therefore system_access_allowed?"
        )
        if not self.state.crystallized.facts.get("system_access_allowed", False):
            return {"error": "Security preconditions not met; kernel action denied."}

        # 2. Abductive justification
        justification_query = f"Why should I perform kernel action {action}?"
        await self.think(justification_query, current_state=params)
        last_event = self.state.narrative.timeline[-1]
        strong_explanations = [
            e for e in last_event.explanations
            if "post=0.8" in e or "post=0.9" in e
        ]
        if not strong_explanations:
            return {"error": "No strong abductive justification; kernel action denied."}

        # 3. Perform the action via AIOSKernelTool
        if action == "analyze":
            result = self.kernel_tool.analyze()
        elif action == "autonomous_takeover":
            target = params.get("target_device")
            result = self.kernel_tool.autonomous_takeover(target)
        else:
            return {"error": f"Unknown kernel action '{action}'."}

        # 4. Log in narrative
        if self.state.narrative.timeline:
            self.state.narrative.timeline[-1].actions_taken.append({
                "action": "kernel_action",
                "kernel_operation": action,
                "params": params,
                "result": result,
            })

        return result

    def _render_answer(self, event: NarrativeEvent, character_id: str = "master") -> str:
        """Render a narrative event into a human-readable answer string with character identity."""
        
        # 1. Load character identity
        personality = []
        required_phrases = []
        
        try:
            char_dir = Path("characters") / character_id
            if char_dir.exists():
                # Load Bio
                bio_path = char_dir / "bio.json"
                if bio_path.exists():
                    with open(bio_path, "r") as f:
                        bio = json.load(f)
                        
                        # 1. Identity Name
                        if "name" in bio:
                            personality.append(f"identity_{bio['name']}")
                        
                        # 2. Personality Traits (Big 5 or custom)
                        persona = bio.get("persona", {})
                        traits = persona.get("personality_traits") or bio.get("traits", {})
                        if isinstance(traits, dict):
                            for trait, val in traits.items():
                                if isinstance(val, (int, float)) and val > 0.6:
                                    personality.append(f"trait_{trait}")
                                elif isinstance(val, str):
                                    personality.append(f"voice_{val}")
                        
                        # 3. Tone and Style as soft-prompts
                        if "tone" in persona:
                            for t in str(persona["tone"]).split(","):
                                personality.append(f"tone_{t.strip()}")
                        if "style" in persona:
                            personality.append(f"voice_{persona['style'][:50]}")

                # Load Knowledge (to extract anchors)
                kg_path = char_dir / "knowledge.json"
                if kg_path.exists():
                    with open(kg_path, "r") as f:
                        kg = json.load(f)
                        # Use evolution notes as context
                        notes = kg.get("evolution_notes", [])
                        if notes:
                            personality.extend(notes[-3:]) # Last 3 recent insights
        except Exception as e:
            print(f"[DEBUG] Character {character_id} meta load failed: {e}")

        # 2. Collect Organ Scores from Fluid State
        organ_scores = {
            "policy_prior": self.state.fluid.policy_prior,
            "risk_outcome": self.state.fluid.risk_outcome,
            "attention": self.state.fluid.attention
        }
        
        # 2. Build Generation Plan
        event_dict = {
            "intent": getattr(event, "intent", "inform"),
            "style": event.role,
            "domain": getattr(event, "domain", self.state.fluid.current_domain),
            "summary": event.summary,
            "key_points": event.explanations[:3],
            "personality": personality,
            "required_phrases": required_phrases,
            "actions_taken": event.actions_taken,
            "forbidden_phrases": [] # Can be extended with safety rules
        }
        
        try:
            plan = build_response_plan(event_dict, organ_scores)
            config = map_organs_to_config(organ_scores)
            
            # 3. Probabilistic Decoding
            trace = decode_response(plan, config)
            
            if trace and trace.text and "[ERROR" not in trace.text:
                # Store trace for potential amplification validation
                event.generation_trace = trace
                response_text = trace.text
                
                # Append tool results if they weren't absorbed by the generator
                if event.actions_taken:
                    tool_summaries = []
                    for action in event.actions_taken:
                        if action.get("type") == "tool_use":
                            desc = action.get("description", "Used a tool")
                            res = action.get("result", {})
                            if isinstance(res, dict):
                                content = res.get("context") or res.get("content") or (res.get("raw_result", {}).get("content") if isinstance(res.get("raw_result"), dict) else None)
                                if content:
                                    # Add the actual content summary
                                    content_snippet = content[:300].replace("\n", " ")
                                    tool_summaries.append(f"{desc}: {content_snippet}...")
                                else:
                                    tool_summaries.append(desc)
                            else:
                                tool_summaries.append(desc)
                    
                    if tool_summaries:
                        response_text += "\n\n[Tool Execution Log]:\n" + "\n".join(tool_summaries)
                
                return response_text
        except Exception as e:
            # Fallback to legacy if generation fails
            print(f"[RECOVERABLE] Probabilistic generation failed: {e}")

        # 4. Legacy Deterministic Fallback
        role_prefixes = {
            "analyst": "Here's what I concluded:",
            "investigator": "My best read on this is:",
            "observer": "From the patterns I see:",
            "default": "Here's my response:"
        }
        prefix = role_prefixes.get(event.role, role_prefixes["default"])

        lines = [f"[{event.role}/{event.emotional_tone}] {prefix} {event.summary}"]

        if event.explanations:
            lines.append("Most plausible causes:")
            for e in event.explanations[:3]:
                lines.append(f"- {e}")

        if event.actions_taken:
            lines.append("I also took the following system actions:")
            for a in event.actions_taken:
                lines.append(f"- {a.get('description', str(a))}")

        return "\n".join(lines)
