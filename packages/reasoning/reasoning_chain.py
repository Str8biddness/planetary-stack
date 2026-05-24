"""
PPBRS Reasoning Chain Module
Multi-step reasoning chains with weighted evaluation and fallback logic.
"""
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import re


class ReasoningType(Enum):
    """Types of reasoning for multi-step reasoning chains.
    
    Attributes:
        DIRECT: Direct pattern matching without inference
        CAUSAL: Causal reasoning (cause → effect)
        ABDUCTIVE: Abductive reasoning (observation → best explanation)
        ANALOGICAL: Analogical reasoning (pattern transfer)
        INDUCTIVE: Inductive reasoning (specific → general)
    """
    DIRECT = "direct"
    CAUSAL = "causal"
    ABDUCTIVE = "abductive"
    ANALOGICAL = "analogical"
    INDUCTIVE = "inductive"


@dataclass
class ReasoningStep:
    """A single step in a multi-step reasoning chain.
    
    Attributes:
        step_id: Unique step identifier
        description: Human-readable description of the step
        reasoning_type: Type of reasoning this step employs
        antecedents: List of prior step_ids this step depends on
        consequent: The conclusion or result of this step
        weight: Contribution weight to overall chain confidence
        confidence: Base confidence for this step
        evidence: List of evidence keys required for this step
    """
    step_id: str
    description: str
    reasoning_type: ReasoningType
    antecedents: List[str] = field(default_factory=list)
    consequent: str = ""
    weight: float = 1.0
    confidence: float = 1.0
    evidence: List[str] = field(default_factory=list)


@dataclass
class ReasoningChain:
    """A multi-step reasoning chain with weighted evaluation.
    
    Attributes:
        chain_id: Unique chain identifier
        steps: Ordered list of ReasoningStep instances
        conclusion: Final conclusion of the chain
        overall_confidence: Aggregated confidence across all steps
        tags: Classification tags for the chain
    """
    chain_id: str
    steps: List[ReasoningStep]
    conclusion: str = ""
    overall_confidence: float = 0.0
    tags: List[str] = field(default_factory=list)


@dataclass
class ChainResult:
    """Result of evaluating a reasoning chain.
    
    Attributes:
        chain: The original ReasoningChain
        final_confidence: Computed final confidence after evaluation
        path_taken: List of step_ids in evaluation order with scores
        fallback_used: Whether fallback logic was triggered
        reasoning: Human-readable explanation of the evaluation
    """
    chain: ReasoningChain
    final_confidence: float
    path_taken: List[str]
    fallback_used: bool
    reasoning: str


