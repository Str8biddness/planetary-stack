"""
Conversational Narrator — Natural Language Reasoning Explanations for Synthesus.

Converts quad-brain reasoning traces into human-readable narratives.
This is the "Aegis Voice" for general conversation, explaining HOW the AI thinks.
"""

import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ReasoningStep:
    """A single step in the reasoning process."""
    hemisphere: str  # MC, NS, Psi, VO, or Integration
    action: str
    input_data: Any
    output_data: Any
    confidence: float
    timestamp: datetime


class ConversationalNarrator:
    """
    Translates quad-brain reasoning traces into conversational explanations.
    
    Unlike AegisExplainer (security-focused), this handles general queries:
    - Knowledge retrieval reasoning
    - Confidence calibration explanations  
    - Uncertainty acknowledgment
    - Source attribution
    """
    
    def __init__(self, persona: str = "analytical"):
        self.persona = persona
        self.templates = {
            "analytical": {
                "intros": [
                    "Let me think through this step by step...",
                    "I'll analyze this by considering several factors...",
                    "Here's how I'm approaching your question...",
                ],
                "knowledge_lookup": [
                    "I searched my knowledge base for '{query}' and found {count} relevant items.",
                    "Looking up information about {topic}... I have {count} sources.",
                    "Retrieving facts on {topic} from {count} reference points.",
                ],
                "high_confidence": [
                    "I'm quite confident about this ({confidence:.0%} certainty) because {reason}.",
                    "With {confidence:.0%} confidence, I can say that {conclusion}.",
                ],
                "medium_confidence": [
                    "I'm moderately confident ({confidence:.0%})—{reason}, but {caveat}.",
                    "This seems likely ({confidence:.0%}), though {caveat}.",
                ],
                "low_confidence": [
                    "I'm uncertain about this ({confidence:.0%})—{reason}.",
                    "I should note my confidence is only {confidence:.0%} because {reason}.",
                ],
                "uncertainty": [
                    "I don't have enough information to answer this confidently.",
                    "I'm not sure about this aspect—I'd need more data.",
                ],
                "transitions": [
                    "Additionally,",
                    "Furthermore,",
                    "Also,",
                    "Next,",
                ],
                "conclusions": [
                    "Based on this analysis,",
                    "Putting this together,",
                    "In conclusion,",
                ],
                "knowledge_routing": {
                    "wikipedia": "I consulted Wikipedia for established facts on this topic.",
                    "web_search": "I searched the web for current information.",
                    "document_store": "I referenced the uploaded documents you provided.",
                    "knowledge_cloud": "I checked my knowledge cloud for related context.",
                    "distillation_rag": "I used a distilled neural model to analyze this complex topic in depth.",
                    "merged": "I combined information from multiple sources to give you the best answer.",
                },
                "source_attribution": [
                    "My answer draws from: {sources}.",
                    "I found this information in: {sources}.",
                    "Sources consulted: {sources}.",
                ],
            },
            "friendly": {
                "intros": [
                    "Great question! Let me work through this...",
                    "Interesting! Here's what I'm thinking...",
                    "Let me break this down for you...",
                ],
                "knowledge_lookup": [
                    "So, I looked up '{query}' and found {count} things that might help!",
                    "I searched my memory for {topic}—got {count} results.",
                ],
                "high_confidence": [
                    "I'm pretty sure about this ({confidence:.0%}) because {reason}!",
                    "With {confidence:.0%} confidence, I'd say {conclusion}.",
                ],
                "medium_confidence": [
                    "I'm somewhat confident ({confidence:.0%})—{reason}, but keep in mind {caveat}.",
                    "This feels about {confidence:.0%} right, though {caveat}.",
                ],
                "low_confidence": [
                    "Honestly, I'm not too sure ({confidence:.0%})—{reason}.",
                    "I'd say I'm only {confidence:.0%} confident here because {reason}.",
                ],
                "uncertainty": [
                    "I wish I knew more about this!",
                    "I'm not sure I'd need to research this more.",
                ],
                "transitions": [
                    "Plus,",
                    "Also,",
                    "And,",
                ],
                "conclusions": [
                    "So putting it all together,",
                    "All in all,",
                    "So to answer your question,",
                ]
            }
        }
    
    def narrate_reasoning(
        self,
        query: str,
        reasoning_trace: List[ReasoningStep],
        final_answer: str,
        sources: Optional[List[str]] = None,
        overall_confidence: float = 0.0
    ) -> str:
        """
        Generate a natural language narrative of the reasoning process.
        
        Args:
            query: The original user query
            reasoning_trace: List of reasoning steps from quad-brain
            final_answer: The final response
            sources: Optional list of knowledge sources used
            overall_confidence: Overall confidence score (0-1)
            
        Returns:
            A conversational explanation of the reasoning
        """
        import random
        
        tmpl = self.templates.get(self.persona, self.templates["analytical"])
        parts = []
        
        # Introduction
        parts.append(random.choice(tmpl["intros"]))
        
        # Process each reasoning step
        for i, step in enumerate(reasoning_trace):
            narration = self._narrate_step(step, tmpl, i > 0)
            if narration:
                parts.append(narration)
        
        # Source attribution
        if sources:
            source_str = self._format_sources(sources)
            parts.append(f"My answer draws from: {source_str}.")
        
        # Confidence statement
        conf_narration = self._narrate_confidence(overall_confidence, reasoning_trace, tmpl)
        if conf_narration:
            parts.append(conf_narration)
        
        # Conclusion
        parts.append(random.choice(tmpl["conclusions"]) + " " + final_answer)
        
        return "\n\n".join(parts)
    
    def _narrate_step(self, step: ReasoningStep, tmpl: Dict, use_transition: bool) -> Optional[str]:
        """Convert a single reasoning step to natural language."""
        import random
        
        prefix = random.choice(tmpl["transitions"]) if use_transition else ""
        
        if step.hemisphere == "MC":
            return self._narrate_mc_step(step, prefix)
        elif step.hemisphere == "NS":
            return self._narrate_ns_step(step, prefix)
        elif step.hemisphere == "Psi":
            return self._narrate_psi_step(step, prefix)
        elif step.hemisphere == "VO":
            return self._narrate_vo_step(step, prefix)
        elif step.hemisphere == "Knowledge":
            return self._narrate_knowledge_step(step, tmpl, prefix)
        
        return None
    
    def _narrate_mc_step(self, step: ReasoningStep, prefix: str) -> str:
        """Narrate a Policy/Prior hemisphere step."""
        action = step.action
        if "classify" in action.lower():
            intent = step.output_data.get("intent", "unknown")
            conf = step.output_data.get("confidence", 0)
            return f"{prefix} I classified this as a '{intent}' query ({conf:.0%} confidence)."
        elif "route" in action.lower():
            target = step.output_data.get("target", "unknown")
            return f"{prefix} I routed this to the {target} module."
        return f"{prefix} My policy brain evaluated the action path."
    
    def _narrate_ns_step(self, step: ReasoningStep, prefix: str) -> str:
        """Narrate a Risk/Outcome hemisphere step."""
        risk_level = step.output_data.get("risk_level", "unknown")
        concerns = step.output_data.get("concerns", [])
        
        if concerns:
            concern_str = ", ".join(concerns[:2])
            return f"{prefix} My risk analysis flagged: {concern_str} (level: {risk_level})."
        return f"{prefix} Risk assessment indicated {risk_level} concerns."
    
    def _narrate_psi_step(self, step: ReasoningStep, prefix: str) -> str:
        """Narrate an Attention hemisphere step."""
        focus = step.output_data.get("focus_areas", [])
        if focus:
            focus_str = ", ".join(focus[:2])
            return f"{prefix} I focused my attention on: {focus_str}."
        return f"{prefix} I prioritized key elements of your query."
    
    def _narrate_vo_step(self, step: ReasoningStep, prefix: str) -> str:
        """Narrate a Value hemisphere step."""
        values = step.output_data.get("values_considered", [])
        if values:
            val_str = ", ".join(values[:2])
            return f"{prefix} I considered these values: {val_str}."
        return f"{prefix} I evaluated the outcomes against my value system."
    
    def _narrate_knowledge_step(self, step: ReasoningStep, tmpl: Dict, prefix: str) -> str:
        """Narrate a knowledge retrieval step."""
        import random
        
        query = step.input_data.get("query", "this topic")
        count = step.output_data.get("results_count", 0)
        
        template = random.choice(tmpl["knowledge_lookup"])
        return prefix + " " + template.format(query=query, topic=query, count=count)
    
    def _narrate_confidence(
        self,
        confidence: float,
        reasoning_trace: List[ReasoningStep],
        tmpl: Dict
    ) -> Optional[str]:
        """Generate confidence explanation."""
        import random
        
        # Find reasons for confidence level
        if confidence >= 0.8:
            reasons = ["multiple sources corroborate this", "the pattern is clear"]
            template = random.choice(tmpl["high_confidence"])
            return template.format(confidence=confidence, reason=random.choice(reasons), conclusion="")
        elif confidence >= 0.5:
            reasons = ["I have partial information", "the data is somewhat consistent"]
            caveats = ["some uncertainty remains", "context is limited"]
            template = random.choice(tmpl["medium_confidence"])
            return template.format(
                confidence=confidence,
                reason=random.choice(reasons),
                caveat=random.choice(caveats)
            )
        elif confidence > 0:
            reasons = ["information is sparse", "conflicting data exists"]
            template = random.choice(tmpl["low_confidence"])
            return template.format(confidence=confidence, reason=random.choice(reasons))
        else:
            return random.choice(tmpl["uncertainty"])
    
    def _format_sources(self, sources: List[str]) -> str:
        """Format source list for display."""
        if len(sources) == 1:
            return sources[0]
        elif len(sources) == 2:
            return f"{sources[0]} and {sources[1]}"
        else:
            return ", ".join(sources[:-1]) + f", and {sources[-1]}"
    
    def generate_thinking_indicator(self) -> str:
        """Generate a thinking/reasoning indicator."""
        import random
        indicators = [
            "Analyzing...",
            "Processing through Policy hemisphere...",
            "Checking Risk assessment...",
            "Attending to key patterns...",
            "Evaluating values alignment...",
            "Synthesizing quadrants...",
        ]
        return random.choice(indicators)
    
    def narrate_knowledge_routing(
        self,
        query: str,
        routing_decision: str,
        primary_source: str,
        sources_consulted: List[str],
        confidence: float,
    ) -> str:
        """
        Generate a natural language explanation of knowledge routing.
        
        Args:
            query: The original query
            routing_decision: Human-readable routing decision
            primary_source: Primary knowledge source used
            sources_consulted: List of all sources checked
            confidence: Confidence in the retrieved information
            
        Returns:
            Narrative explanation of the knowledge gathering process
        """
        import random
        
        tmpl = self.templates.get(self.persona, self.templates["analytical"])
        routing_tmpl = tmpl.get("knowledge_routing", {})
        
        parts = []
        
        # Add routing explanation
        source_key = primary_source.lower().replace(" ", "_")
        routing_narrative = routing_tmpl.get(
            source_key,
            routing_tmpl.get("merged", f"I searched my knowledge sources for information.")
        )
        parts.append(routing_narrative)
        
        # Add the routing decision detail if analytical persona
        if self.persona == "analytical" and routing_decision:
            parts.append(f"({routing_decision})")
        
        # Add source attribution
        if sources_consulted:
            source_str = self._format_sources(sources_consulted)
            if "source_attribution" in tmpl:
                attr_template = random.choice(tmpl["source_attribution"])
                parts.append(attr_template.format(sources=source_str))
        
        # Add confidence note
        if confidence < 0.5:
            parts.append("I should note that my confidence in this information is moderate—I'd recommend verifying critical details.")
        
        return " ".join(parts)


# Singleton instance
_narrator_instance: Optional[ConversationalNarrator] = None


def get_narrator(persona: str = "analytical") -> ConversationalNarrator:
    """Get or create a narrator instance."""
    global _narrator_instance
    if _narrator_instance is None or _narrator_instance.persona != persona:
        _narrator_instance = ConversationalNarrator(persona)
    return _narrator_instance
