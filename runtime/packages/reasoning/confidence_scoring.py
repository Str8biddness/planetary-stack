"""
PPBRS Confidence Scoring Module
Multi-factor confidence calculation with decay and normalization.
"""
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import math


class ConfidenceSource(Enum):
    """Sources of evidence for confidence scoring.
    
    Attributes:
        PATTERN_MATCH: Confidence derived from pattern matching score
        CONTEXTUAL: Confidence from contextual factors (relevance, recency, etc.)
        EVIDENCE: Confidence boost from supporting evidence
        CHAIN_INFERENCE: Confidence from multi-step reasoning chains
        RULE_ACTIVATION: Confidence from activated rules
    """
    PATTERN_MATCH = "pattern_match"
    CONTEXTUAL = "context"
    EVIDENCE = "evidence"
    CHAIN_INFERENCE = "chain_inference"
    RULE_ACTIVATION = "rule_activation"


@dataclass
class ConfidenceComponent:
    """A single component contributing to overall confidence score.
    
    Attributes:
        source: The ConfidenceSource enum value identifying the source
        value: The raw confidence value from this source (0.0 to 1.0)
        weight: Multiplier applied to this component (default 1.0)
        decay_factor: Temporal decay factor for over-time degradation
        metadata: Additional metadata about this component
    """
    source: ConfidenceSource
    value: float
    weight: float = 1.0
    decay_factor: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConfidenceScore:
    """Aggregated confidence score from multiple components.
    
    Attributes:
        overall: Final weighted confidence score (0.0 to 1.0)
        components: List of individual ConfidenceComponent instances
        level: Descriptive level string (minimal/low/medium/high/very_high)
        factors: Dictionary of individual factor scores for debugging
    """
    overall: float
    components: List[ConfidenceComponent]
    level: str
    factors: Dict[str, float] = field(default_factory=dict)


