from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import time
import threading

from .conscious_state import ConsciousState, NarrativeEvent
from .cognitive_core import CognitiveCore
from .synthesus_master import SynthesusMaster


@dataclass
class TrainerConfig:
    batch_interval_seconds: int = 60
    max_events_per_batch: int = 200
    min_events_to_train: int = 20
    learning_rate: float = 0.1

    # Rule learning thresholds
    rule_support_min: int = 3          # minimum times seen as pattern
    rule_positive_min: int = 2         # minimum positive feedbacks
    rule_accept_ratio: float = 0.8     # positive / (pos+neg) to confirm
    rule_reject_ratio: float = 0.7     # negative / (pos+neg) to reject
    max_learned_rules: int = 100


@dataclass
class TrainerMetrics:
    total_batches: int = 0
    total_events_processed: int = 0
    last_batch_time: float = 0.0
    avg_belief_delta: float = 0.0
    inductive_models_trained: int = 0


class VEAITrainer:
    def __init__(self,
                 master: SynthesusMaster,
                 config: Optional[TrainerConfig] = None):
        self.master = master
        self.core: CognitiveCore = master.core
        self.config = config or TrainerConfig()
        self.metrics = TrainerMetrics()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        # simple pointer so we don’t re-train on all history every time
        self._last_trained_index: int = 0

    def _collect_training_events(self) -> List[NarrativeEvent]:
        """Collect new narrative events since the last training batch."""
        timeline = self.master.state.narrative.timeline
        if self._last_trained_index >= len(timeline):
            return []

        events = timeline[self._last_trained_index:]
        # Cap by max_events_per_batch
        events = events[: self.config.max_events_per_batch]
        return events

    def run_batch_training(self) -> Dict[str, Any]:
        """
        Run one training batch over recent events:
        - tune abductive priors using feedback/belief scores
        - trigger inductive retraining if enough system logs are present
        """
        events = self._collect_training_events()
        if len(events) < self.config.min_events_to_train:
            return {"status": "skipped", "reason": "not_enough_events"}

        belief_deltas: List[float] = []
        inductive_trains = 0

        # 1) Abductive / explanation-level tuning
        for ev in events:
            # Look for explanations with belief scores
            for expl in ev.explanations:
                hyp = expl.split(" (post=")[0]
                current = self.master.state.fluid.belief_scores.get(hyp)
                if current is None:
                    continue
                # Move domain priors slightly toward this belief
                if hasattr(self.core.abductive, 'explanation_ranker') and hasattr(self.core.abductive.explanation_ranker, 'domain_priors'):
                    for domain, prior in self.core.abductive.explanation_ranker.domain_priors.items():
                        if domain in hyp.lower():
                            target = current
                            delta = (target - prior) * self.config.learning_rate
                            self.core.abductive.explanation_ranker.domain_priors[domain] = max(
                                0.1, min(0.9, prior + delta)
                            )
                            belief_deltas.append(abs(delta))

        # 2) Inductive model retraining (optional, if you have logs)
        logs = self.master.state.crystallized.system_logs
        if len(logs) >= self.config.min_events_to_train:
            analysis = self.core.inductive.analyze_system_behavior(logs)
            self.metrics.inductive_models_trained += 1
            # Propose rules from hypotheses
            for hyp in analysis.get("hypotheses", []):
                self._propose_rule_from_hypothesis(self.master.state, hyp)

        # Update rules from feedback
        self._update_rules_from_feedback(self.master.state)

        # Update metrics and pointer
        self._last_trained_index += len(events)
        self.metrics.total_events_processed += len(events)
        self.metrics.total_batches += 1
        self.metrics.last_batch_time = time.time()
        if belief_deltas:
            self.metrics.avg_belief_delta = sum(belief_deltas) / len(belief_deltas)

    def _propose_rule_from_hypothesis(self, cs, hypothesis: str):
        import re
        # Simple pattern: "If feature=value, then likely outcome ..."
        m = re.match(r"If\s+([a-zA-Z_]+)=([a-zA-Z_]+),?\s+then\s+likely\s+([a-zA-Z_]+)", hypothesis)
        if not m:
            return

        feature, value, outcome = m.groups()
        premise = f"{feature}_{value}"
        conclusion = outcome

        rule_key = f"{premise}=>{conclusion}"
        rules = cs.crystallized.candidate_rules
        if rule_key not in rules:
            rules[rule_key] = {
                "premises": [premise],
                "conclusion": conclusion,
                "source": "inductive_hypothesis",
                "support": 0,
                "positive": 0,
                "negative": 0,
                "status": "proposed",
                "installed": False,
            }
        rules[rule_key]["support"] += 1

    def _update_rules_from_feedback(self, cs):
        cfg = self.config
        rules = cs.crystallized.candidate_rules

        # Count already installed learned rules
        installed_count = sum(1 for r in rules.values() if r.get("installed"))

        for key, rule in rules.items():
            pos = rule["positive"]
            neg = rule["negative"]
            support = rule["support"]
            status = rule["status"]
            total_fb = pos + neg

            if status == "proposed":
                # Only consider rules with enough support and feedback
                if support >= cfg.rule_support_min and total_fb >= cfg.rule_positive_min:
                    ratio = pos / total_fb if total_fb else 0.0
                    if ratio >= cfg.rule_accept_ratio and installed_count < cfg.max_learned_rules:
                        rule["status"] = "confirmed"
                        self._install_learned_rule(cs, key, rule)
                        installed_count += 1
                    elif neg > 0 and (neg / total_fb) >= cfg.rule_reject_ratio:
                        rule["status"] = "rejected"

    def _install_learned_rule(self, cs, key: str, rule: Dict[str, Any]):
        # Install into deductive reasoner
        premises = rule["premises"]
        conclusion = rule["conclusion"]
        name = f"learned_rule_{key}"
        self.core.deductive.reasoner.add_rule(premises, conclusion, name)
        rule["installed"] = True

        # Log into narrative as an action
        if cs.narrative.timeline:
            cs.narrative.timeline[-1].actions_taken.append({
                "action": "install_rule",
                "rule_key": key,
                "premises": premises,
                "conclusion": conclusion,
            })

    def _loop(self):
        """Background training loop — runs in a daemon thread."""
        while self._running:
            try:
                result = self.run_batch_training()
                # Optionally log result somewhere
            except Exception as e:
                # Avoid killing the thread; just continue
                # Optional: log exception
                pass
            time.sleep(self.config.batch_interval_seconds)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0):
        self._running = False
        if self._thread:
            self._thread.join(timeout=timeout)
            self._thread = None