class ReasoningChainBuilder:
    """
    Build and execute multi-step reasoning chains with fallback logic.
    """
    
    def __init__(self, max_steps: int = 10, min_confidence: float = 0.3):
        """Initializes the ReasoningChainBuilder.

        Args:
            max_steps: Maximum number of steps allowed in a chain. Defaults to 10.
            min_confidence: Threshold below which a step is considered low-confidence. Defaults to 0.3.
        """
        self.max_steps = max_steps
        self.min_confidence = min_confidence
        self.defined_chains: Dict[str, List[ReasoningStep]] = {}
        
    def define_chain(self, chain_id: str, steps: List[ReasoningStep]) -> None:
        """Registers a predefined list of reasoning steps as a named chain.

        Args:
            chain_id: Unique identifier for the chain.
            steps: List of ReasoningStep objects making up the chain.
        """
        self.defined_chains[chain_id] = steps
    
    def build_from_patterns(self, matched_patterns: List[str], 
                            context: Dict[str, Any]) -> List[ReasoningChain]:
        """Generates reasoning chains based on a list of matched pattern identifiers.

        Args:
            matched_patterns: List of pattern IDs that triggered.
            context: Context dictionary used for inference logic.

        Returns:
            A list of instantiated ReasoningChain objects.
        """
        chains = []
        
        for i, pattern_id in enumerate(matched_patterns):
            steps = self._infer_steps(pattern_id, context)
            if steps:
                chain = ReasoningChain(
                    chain_id=f"chain_{pattern_id}_{i}",
                    steps=steps,
                    tags=[pattern_id]
                )
                chains.append(chain)
        
        return chains
    
    def _infer_steps(self, pattern_id: str, context: Dict) -> List[ReasoningStep]:
        """Infers logical reasoning steps from a pattern ID and context.

        Args:
            pattern_id: The ID of the detected pattern.
            context: Current execution context.

        Returns:
            A list of ReasoningStep objects.
        """
        steps = []
        
        step1 = ReasoningStep(
            step_id=f"{pattern_id}_detect",
            description=f"Detected pattern: {pattern_id}",
            reasoning_type=ReasoningType.DIRECT,
            consequent=f"Pattern {pattern_id} is active",
            weight=1.0
        )
        steps.append(step1)
        
        if context.get('requires_context'):
            step2 = ReasoningStep(
                step_id=f"{pattern_id}_context",
                description="Evaluating context requirements",
                reasoning_type=ReasoningType.CAUSAL,
                antecedents=[step1.step_id],
                consequent="Context conditions satisfied",
                weight=0.9
            )
            steps.append(step2)
        
        return steps
    
    def evaluate_chain(self, chain: ReasoningChain, 
                      evidence: Dict[str, Any]) -> ChainResult:
        """Evaluates all steps in a chain against provided evidence.

        Args:
            chain: The ReasoningChain to evaluate.
            evidence: Dictionary of facts/data to validate steps against.

        Returns:
            A ChainResult containing final confidence and execution trace.
        """
        path = []
        total_weight = 0.0
        weighted_sum = 0.0
        fallback_used = False
        
        for step in chain.steps:
            step_confidence = self._evaluate_step(step, evidence)
            
            if step_confidence < self.min_confidence:
                fallback_used = True
                step_confidence *= 0.5
            
            weighted_sum += step_confidence * step.weight
            total_weight += step.weight
            path.append(f"{step.step_id}({step_confidence:.2f})")
        
        final_confidence = weighted_sum / total_weight if total_weight > 0 else 0.0
        
        return ChainResult(
            chain=chain,
            final_confidence=final_confidence,
            path_taken=path,
            fallback_used=fallback_used,
            reasoning=self._build_reasoning(chain, final_confidence)
        )
    
    def _evaluate_step(self, step: ReasoningStep, evidence: Dict) -> float:
        """Calculates the confidence for a single reasoning step based on evidence.

        Args:
            step: The ReasoningStep to evaluate.
            evidence: Dictionary of evidence keys.

        Returns:
            A float representing the confidence score (0.0 to 1.0).
        """
        base_confidence = step.confidence
        
        for evidence_key in step.evidence:
            if evidence_key in evidence:
                base_confidence *= 1.1
                base_confidence = min(base_confidence, 1.0)
        
        return base_confidence
    
    def _build_reasoning(self, chain: ReasoningChain, confidence: float) -> str:
        """Generates a human-readable string explaining the reasoning process.

        Args:
            chain: The ReasoningChain that was evaluated.
            confidence: The final computed confidence.

        Returns:
            A formatted explanation string.
        """
        parts = [f"Chain: {chain.chain_id}"]
        for step in chain.steps:
            parts.append(f"  - {step.step_id}: {step.description}")
        parts.append(f"Final confidence: {confidence:.3f}")
        return "\n".join(parts)
    
    def combine_chains(self, chains: List[ReasoningChain], 
                      weights: Optional[Dict[str, float]] = None) -> ReasoningChain:
        """Merges multiple reasoning chains into a single unified chain.

        Args:
            chains: List of ReasoningChain objects to combine.
            weights: Optional dictionary of weights for each chain.

        Returns:
            A new ReasoningChain containing steps from all inputs.
        """
        if not chains:
            return ReasoningChain(chain_id="empty", steps=[])
        
        if weights is None:
            weights = {c.chain_id: 1.0 for c in chains}
        
        all_steps = []
        for chain in chains:
            all_steps.extend(chain.steps)
        
        combined = ReasoningChain(
            chain_id="combined_" + "_".join(c.chain_id for c in chains),
            steps=all_steps,
            tags=list(set(tag for c in chains for tag in c.tags))
        )
        
        return combined


