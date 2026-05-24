from typing import Any, Dict, List, Optional
from .conscious_state import ConsciousState, NarrativeEvent
from cognitive.agent_dispatcher import AgentDispatcher
from .knowledge_cloud import KnowledgeCloud

# Adjust import paths based on actual repo structure
try:
    from cognitive.reasoning.deductive.deductive_engine import AIOSDeductiveModule
    from cognitive.reasoning.inductive.inductive_engine import AIOSInductiveModule
    from cognitive.reasoning.abductive.abductive_engine import AIOSAbductiveModule
except ImportError:
    try:
        from reasoning.deductive_engine import AIOSDeductiveModule
        from reasoning.inductive_engine import AIOSInductiveModule
        from reasoning.abductive_engine import AIOSAbductiveModule
    except ImportError:
        from .dummy_reasons import AIOSDeductiveModule, AIOSInductiveModule, AIOSAbductiveModule


class CognitiveCore:
    """
    Core engine for Right-Hemisphere reasoning tasks.
    Coordinates deductive, inductive, and abductive reasoning modules and manages
    tool dispatching for character-driven interactions.
    """

    def __init__(self):
        """
        Initializes CognitiveCore with specialized reasoning engines and a tool dispatcher.
        """
        self.deductive = AIOSDeductiveModule()
        self.inductive = AIOSInductiveModule()
        self.abductive = AIOSAbductiveModule()
        self.agent_dispatcher = AgentDispatcher()
        self.knowledge_cloud = KnowledgeCloud()

    def classify_intent(self, query: str) -> Dict[str, Any]:
        """
        Analyzes a natural language query to determine the required reasoning mode.

        Args:
            query: The natural language query from the user.

        Returns:
            Dict[str, Any]: A dictionary containing primary/secondary intents and confidence scores.
        """
        query_lower = query.lower()
        scores = {"deductive": 0, "inductive": 0, "abductive": 0, "knowledge": 0}

        # Deductive keywords
        deductive_keywords = ["prove", "show that", "therefore", "implies", "contradiction", "given that"]
        for kw in deductive_keywords:
            if kw in query_lower:
                scores["deductive"] += 1

        # Inductive keywords
        inductive_keywords = ["pattern", "trend", "predict", "likely", "probability", "behavior", "logs", "data"]
        for kw in inductive_keywords:
            if kw in query_lower:
                scores["inductive"] += 1

        # Abductive keywords
        abductive_keywords = ["why", "cause", "caused", "explain", "explanation", "root cause", "symptom", "anomaly"]
        for kw in abductive_keywords:
            if kw in query_lower:
                scores["abductive"] += 1

        # Knowledge keywords
        knowledge_keywords = ["what is", "who is", "tell me about", "history of", "lore", "describe"]
        for kw in knowledge_keywords:
            if kw in query_lower:
                scores["knowledge"] += 1

        primary = max(scores, key=scores.get)
        primary_score = scores[primary]
        secondary = [k for k, v in scores.items() if v >= 0.5 * primary_score and k != primary]

        if all(v == 0 for v in scores.values()):
            if query_lower.startswith("why"):
                primary = "abductive"
            elif any(w in query_lower for w in ["how likely", "chance", "predict"]):
                primary = "inductive"
            else:
                primary = "deductive"
            secondary = []

        return {"primary": primary, "secondary": secondary, "scores": scores}

    def _parse_deductive_query(self, query: str) -> Dict[str, Any]:
        """
        Extracts facts and goals from a query intended for deductive reasoning.

        Args:
            query: The raw natural language query.

        Returns:
            Dict[str, Any]: A dictionary containing extracted 'facts' and the target 'goal'.
        """
        import re
        facts = []
        goal = None

        text = re.sub(r"\s+", " ", query).strip()
        text_lc = text.lower()

        # Simple regex for "Given that ..." facts
        given_match = re.search(r'given that (.+?)(?:then|therefore|does|$)', text, re.IGNORECASE)
        if given_match:
            fact_text = given_match.group(1).strip()
            raw_parts = re.split(r"\b(?:and|or)\b|[,;]", fact_text, flags=re.IGNORECASE)
            facts = [p.strip() for p in raw_parts if p.strip()]

        # Goal extraction
        goal_match = re.search(r'(?:then|therefore)\s+(.+?)(?:\?|\.|$)', text, re.IGNORECASE)
        if goal_match:
            goal = goal_match.group(1).strip()

        if not goal:
            goal_match = re.search(r'(?:does|is it true that|must)\s+(.+?)(?:\?|\.|$)', text, re.IGNORECASE)
            if goal_match:
                goal = goal_match.group(1).strip()

        # Handle "what if" hypotheticals
        m_what_if = re.search(r"what if\s+(.+?)(?:,|\?|\.|$)", text_lc)
        if m_what_if:
            scenario = m_what_if.group(1).strip()
            # Example: "i try to access without authentication"
            if "access" in scenario and "without" in scenario and ("auth" in scenario or "login" in scenario):
                facts.append("user_authenticated_false")
                goal = "system_access_allowed"

        # Improve generic conditional goal extraction
        if goal is None:
            # handle questions like "should they access everything?"
            m_goal_q = re.search(r"(should .+?|can .+?|may .+?)\?", text, re.IGNORECASE)
            if m_goal_q:
                goal = m_goal_q.group(1).strip()

        return {"facts": facts, "goal": goal}

    def _parse_inductive_query(self, query: str) -> Dict[str, Any]:
        """
        Parses a query for inductive reasoning, extracting hints for pattern analysis.

        Args:
            query: The raw natural language query.

        Returns:
            Dict[str, Any]: A dictionary containing hints for inductive processing.
        """
        # For now, just return hint as query
        return {"hint": query}

    def _parse_abductive_query(self, query: str) -> Dict[str, Any]:
        """
        Identifies symptoms and observations for abductive reasoning (diagnosis).

        Args:
            query: The raw natural language query.

        Returns:
            Dict[str, Any]: A dictionary of detected symptoms/observations.
        """
        symptoms = {}
        symptom_words = ["crash", "slowdown", "timeout", "error", "failure", "anomaly", "bug", "issue", "problem", "lag", "freeze", "hang", "latency"]
        query_lower = query.lower()
        for word in symptom_words:
            if word in query_lower:
                symptoms[word] = True
        return {"observations": symptoms}

    def parse_query(self, query: str, intent: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dispatches a query to the appropriate parser based on its classified intent.

        Args:
            query: The raw query string.
            intent: The intent classification result.

        Returns:
            Dict[str, Any]: The parsed representation of the query.
        """
        primary = intent["primary"]
        if primary == "deductive":
            return self._parse_deductive_query(query)
        elif primary == "inductive":
            return self._parse_inductive_query(query)
        elif primary == "abductive":
            return self._parse_abductive_query(query)
        else:
            return {}

    def run_deductive_from_state(self, cs: ConsciousState, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes a deductive reasoning pass using current conscious state and parsed facts.

        Args:
            cs: The current ConsciousState of the character.
            parsed: The parsed query details (facts and goal).

        Returns:
            Dict[str, Any]: The results of the deductive pass, including proof traces.
        """
        # Seed with existing facts
        for fact, value in cs.crystallized.facts.items():
            self.deductive.add_fact(fact, value)

        # Add parsed facts
        for fact in parsed.get("facts", []):
            self.deductive.add_fact(fact, True)

        derived_facts = []
        contradictions = []

        # Forward chain
        self.deductive.forward_chain()

        # Get proof trace
        proof_trace = self.deductive.get_proof_trace()

        # Resolve contradictions
        contradictions = self.deductive.resolve_contradictions()

        goal_proved = False
        goal = parsed.get("goal")
        if goal:
            goal_proved = self.deductive.backward_chain(goal)

        # Update crystallized facts with derived
        for fact in derived_facts:
            cs.crystallized.facts[fact] = True

        return {
            "type": "deductive",
            "facts": parsed.get("facts", []),
            "goal": goal,
            "goal_proved": goal_proved,
            "derived_facts": derived_facts,
            "contradictions": contradictions,
            "proof_trace": proof_trace
        }

    def run_inductive_from_state(self, cs: ConsciousState, system_logs: Optional[List[Dict]] = None, current_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Executes an inductive reasoning pass to detect patterns or trends in logs and state.

        Args:
            cs: The current ConsciousState.
            system_logs: Optional list of log entries for behavior analysis.
            current_state: Optional current system state for prediction.

        Returns:
            Dict[str, Any]: The results of the inductive analysis and predictions.
        """
        analysis = None
        prediction = None

        if system_logs:
            analysis = self.inductive.analyze_system_behavior(system_logs)
            cs.fluid.active_hypotheses.extend(analysis.get("hypotheses", []))

        if current_state:
            prediction = self.inductive.predict_system_behavior(current_state)
            cs.fluid.predictions.update(prediction)

        return {"type": "inductive", "analysis": analysis, "prediction": prediction}

    def run_abductive_from_state(self, cs: ConsciousState, symptoms: Dict[str, Any], system_logs: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """
        Executes an abductive reasoning pass to diagnose potential causes for symptoms.

        Args:
            cs: The current ConsciousState.
            symptoms: A dictionary of detected symptoms.
            system_logs: Optional logs for diagnostic verification.

        Returns:
            Dict[str, Any]: A list of potential explanations and their probabilities.
        """
        explanations = self.abductive.diagnose_system_issue(symptoms, system_logs or [])

        for exp in explanations[:10]:  # Top 10
            hyp = exp.hypothesis
            cs.fluid.active_hypotheses.append(hyp)
            cs.fluid.belief_scores[hyp] = exp.posterior_probability

        return {"type": "abductive", "symptoms": symptoms, "explanations": explanations}

    async def process(self,
                query: str,
                cs: ConsciousState,
                system_logs: Optional[List[Dict]] = None,
                current_state: Optional[Dict[str, Any]] = None,
                character_id: str = "synth") -> ConsciousState:
        """
        The main processing pipeline for CognitiveCore.
        Handles tool use, intent classification, multi-mode reasoning, and state updates.

        Args:
            query: The natural language input query.
            cs: The current conscious state.
            system_logs: Optional logs for context-aware reasoning.
            current_state: Optional state snapshots.
            character_id: The ID of the character processing the query.

        Returns:
            ConsciousState: The updated conscious state after processing.
        """
        
        # Check for tool use
        tool_result = await self.agent_dispatcher.evaluate_and_dispatch(query, character_id=character_id)
        actions_taken = []
        if tool_result:
            actions_taken.append({
                "description": f"Used tool {tool_result['tool']} ({tool_result['action']})",
                "type": "tool_use",
                "tool": tool_result['tool'],
                "action": tool_result['action'],
                "result": tool_result
            })
            # Inject context into query so downstream engines can see it
            context_str = tool_result.get('context', '')[:5000]
            query = f"{query}\n[Context from {tool_result['tool']}: {context_str}]"
            
        intent = self.classify_intent(query)
        parsed = self.parse_query(query, intent)

        # ── Knowledge Cloud Lookup ──
        cloud_results = self.knowledge_cloud.lookup_multi(query, top_k=2)
        if cloud_results:
            for res in cloud_results:
                actions_taken.append({
                    "description": f"Retrieved knowledge: {res['entity_name']}",
                    "type": "knowledge_retrieval",
                    "entity": res['entity_id']
                })

        # Domain-specific adjustments
        domain = cs.fluid.current_domain
        if domain == "sysops":
            # Load SysOps causal rules if not already loaded
            self._load_domain_rules("sysops")
            # Add SysOps warnings to summary
            if intent.get("is_expository"):
                pass  # Handled in expository
            else:
                # Append warning to narrative summary
                pass  # Will be handled in summary

        # Short-circuit expository queries
        if intent.get("is_expository"):
            summary = self._handle_expository(query, cs)
            event = NarrativeEvent(
                t=cs.t,
                query=query,
                engines_used=["expository"],
                summary=summary,
                role="explainer",
                emotional_tone="neutral",
            )
            cs.narrative.timeline.append(event)
            return cs

        primary = intent["primary"]
        secondary = intent["secondary"]
        results: List[Dict[str, Any]] = []
        engines_used: List[str] = []

        if primary == "knowledge" and cloud_results:
            engines_used.append("knowledge_cloud")
            results.append({
                "type": "knowledge",
                "summary": f"Retrieved world lore regarding {', '.join([r['entity_name'] for r in cloud_results])}."
            })

        def run_mode(mode: str):
            if mode == "deductive":
                engines_used.append("deductive")
                results.append(self.run_deductive_from_state(cs, parsed))
            elif mode == "inductive":
                engines_used.append("inductive")
                results.append(self.run_inductive_from_state(cs, system_logs=system_logs,
                                                             current_state=current_state))
            elif mode == "abductive":
                engines_used.append("abductive")
                symptoms = parsed.get("observations", {})
                results.append(self.run_abductive_from_state(cs, symptoms, system_logs=system_logs))

        run_mode(primary)
        for mode in secondary:
            run_mode(mode)

        summary = self._summarize_results(query, results)
        if cloud_results and "knowledge" not in [r["type"] for r in results]:
             summary += f" Also referenced world lore about {cloud_results[0]['entity_name']}."

        # Add domain-specific warnings
        if domain == "sysops" and "recommend" in summary.lower():
            summary += " (Note: This is only a recommendation; no actions will be taken without explicit confirmation.)"

        proof_trace = ""
        explanations_text: List[str] = []
        for r in results:
            if r["type"] == "deductive":
                proof_trace = r.get("proof_trace", "")
            if r["type"] == "abductive":
                for e in r.get("explanations", [])[:5]:
                    explanations_text.append(
                        f"{e.hypothesis} (post={e.posterior_probability:.2f})"
                    )
            if r["type"] == "inductive":
                analysis = r.get("analysis") or {}
                for hyp in analysis.get("hypotheses", []):
                    explanations_text.append(hyp)
            if r["type"] == "knowledge":
                explanations_text.append(r["summary"])

        # Assign role and tone based on intent and outcome
        role = cs.narrative.current_role
        if not role:
            if primary == "deductive":
                role = "analyst"
            elif primary == "inductive":
                role = "observer"
            elif primary == "abductive":
                role = "investigator"
            else:
                role = "default"

        tone = "neutral"
        has_contradictions = any(r.get("contradictions", []) for r in results if r["type"] == "deductive")
        has_many_explanations = any(len(r.get("explanations", [])) > 2 for r in results if r["type"] == "abductive")
        high_beliefs = any(e.posterior_probability > 0.8 for r in results if r["type"] == "abductive" for e in r.get("explanations", []))
        if has_contradictions or "error" in query.lower():
            tone = "concerned"
        elif has_many_explanations and high_beliefs:
            tone = "confident"
        elif not results or all(not r.get("analysis") and not r.get("explanations") for r in results):
            tone = "uncertain"
        else:
            tone = "neutral"

        cs.narrative.current_role = role
        cs.narrative.current_emotional_tone = tone

        # Log hemisphere decisions if present in query
        if query.startswith("[Escalated"):
            escalation_note = query.split("]")[0] + "]"
            actions_taken.append({"description": escalation_note, "type": "escalation"})

        event = NarrativeEvent(
            t=cs.t,
            query=query,
            engines_used=engines_used,
            summary=summary,
            role=role,
            emotional_tone=tone,
            proof_trace=proof_trace,
            explanations=explanations_text,
            actions_taken=actions_taken,
        )
        cs.narrative.timeline.append(event)

        return cs

    def _load_domain_rules(self, domain: str):
        """
        Loads domain-specific reasoning rules into the active engines.

        Args:
            domain: The target domain (e.g., 'sysops', 'gm').
        """
        if domain == "sysops":
            # SysOps rules are already in AIOSAbductiveModule
            # If needed, dynamically add to deductive reasoner
            pass

    def _handle_expository(self, query: str, cs: ConsciousState) -> str:
        """
        Handles queries that ask for general explanations or help rather than active reasoning.

        Args:
            query: The expository query.
            cs: The current state context.

        Returns:
            str: A natural language explanation or guidance response.
        """
        query_lc = query.lower()
        domain = cs.fluid.current_domain
        if domain == "assistant":
            if "plan my day" in query_lc or "organize tasks" in query_lc:
                return "I can help you plan your day by listing your key tasks, estimating time, and ordering them by importance and energy level. I'll also consider patterns from your recent activity."
            elif "help me focus" in query_lc or "overloaded" in query_lc or "focus better" in query_lc:
                return "When you feel overloaded, it usually helps to reduce active contexts. I can suggest which tasks to park, which tabs to close or group, and a small next action to regain momentum."
            elif "set up reminders" in query_lc or "automation" in query_lc:
                return "You've asked for similar actions several times. I can help you define a simple routine or script so future runs are one-click instead of manual."
        elif domain == "gm":
            if "combat strategy" in query_lc or "fight boss" in query_lc:
                return "In combat, assess enemy patterns, use environmental hazards, and coordinate with allies. Focus on kiting, crowd control, and resource management to turn difficult fights into winnable encounters."
            elif "quest help" in query_lc or "stuck on quest" in query_lc:
                return "For quests, break down objectives into smaller tasks, gather intel from NPCs, and look for hidden paths or side objectives. Time pressure often indicates a need to prioritize main quest over side content."
            elif "character build" in query_lc or "skill progression" in query_lc:
                return "Character builds should balance offense, defense, and utility based on your playstyle. Experiment with synergies, but don't neglect core stats. Frustration often signals a need for a tutorial or skill reset."
        elif domain == "legal":
            if "contract review" in query_lc or "review contract" in query_lc:
                return "When reviewing contracts, focus on key clauses like obligations, termination, dispute resolution, and liability limits. Compare with industry standards and consult experts for complex terms."
            elif "liability" in query_lc or "legal risk" in query_lc:
                return "Liability depends on jurisdiction, intent, and foreseeability. Document everything, maintain insurance, and seek professional advice to minimize exposure in potential disputes."
            elif "evidence" in query_lc or "build case" in query_lc:
                return "Strong cases require admissible evidence, witness statements, and expert testimony. Organize chronologically, establish causation, and anticipate counterarguments for robust legal positions."
        elif "dual-hemisphere" in query_lc or "dual hemisphere" in query_lc:
            return "The dual-hemisphere architecture mimics human cognition: the left hemisphere handles fast, pattern-based reasoning like token matching and confidence scoring, while the right hemisphere manages cognitive modules such as emotion, relationships, and context recall. They reconcile via a central ML swarm for efficient, low-latency NPC intelligence."
        elif "core architecture" in query_lc:
            return "Synthesus 2.0 uses a dual-hemisphere system with left for pattern matching and right for cognitive modules, powered by a 458KB ML swarm of specialized micro-models, running entirely on CPU at under 1ms inference."
        else:
            return "That's an interesting question. I'm still learning to explain complex topics clearly—could you rephrase or provide more details?"

    def _summarize_results(self, query: str, results: List[Dict[str, Any]]) -> str:
        """
        Consolidates results from multiple reasoning passes into a single summary.

        Args:
            query: The original input query.
            results: A list of results from different reasoning modes.

        Returns:
            str: A natural language summary of the reasoning outcomes.
        """
        summaries = []
        for r in results:
            if r["type"] == "deductive":
                goal = r.get("goal", "unknown")
                if goal == "unknown":
                    summaries.append("Analyzed your question but no explicit logical goal was provided.")
                else:
                    proved = "proved" if r.get("goal_proved") else "not proved"
                    summaries.append(f"Goal '{goal}' {proved}, derived {len(r.get('derived_facts', []))} facts.")
            elif r["type"] == "inductive":
                analysis = r.get("analysis", {})
                n_patterns = len(analysis.get("patterns", [])) if analysis else 0
                summaries.append(f"Detected {n_patterns} patterns in system behavior.")
            elif r["type"] == "abductive":
                n_exp = len(r.get("explanations", []))
                summaries.append(f"Generated {n_exp} explanations for symptoms.")
        return " ".join(summaries) if summaries else "No significant results."
