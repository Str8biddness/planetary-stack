"""
Aegis Explainer — Natural Language Insight for Synthesus 4.0.

Converts cold reasoning traces (JSON) into human-readable narratives.
Uses a generative logic approach to ensure explanations are dynamic and context-aware.
"""

import logging
import random
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

class AegisExplainer:
    """
    Translates security logic into professional narratives.
    """
    def __init__(self):
        self.personas = {
            "officer": {
                "prefixes": ["My analysis shows", "I have determined that", "Current telemetry indicates"],
                "transitions": ["which subsequently led to", "resulting in", "followed immediately by"],
                "conclusions": ["This pattern is consistent with", "I am highly confident this represents", "All indicators point to"]
            }
        }

    def narrate_incident(self, incident: Dict[str, Any]) -> str:
        """
        Generates a natural language summary of a security incident.
        """
        confidence = incident.get("confidence", 0.0) * 100
        causal_chain = incident.get("causal_chain", [])
        primary = incident.get("primary_alert", {})
        
        # 1. Opening
        persona = self.personas["officer"]
        opening = random.choice(persona["prefixes"])
        
        # 2. Describing the Root Cause
        root_cause = primary.get("source", "an unknown source")
        root_desc = primary.get("title", "suspicious activity")
        
        narrative = f"{opening} a threat originating from {root_cause} ({root_desc}). "
        
        # 3. Walking the Causal Chain
        if causal_chain:
            chain_desc = []
            for link in causal_chain:
                # "source -> target"
                parts = link.split(" -> ")
                if len(parts) == 2:
                    chain_desc.append(f"the {parts[0]} triggered a {parts[1]} event")
            
            narrative += "I observed that " + ", ".join(chain_desc) + ". "
        
        # 4. Conclusion & Confidence
        conclusion = random.choice(persona["conclusions"])
        narrative += f"{conclusion} a high-confidence attack vector. "
        narrative += f"My Bayesian engine has verified this threat with {confidence:.1f}% certainty."
        
        return narrative

    def explain_remediation(self, action: str, result: str, status: str) -> str:
        """
        Explains why an autonomous action was taken or blocked.
        """
        if status == "success":
            return f"I have successfully executed '{action}' to neutralize the threat. {result}"
        elif status == "blocked":
            return f"I attempted to execute '{action}', but I was stopped by your safety policies. Reason: {result}"
        else:
            return f"An attempt to remediate via '{action}' failed. Error: {result}"
