"""
SecurityReasoner — Advanced threat analysis and alert correlation for Synthesus 4.0.

Implements Causal Inference and Bayesian Reasoning to group related alerts
into incidents and calculate threat confidence scores.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

@dataclass
class CausalEdge:
    effect: str
    strength: float

@dataclass
class CausalVar:
    name: str
    value: float = 0.0

@dataclass
class CausalResult:
    target: str
    effect_size: float
    trace: str

class CausalReasoner:
    """Python implementation of zo::CausalReasoner."""
    def __init__(self):
        self.vars: Dict[str, CausalVar] = {}
        self.edges: Dict[str, List[CausalEdge]] = {}

    def add_variable(self, name: str, value: float = 0.0):
        self.vars[name] = CausalVar(name, value)

    def add_edge(self, cause: str, effect: str, strength: float):
        if cause not in self.edges:
            self.edges[cause] = []
        self.edges[cause].append(CausalEdge(effect, strength))

    def propagate(self, target: str, interventions: Dict[str, float]) -> float:
        total = 0.0
        for cause, eflist in self.edges.items():
            for edge in eflist:
                if edge.effect == target:
                    cv = interventions.get(cause, self.vars.get(cause, CausalVar(cause, 0.0)).value)
                    total += cv * edge.strength
        return total

    def do_intervention(self, var: str, value: float, target: str) -> CausalResult:
        interventions = {var: value}
        effect = self.propagate(target, interventions)
        trace = f"do({var}={value}) -> {target}={effect:.2f}"
        return CausalResult(target, effect, trace)

class BayesianReasoner:
    """Python implementation of zo::BayesianReasoner."""
    def __init__(self):
        self.nodes: Dict[str, float] = {}  # node_name -> prior
        self.likelihoods: Dict[str, Dict[str, float]] = {}  # hypothesis -> {evidence -> p}

    def add_node(self, name: str, prior: float = 0.5):
        self.nodes[name] = prior

    def set_likelihood(self, hypothesis: str, evidence: str, p: float):
        if hypothesis not in self.likelihoods:
            self.likelihoods[hypothesis] = {}
        self.likelihoods[hypothesis][evidence] = p

    def update(self, prior: float, likelihood: float, marginal: float = 0.5) -> float:
        if marginal > 0:
            return (likelihood * prior) / marginal
        return prior

    def infer(self, hypothesis: str, evidence_list: List[str]) -> Tuple[float, str]:
        prior = self.nodes.get(hypothesis, 0.5)
        combined = prior
        ev_used = []
        
        l_map = self.likelihoods.get(hypothesis, {})
        for e in evidence_list:
            if e in l_map:
                combined = self.update(combined, l_map[e])
                ev_used.append(e)
        
        return min(1.0, combined), ", ".join(ev_used)

class SecurityReasoner:
    """
    High-level security reasoning orchestrator.
    Combines Causal and Bayesian reasoning to analyze alerts.
    """
    def __init__(self):
        self.causal = CausalReasoner()
        self.bayesian = BayesianReasoner()
        self._init_security_knowledge()

    def _init_security_knowledge(self):
        """Seed the reasoner with common security patterns."""
        # --- Causal Model ---
        # Edges: cause -> effect (strength)
        self.causal.add_edge("baseliner", "unauthorized_access", 0.7)
        self.causal.add_edge("unauthorized_access", "immune_system", 0.9)
        self.causal.add_edge("anomalous_port", "unauthorized_access", 0.7)
        self.causal.add_edge("unauthorized_access", "file_integrity_violation", 0.9)
        self.causal.add_edge("brute_force_simulation", "account_lockout", 0.6)
        self.causal.add_edge("ghostnet", "immune_system", 0.5)

        # --- Bayesian Model ---
        # Priors
        self.bayesian.add_node("intrusion_attempt", 0.1)
        self.bayesian.add_node("insider_threat", 0.05)
        self.bayesian.add_node("data_exfiltration", 0.02)
        
        # Likelihoods: hypothesis -> evidence (p)
        # Intrusion Attempt
        self.bayesian.set_likelihood("intrusion_attempt", "baseliner", 0.8)
        self.bayesian.set_likelihood("intrusion_attempt", "unauthorized_access", 0.9)
        self.bayesian.set_likelihood("intrusion_attempt", "immune_system", 0.95)
        self.bayesian.set_likelihood("intrusion_attempt", "anomalous_port", 0.8)
        self.bayesian.set_likelihood("intrusion_attempt", "brute_force", 0.9)
        self.bayesian.set_likelihood("intrusion_attempt", "ghostnet", 0.6)
        
        # Data Exfiltration
        self.bayesian.set_likelihood("data_exfiltration", "unusual_outbound_traffic", 0.9)
        self.bayesian.set_likelihood("data_exfiltration", "file_integrity_violation", 0.4)

    def correlate_alerts(self, alerts: List[Dict]) -> List[Dict]:
        """
        Group related alerts using causal links.
        Returns a list of 'Incidents' containing correlated alerts.
        """
        if not alerts:
            return []

        # Sort by ID (chronological) to ensure causes are processed before effects
        alerts = sorted(alerts, key=lambda a: a.get("id", 0))

        incidents = []
        used_alert_ids = set()

        for i, first_alert in enumerate(alerts):
            if first_alert.get("id") in used_alert_ids:
                continue
            
            current_incident = {
                "id": f"INC-{first_alert.get('id')}",
                "primary_alert": first_alert,
                "correlated_alerts": [],
                "causal_chain": [],
                "confidence": 0.0
            }
            used_alert_ids.add(first_alert.get("id"))

            # Iterative search for all linked alerts in the chain
            to_process = [first_alert]
            while to_process:
                parent = to_process.pop(0)
                parent_source = parent.get("source", "").lower()
                
                for other in alerts:
                    other_id = other.get("id")
                    if other_id in used_alert_ids:
                        continue
                    
                    target_type = other.get("source", "").lower()
                    
                    # Check if parent -> other
                    is_linked = False
                    for edge in self.causal.edges.get(parent_source, []):
                        if edge.effect == target_type:
                            is_linked = True
                            current_incident["causal_chain"].append(f"{parent_source} -> {target_type}")
                            break
                    
                    if is_linked:
                        current_incident["correlated_alerts"].append(other)
                        used_alert_ids.add(other_id)
                        to_process.append(other)
            
            # Calculate Bayesian confidence for the incident
            evidence = [first_alert.get("source", "").lower()] + [a.get("source", "").lower() for a in current_incident["correlated_alerts"]]
            conf, ev_used = self.bayesian.infer("intrusion_attempt", evidence)
            current_incident["confidence"] = conf
            
            incidents.append(current_incident)

        return incidents

    def analyze_threat(self, alerts: List[Dict]) -> Dict:
        """Provide a deep analysis of a set of alerts."""
        incidents = self.correlate_alerts(alerts)
        
        summary = {
            "incident_count": len(incidents),
            "top_threat": None,
            "max_confidence": 0.0,
            "analysis_trace": []
        }

        for inc in incidents:
            if inc["confidence"] > summary["max_confidence"]:
                summary["max_confidence"] = inc["confidence"]
                summary["top_threat"] = inc
            
            if inc["causal_chain"]:
                summary["analysis_trace"].append(f"Incident {inc['id']}: Detected causal link {' and '.join(inc['causal_chain'])}")

        return summary
