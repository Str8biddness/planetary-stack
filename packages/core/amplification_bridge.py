# core/amplification_bridge.py
# AIVM VEAI Loop Integration - Connects AmplificationPlane signals to VEAI Trainer
# Enables organ promotion/demotion based on amplification metrics and performance

from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
import asyncio

@dataclass
class AmplificationSignal:
    """Signal from AmplificationPlane for VEAI learning."""
    session_id: str
    domain: str
    phase: str  # 'intake', 'planning', 'output'
    timestamp: datetime

    # Triad scores from amplification
    risk_score: float
    confidence_margin: float
    attention_sensitivity: float

    # Execution recommendation
    execution_recommendation: str  # 'PROCEED', 'REQUEST_CONFIRMATION', 'HALT'

    # Organ performance metrics
    organ_scores: Dict[str, float]  # organ_type -> score

    # Action taken and outcome
    chosen_action: Optional[str] = None
    action_outcome: Optional[str] = None  # 'success', 'failure', 'pending'

    # Additional context
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class OrganPerformanceMetrics:
    """Aggregated performance metrics for an ML organ."""
    organ_type: str
    domain: str
    total_calls: int = 0
    successful_predictions: int = 0
    failed_predictions: int = 0
    avg_confidence: float = 0.0
    avg_risk_score: float = 0.0
    promotion_score: float = 0.5  # 0-1, higher is better