class WeightedRuleEvaluator:
    """
    Evaluate rules with weighted scoring and threshold-based activation.
    """
    
    def __init__(self, activation_threshold: float = 0.5):
        """Initializes the WeightedRuleEvaluator.

        Args:
            activation_threshold: Minimum weight score for a rule to be considered active.
        """
        self.activation_threshold = activation_threshold
        self.rules: List[Dict[str, Any]] = []
        
    def add_rule(self, condition: Callable[[Dict], bool],
                consequence: Callable[[Dict], Any],
                weight: float = 1.0,
                tags: Optional[List[str]] = None) -> None:
        """Adds a new weighted rule to the evaluator.

        Args:
            condition: Function that returns True if the rule triggers.
            consequence: Function to execute if the rule is selected.
            weight: Relative priority weight. Defaults to 1.0.
            tags: Classification tags.
        """
        self.rules.append({
            'condition': condition,
            'consequence': consequence,
            'weight': weight,
            'tags': tags or [],
            'activation_count': 0
        })
    
    def evaluate(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Evaluates all rules against the context and identifies triggered ones.

        Args:
            context: Dictionary of current state and data.

        Returns:
            A list of dictionaries containing triggered rules and their scores.
        """
        activated = []
        
        for rule in self.rules:
            try:
                if rule['condition'](context):
                    rule['activation_count'] += 1
                    activated.append({
                        'rule': rule,
                        'weight': rule['weight'],
                        'tags': rule['tags']
                    })
            except Exception as e:
                print(f"Rule evaluation error: {e}")
        
        activated.sort(key=lambda x: x['weight'], reverse=True)
        return activated
    
    def apply_top_rule(self, context: Dict[str, Any]) -> Optional[Any]:
        """Selects and executes the highest-weighted triggered rule.

        Args:
            context: Current context for rule evaluation.

        Returns:
            The output of the triggered rule's consequence, or None.
        """
        activated = self.evaluate(context)
        if not activated:
            return None
        
        top_rule = activated[0]['rule']
        return top_rule['consequence'](context)
    
    def apply_fallback(self, context: Dict[str, Any], 
                      fallback_func: Callable[[Dict], Any]) -> Any:
        """Attempts to apply the best rule, falling back to a default function if none trigger.

        Args:
            context: Current context.
            fallback_func: Function to execute if no rules are activated.

        Returns:
            Output from either a rule consequence or the fallback function.
        """
        activated = self.evaluate(context)
        if activated:
            return activated[0]['rule']['consequence'](context)
        return fallback_func(context)


class ContextAwareReasoningPipeline:
    """
    Full pipeline: pattern matching -> reasoning chains -> rule evaluation -> output.
    """
    
    def __init__(self, classifier=None, chain_builder=None, rule_evaluator=None):
        """Initializes the reasoning pipeline with its constituent modules.

        Args:
            classifier: Optional PatternClassifier instance.
            chain_builder: Optional ReasoningChainBuilder instance.
            rule_evaluator: Optional WeightedRuleEvaluator instance.
        """
        from .pattern_classifier import PatternClassifier, ConfidenceLevel
        self.classifier = classifier or PatternClassifier()
        self.chain_builder = chain_builder or ReasoningChainBuilder()
        self.rule_evaluator = rule_evaluator or WeightedRuleEvaluator()
        self.confidence_level = ConfidenceLevel
        
    def process(self, input_str: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Executes the full reasoning process for a given input string.

        Args:
            input_str: The text to process.
            context: Optional context dictionary.

        Returns:
            A dictionary containing status, classification, chains, and the final response.
        """
        context = context or {}
        
        classification = self.classifier.get_best_match(input_str)
        
        if not classification:
            return {
                'status': 'no_match',
                'input': input_str,
                'confidence': 0.0,
                'response': context.get('default_response', 'No matching pattern found.'),
                'reasoning': []
            }
        
        matched_patterns = [classification.pattern_id]
        chains = self.chain_builder.build_from_patterns(matched_patterns, context)
        
        chain_results = []
        for chain in chains:
            result = self.chain_builder.evaluate_chain(chain, context)
            chain_results.append(result)
        
        activated_rules = self.rule_evaluator.evaluate({**context, 'classification': classification})
        
        response = self._build_response(classification, chain_results, activated_rules, context)
        
        return {
            'status': 'success',
            'input': input_str,
            'classification': {
                'pattern_id': classification.pattern_id,
                'confidence': classification.confidence,
                'tags': classification.tags
            },
            'chains': [{
                'chain_id': r.chain.chain_id,
                'confidence': r.final_confidence,
                'fallback_used': r.fallback_used
            } for r in chain_results],
            'rules_activated': len(activated_rules),
            'response': response,
            'reasoning': self._build_pipeline_reasoning(classification, chain_results)
        }
    
    def _build_response(self, classification, chain_results, activated_rules, context):
        """Constructs the final text response based on pipeline outputs.

        Args:
            classification: Result from the classifier.
            chain_results: Results from evaluated reasoning chains.
            activated_rules: List of activated rules.
            context: Execution context.

        Returns:
            A response string.
        """
        pattern = self.classifier.patterns.get(classification.pattern_id)
        if not pattern:
            return context.get('default_response', 'Pattern found but no template.')
        
        response = pattern.response_template
        
        if chain_results:
            best_chain = max(chain_results, key=lambda x: x.final_confidence)
            response = self._apply_fallback_logic(response, best_chain, context)
        
        return response
    
    def _apply_fallback_logic(self, response: str, chain_result: ChainResult, 
                             context: Dict) -> str:
        """Applies fallback modifiers to the response if reasoning confidence is low.

        Args:
            response: The original template response.
            chain_result: Result of the primary reasoning chain.
            context: Execution context for fallback hints.

        Returns:
            The modified response string.
        """
        if chain_result.fallback_used or chain_result.final_confidence < 0.5:
            if '{fallback}' in response:
                return response.replace('{fallback}', context.get('fallback_hint', ''))
            return f"{response} (Note: low confidence reasoning used)"
        return response
    
    def _build_pipeline_reasoning(self, classification, chain_results) -> List[str]:
        """Constructs a detailed execution trace for the pipeline.

        Args:
            classification: Classifier result.
            chain_results: List of chain evaluation results.

        Returns:
            A list of strings explaining each step of the pipeline.
        """
        reasoning = [
            f"Pattern '{classification.pattern_id}' matched with confidence {classification.confidence:.3f}",
            f"Matched tokens: {', '.join(classification.matched_tokens)}",
            f"Chains evaluated: {len(chain_results)}"
        ]
        for r in chain_results:
            reasoning.append(f"  -> Chain {r.chain.chain_id}: {r.final_confidence:.3f} (fallback={'yes' if r.fallback_used else 'no'})")
        return reasoning