class ConfidenceScorer:
    """
    Calculate multi-factor confidence scores with normalization.
    """
    
    def __init__(self, base_threshold: float = 0.3):
        """Initializes the ConfidenceScorer.

        Args:
            base_threshold: The minimum confidence required for reliability. Defaults to 0.3.
        """
        self.base_threshold = base_threshold
        self.history: List[ConfidenceScore] = []
        
    def calculate(self, 
                 pattern_confidence: float,
                 context_factors: Optional[Dict[str, float]] = None,
                 chain_confidences: Optional[List[float]] = None,
                 evidence_boost: float = 0.0) -> ConfidenceScore:
        """Calculates an aggregated confidence score from multiple evidence sources.

        Args:
            pattern_confidence: The confidence score from the initial pattern match.
            context_factors: Optional dictionary of contextual factor scores.
            chain_confidences: Optional list of confidence scores from reasoning chains.
            evidence_boost: An optional additional confidence boost. Defaults to 0.0.

        Returns:
            A ConfidenceScore object containing the final overall score and components.
        """
        context_factors = context_factors or {}
        chain_confidences = chain_confidences or []

        components = []
        weighted_sum = 0.0
        total_weight = 0.0

        pattern_component = ConfidenceComponent(
            source=ConfidenceSource.PATTERN_MATCH,
            value=pattern_confidence,
            weight=1.5,
            metadata={'primary': True}
        )
        components.append(pattern_component)
        weighted_sum += pattern_component.value * pattern_component.weight
        total_weight += pattern_component.weight

        context_total = 0.0
        for factor_name, factor_value in context_factors.items():
            component = ConfidenceComponent(
                source=ConfidenceSource.CONTEXTUAL,
                value=factor_value,
                weight=0.8,
                metadata={'factor': factor_name}
            )
            components.append(component)
            weighted_sum += component.value * component.weight
            total_weight += component.weight
            context_total += factor_value

        chain_avg = 0.0
        if chain_confidences:
            chain_avg = sum(chain_confidences) / len(chain_confidences)
            component = ConfidenceComponent(
                source=ConfidenceSource.CHAIN_INFERENCE,
                value=chain_avg,
                weight=1.2,
                metadata={'chain_count': len(chain_confidences)}
            )
            components.append(component)
            weighted_sum += component.value * component.weight
            total_weight += component.weight

        if evidence_boost > 0:
            component = ConfidenceComponent(
                source=ConfidenceSource.EVIDENCE,
                value=evidence_boost,
                weight=0.5,
                metadata={'boost': True}
            )
            components.append(component)
            weighted_sum += component.value * component.weight
            total_weight += component.weight

        overall = weighted_sum / total_weight if total_weight > 0 else 0.0
        
        overall = self._apply_temporal_decay(overall)
        overall = self._normalize(overall)
        
        level = self._get_level(overall)
        
        factors = {
            'pattern': pattern_confidence,
            'context_avg': context_total / len(context_factors) if context_factors else 0.0,
            'chain_avg': chain_avg,
            'evidence_boost': evidence_boost
        }
        
        return ConfidenceScore(
            overall=overall,
            components=components,
            level=level,
            factors=factors
        )
    
    def _apply_temporal_decay(self, confidence: float) -> float:
        """Applies a minor degradation to extremely high confidence scores to prevent over-certainty.

        Args:
            confidence: The raw input confidence.

        Returns:
            The decayed confidence score.
        """
        if confidence > 0.95:
            return 0.95 + (confidence - 0.95) * 0.5
        return confidence
    
    def _normalize(self, value: float) -> float:
        """Clamps a numeric value between 0.0 and 1.0.

        Args:
            value: The input value.

        Returns:
            The normalized value.
        """
        return max(0.0, min(1.0, value))
    
    def _get_level(self, confidence: float) -> str:
        """Converts a numeric confidence score into a descriptive level string.

        Args:
            confidence: The numeric score to categorize.

        Returns:
            A string (e.g., 'very_high', 'high', 'medium', 'low', 'minimal').
        """
        if confidence >= 0.95:
            return "very_high"
        elif confidence >= 0.8:
            return "high"
        elif confidence >= 0.6:
            return "medium"
        elif confidence >= 0.3:
            return "low"
        return "minimal"
    
    def calculate_entropy(self, scores: List[float]) -> float:
        """Computes the Shannon entropy for a distribution of confidence scores.

        Args:
            scores: A list of numeric confidence values.

        Returns:
            The calculated entropy in bits.
        """
        if not scores:
            return 0.0
        
        total = sum(scores)
        if total == 0:
            return 0.0
        
        probs = [s / total for s in scores]
        entropy = 0.0
        for p in probs:
            if p > 0:
                entropy -= p * math.log2(p)
        return entropy
    
    def is_reliable(self, score: ConfidenceScore, min_components: int = 2) -> bool:
        """Determines if a confidence score is considered reliable based on depth and magnitude.

        Args:
            score: The ConfidenceScore to evaluate.
            min_components: Minimum number of evidence components required. Defaults to 2.

        Returns:
            True if reliable, False otherwise.
        """
        if len(score.components) < min_components:
            return False
        if score.overall < self.base_threshold:
            return False
        return True
    
    def compare(self, score1: ConfidenceScore, score2: ConfidenceScore) -> int:
        """Compares two confidence scores.

        Args:
            score1: The first ConfidenceScore.
            score2: The second ConfidenceScore.

        Returns:
            1 if score1 is higher, -1 if score2 is higher, 0 if equal.
        """
        if score1.overall > score2.overall:
            return 1
        elif score1.overall < score2.overall:
            return -1
        return 0
    
    def merge_scores(self, scores: List[ConfidenceScore]) -> ConfidenceScore:
        """Aggregates multiple ConfidenceScore objects into a single unified result.

        Args:
            scores: List of ConfidenceScore objects to merge.

        Returns:
            A new ConfidenceScore representing the average of the inputs.
        """
        if not scores:
            return ConfidenceScore(overall=0.0, components=[], level="minimal", factors={})
        
        all_components = []
        for s in scores:
            all_components.extend(s.components)
        
        overall_avg = sum(s.overall for s in scores) / len(scores)
        level = self._get_level(overall_avg)
        
        merged_factors = {}
        for key in scores[0].factors:
            vals = [s.factors.get(key, 0.0) for s in scores]
            merged_factors[key] = sum(vals) / len(vals)
        
        return ConfidenceScore(
            overall=overall_avg,
            components=all_components,
            level=level,
            factors=merged_factors
        )
    
    def to_dict(self, score: ConfidenceScore) -> Dict[str, Any]:
        """Converts a ConfidenceScore instance into a plain dictionary representation.

        Args:
            score: The ConfidenceScore to convert.

        Returns:
            A dictionary containing the score's primary data.
        """
        return {
            'overall': score.overall,
            'level': score.level,
            'factors': score.factors,
            'component_count': len(score.components),
            'reliable': self.is_reliable(score)
        }


class BayesianConfidenceUpdater:
    """
    Update confidence scores using Bayesian inference.
    """
    
    def __init__(self, prior_alpha: float = 1.0, prior_beta: float = 1.0):
        """Initializes the BayesianConfidenceUpdater with Beta distribution parameters.

        Args:
            prior_alpha: The initial alpha (success) prior. Defaults to 1.0.
            prior_beta: The initial beta (failure) prior. Defaults to 1.0.
        """
        self.prior_alpha = prior_alpha
        self.prior_beta = prior_beta
        
    def update(self, prior_confidence: float, likelihood: float) -> float:
        """Calculates a posterior confidence score using Bayesian inference.

        Args:
            prior_confidence: The current confidence value.
            likelihood: The likelihood of the new evidence.

        Returns:
            The updated posterior confidence mean.
        """
        alpha = self.prior_alpha + likelihood * 10
        beta = self.prior_beta + (1 - likelihood) * 10
        
        posterior_mean = alpha / (alpha + beta)
        return posterior_mean
    
    def update_from_evidence(self, current_confidence: float, 
                           new_evidence: float, evidence_weight: float = 0.3) -> float:
        """Updates a confidence score based on new evidence using a linear weighted average.

        Args:
            current_confidence: The existing confidence score.
            new_evidence: The new evidence score.
            evidence_weight: The weight assigned to the new evidence. Defaults to 0.3.

        Returns:
            The normalized updated confidence score.
        """
        updated = (1 - evidence_weight) * current_confidence + evidence_weight * new_evidence
        return self._normalize(updated)
    
    def _normalize(self, value: float) -> float:
        """Ensures a confidence value stays within the [0, 1] range.

        Args:
            value: The raw confidence value.

        Returns:
            The normalized confidence.
        """
        return max(0.0, min(1.0, value))
