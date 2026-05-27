"""
PPBRS - Probabilistic Pattern-Based Reasoning System
Synthesus Core Reasoning Module
"""
from .pattern_classifier import PatternClassifier, Pattern, ClassificationResult, ConfidenceLevel
from .reasoning_chain import (
    ReasoningChainBuilder, 
    ReasoningChain, 
    ReasoningStep, 
    ReasoningType,
    WeightedRuleEvaluator,
    ContextAwareReasoningPipeline
)
from .confidence_scoring import (
    ConfidenceScorer, 
    ConfidenceScore, 
    ConfidenceComponent,
    ConfidenceSource,
    BayesianConfidenceUpdater
)
from .rule_to_action import (
    RuleToActionMapper,
    Rule,
    Action,
    ActionType,
    MappingResult,
    ActionSequenceBuilder
)
from .pattern_extractor import (
    RegexPatternExtractor,
    NGramPatternExtractor,
    TFIDFPatternExtractor,
    ContextualPatternExtractor,
    CompositePatternExtractor,
    ExtractionResult
)
from .multi_step_reasoning import (
    MultiStepReasoningChain,
    ReasoningChainOptimizer,
    FallbackReasoningEngine,
    ReasoningNode,
    ReasoningGraph,
    Hypothesis,
    HypothesisStatus,
    ReasoningStrategy
)
from .chal import (
    Checkpoint,
    CognitiveTask,
    ExecutionPlan,
    ModuleMessage,
    TelemetryRecord,
    build_ppbrs_firmware_signal,
)

__all__ = [
    'PatternClassifier',
    'Pattern',
    'ClassificationResult',
    'ConfidenceLevel',
    'ReasoningChainBuilder',
    'ReasoningChain',
    'ReasoningStep',
    'ReasoningType',
    'WeightedRuleEvaluator',
    'ContextAwareReasoningPipeline',
    'ConfidenceScorer',
    'ConfidenceScore',
    'ConfidenceComponent',
    'ConfidenceSource',
    'BayesianConfidenceUpdater',
    'RuleToActionMapper',
    'Rule',
    'Action',
    'ActionType',
    'MappingResult',
    'ActionSequenceBuilder',
    'RegexPatternExtractor',
    'NGramPatternExtractor',
    'TFIDFPatternExtractor',
    'ContextualPatternExtractor',
    'CompositePatternExtractor',
    'ExtractionResult',
    'MultiStepReasoningChain',
    'ReasoningChainOptimizer',
    'FallbackReasoningEngine',
    'ReasoningNode',
    'ReasoningGraph',
    'Hypothesis',
    'HypothesisStatus',
    'ReasoningStrategy',
    'CognitiveTask',
    'ExecutionPlan',
    'ModuleMessage',
    'Checkpoint',
    'TelemetryRecord',
    'build_ppbrs_firmware_signal',
]

__version__ = '1.1.0'
