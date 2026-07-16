"""
SecurityGuardrails — Policy enforcement and action validation for Synthesus 4.0.

Uses symbolic logic to ensure that autonomous security actions comply with
predefined safety and business rules.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

class SymbolicReasoner:
    """
    Python implementation of zo::SymbolicReasoner.
    Handles simple propositional logic and rule enforcement.
    """
    def __init__(self):
        self.facts = set()
        self.rules = []  # List of (antecedents, consequent)

    def add_fact(self, fact: str):
        self.facts.add(fact)

    def add_rule(self, antecedents: List[str], consequent: str):
        self.rules.append((set(antecedents), consequent))

    def infer(self):
        """Simple forward chaining."""
        changed = True
        while changed:
            changed = False
            for antecedents, consequent in self.rules:
                if consequent not in self.facts and antecedents.issubset(self.facts):
                    self.facts.add(consequent)
                    changed = True

    def check(self, condition: str) -> bool:
        self.infer()
        return condition in self.facts

class SecurityGuardrails:
    """
    Enforces security policies using symbolic reasoning.
    """
    def __init__(self):
        self.reasoner = SymbolicReasoner()
        self._init_default_policies()

    def _init_default_policies(self):
        """Define core safety rules."""
        # Rule: If it's a critical system AND a high-confidence threat, isolation is RECOMMENDED.
        self.reasoner.add_rule(["is_critical_system", "high_confidence_threat"], "recommend_isolation")
        
        # Rule: If an action is 'reboot' AND it's a 'production' environment, it's UNSAFE without confirmation.
        self.reasoner.add_rule(["action_reboot", "env_production"], "requires_confirmation")
        
        # Rule: If threat source is 'external' AND confidence is 'low', DO NOT block.
        self.reasoner.add_rule(["source_external", "low_confidence"], "suppress_block")

    def validate_action(self, action: str, context: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validates if a security action is safe to execute.
        Returns (is_safe, reason).
        """
        # Reset reasoner for this validation
        self.reasoner.facts = set()
        
        # Inject context as facts
        for key, value in context.items():
            if isinstance(value, bool) and value:
                self.reasoner.add_fact(key)
            elif isinstance(value, str):
                self.reasoner.add_fact(f"{key}_{value}")
        
        self.reasoner.add_fact(f"action_{action}")

        # Run inference
        self.reasoner.infer()

        if self.reasoner.check("requires_confirmation"):
            return False, f"Action '{action}' requires manual confirmation in this context."
        
        if self.reasoner.check("suppress_block") and action == "block_ip":
            return False, "IP blocking suppressed due to low confidence in external threat."

        return True, "Action validated by symbolic guardrails."

    def get_recommendation(self, context: Dict[str, Any]) -> Optional[str]:
        """Suggests an action based on policies."""
        self.reasoner.facts = set()
        for key, value in context.items():
            if isinstance(value, bool) and value:
                self.reasoner.add_fact(key)
            elif isinstance(value, str):
                self.reasoner.add_fact(f"{key}_{value}")
        
        self.reasoner.infer()

        if self.reasoner.check("recommend_isolation"):
            return "isolate_system"
        
        return None