class AmplificationBridge:
    """
    Bridge between AmplificationPlane and VEAI Trainer.
    Collects amplification signals, aggregates organ performance,
    and triggers organ promotion/demotion.
    """

    def __init__(self, synthesus_master, veai_trainer=None):
        self.master = synthesus_master
        self.trainer = veai_trainer
        self.signals: List[AmplificationSignal] = []
        self.organ_metrics: Dict[str, OrganPerformanceMetrics] = {}
        self.signal_handlers: List[Callable[[AmplificationSignal], None]] = []
        self._running = False

        # Thresholds for organ promotion/demotion
        self.promotion_threshold = 0.8
        self.demotion_threshold = 0.3
        self.min_samples_for_decision = 10

    def register_signal_handler(self, handler: Callable[[AmplificationSignal], None]):
        """Register a callback for new amplification signals."""
        self.signal_handlers.append(handler)

    def emit_signal(self, signal: AmplificationSignal):
        """Emit an amplification signal to all handlers."""
        self.signals.append(signal)

        # Update organ metrics
        self._update_organ_metrics(signal)

        # Call registered handlers
        for handler in self.signal_handlers:
            try:
                handler(signal)
            except Exception as e:
                print(f"Signal handler error: {e}")

        # Trigger learning if threshold reached
        self._check_learning_triggers(signal)

    def _update_organ_metrics(self, signal: AmplificationSignal):
        """Update aggregated metrics for organs based on signal."""
        for organ_type, score in signal.organ_scores.items():
            key = f"{signal.domain}:{organ_type}"

            if key not in self.organ_metrics:
                self.organ_metrics[key] = OrganPerformanceMetrics(
                    organ_type=organ_type,
                    domain=signal.domain
                )

            metrics = self.organ_metrics[key]
            metrics.total_calls += 1

            # Update confidence and risk tracking
            alpha = 0.1  # Exponential moving average factor
            metrics.avg_confidence = (1 - alpha) * metrics.avg_confidence + alpha * signal.confidence_margin
            metrics.avg_risk_score = (1 - alpha) * metrics.avg_risk_score + alpha * signal.risk_score

            # Track success based on outcome
            if signal.action_outcome == 'success':
                metrics.successful_predictions += 1
            elif signal.action_outcome == 'failure':
                metrics.failed_predictions += 1

            # Update promotion score based on multiple factors
            success_rate = metrics.successful_predictions / max(1, metrics.successful_predictions + metrics.failed_predictions)
            confidence_factor = signal.confidence_margin
            risk_factor = 1 - signal.risk_score  # Lower risk is better

            # Weighted combination
            metrics.promotion_score = 0.4 * success_rate + 0.3 * confidence_factor + 0.3 * risk_factor

    def _check_learning_triggers(self, signal: AmplificationSignal):
        """Check if learning should be triggered based on signal patterns."""
        # Check for repeated halts - may indicate organ issues
        recent_signals = [s for s in self.signals[-20:] if s.domain == signal.domain]
        halt_count = sum(1 for s in recent_signals if s.execution_recommendation == 'HALT')

        if len(recent_signals) >= 10 and halt_count / len(recent_signals) > 0.3:
            # High halt rate - trigger organ review
            self._trigger_organ_review(signal.domain)

    def _trigger_organ_review(self, domain: str):
        """Review organ performance and trigger promotions/demotions."""
        domain_metrics = {k: v for k, v in self.organ_metrics.items() if v.domain == domain}

        for key, metrics in domain_metrics.items():
            if metrics.total_calls < self.min_samples_for_decision:
                continue

            if metrics.promotion_score >= self.promotion_threshold:
                self._promote_organ(metrics)
            elif metrics.promotion_score <= self.demotion_threshold:
                self._demote_organ(metrics)

    def _promote_organ(self, metrics: OrganPerformanceMetrics):
        """Promote an organ to higher autonomy level."""
        print(f"[AmplificationBridge] Promoting {metrics.organ_type} in {metrics.domain} "
              f"(score: {metrics.promotion_score:.2f})")

        # Update autonomy config if available
        if self.master and hasattr(self.master, 'core'):
            try:
                from ..organs.autonomyConfig import AUTO_CONFIG, AutonomyLevel
                domain_config = AUTO_CONFIG.get(metrics.domain)
                if domain_config:
                    # Increase autonomy level if not already at max
                    current_level = domain_config.level
                    if current_level == AutonomyLevel.SUPERVISED:
                        domain_config.level = AutonomyLevel.ASSISTED
                        print(f"[AmplificationBridge] {metrics.domain} autonomy increased to ASSISTED")
                    elif current_level == AutonomyLevel.ASSISTED:
                        domain_config.level = AutonomyLevel.AUTONOMOUS
                        print(f"[AmplificationBridge] {metrics.domain} autonomy increased to AUTONOMOUS")
            except Exception as e:
                print(f"Failed to update autonomy config: {e}")

        # Record promotion event
        self._record_learning_event('organ_promotion', {
            'organ_type': metrics.organ_type,
            'domain': metrics.domain,
            'promotion_score': metrics.promotion_score,
            'timestamp': datetime.now().isoformat()
        })

    def _demote_organ(self, metrics: OrganPerformanceMetrics):
        """Demote an organ to lower autonomy level with more oversight."""
        print(f"[AmplificationBridge] Demoting {metrics.organ_type} in {metrics.domain} "
              f"(score: {metrics.promotion_score:.2f})")

        # Update autonomy config if available
        if self.master and hasattr(self.master, 'core'):
            try:
                from ..organs.autonomyConfig import AUTO_CONFIG, AutonomyLevel
                domain_config = AUTO_CONFIG.get(metrics.domain)
                if domain_config:
                    # Decrease autonomy level if not already at minimum
                    current_level = domain_config.level
                    if current_level == AutonomyLevel.AUTONOMOUS:
                        domain_config.level = AutonomyLevel.ASSISTED
                        print(f"[AmplificationBridge] {metrics.domain} autonomy decreased to ASSISTED")
                    elif current_level == AutonomyLevel.ASSISTED:
                        domain_config.level = AutonomyLevel.SUPERVISED
                        print(f"[AmplificationBridge] {metrics.domain} autonomy decreased to SUPERVISED")
            except Exception as e:
                print(f"Failed to update autonomy config: {e}")

        # Record demotion event
        self._record_learning_event('organ_demotion', {
            'organ_type': metrics.organ_type,
            'domain': metrics.domain,
            'promotion_score': metrics.promotion_score,
            'timestamp': datetime.now().isoformat()
        })

    def _record_learning_event(self, event_type: str, data: Dict[str, Any]):
        """Record a learning event to the master's state."""
        if self.master and hasattr(self.master, 'state'):
            self.master.state.narrative.add_event(
                event_type=event_type,
                description=f"Learning event: {event_type}",
                metadata=data
            )

    def get_organ_health_report(self, domain: Optional[str] = None) -> Dict[str, Any]:
        """Get a health report for organs."""
        if domain:
            metrics = {k: v for k, v in self.organ_metrics.items() if v.domain == domain}
        else:
            metrics = self.organ_metrics

        report = {}
        for key, m in metrics.items():
            report[key] = {
                'organ_type': m.organ_type,
                'domain': m.domain,
                'total_calls': m.total_calls,
                'success_rate': m.successful_predictions / max(1, m.successful_predictions + m.failed_predictions),
                'avg_confidence': m.avg_confidence,
                'avg_risk_score': m.avg_risk_score,
                'promotion_score': m.promotion_score,
                'status': 'healthy' if m.promotion_score > 0.6 else 'degraded' if m.promotion_score > 0.4 else 'critical'
            }

        return report

    def export_signals_to_trainer(self) -> List[Dict[str, Any]]:
        """Export recent signals as training data for VEAI trainer."""
        # Convert signals to narrative events for trainer consumption
        training_data = []
        for signal in self.signals[-100:]:  # Last 100 signals
            training_data.append({
                'timestamp': signal.timestamp.isoformat(),
                'domain': signal.domain,
                'phase': signal.phase,
                'risk_score': signal.risk_score,
                'confidence_margin': signal.confidence_margin,
                'attention_sensitivity': signal.attention_sensitivity,
                'execution_recommendation': signal.execution_recommendation,
                'organ_scores': signal.organ_scores,
                'action_outcome': signal.action_outcome,
            })
        return training_data

    def start(self):
        """Start the amplification bridge monitoring."""
        self._running = True
        print("[AmplificationBridge] Started monitoring amplification signals")

    def stop(self):
        """Stop the amplification bridge."""
        self._running = False
        print("[AmplificationBridge] Stopped")

    def get_stats(self) -> Dict[str, Any]:
        """Get bridge statistics."""
        return {
            'total_signals': len(self.signals),
            'tracked_organs': len(self.organ_metrics),
            'running': self._running,
            'handlers_registered': len(self.signal_handlers),
            'signals_last_hour': len([s for s in self.signals if (datetime.now() - s.timestamp).seconds < 3600])
        }
