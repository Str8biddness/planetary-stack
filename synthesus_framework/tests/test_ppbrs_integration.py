"""
PPBRS Integration Tests
Integration tests for PPBRS components working together.
"""
import pytest
from ppbrs.pattern_classifier import PatternClassifier, Pattern
from ppbrs.reasoning_chain import (
    ReasoningChainBuilder, ReasoningChain, ReasoningStep, ReasoningType,
    WeightedRuleEvaluator, ContextAwareReasoningPipeline
)
from ppbrs.confidence_scoring import ConfidenceScorer, BayesianConfidenceUpdater
from ppbrs.rule_to_action import RuleToActionMapper, Action, ActionType
from ppbrs.pattern_extractor import (
    CompositePatternExtractor, RegexPatternExtractor, NGramPatternExtractor
)
from ppbrs.multi_step_reasoning import (
    MultiStepReasoningChain, ReasoningNode, ReasoningGraph,
    ReasoningChainOptimizer, FallbackReasoningEngine
)


class TestFullPipelineIntegration:
    """Integration tests for the full PPBRS pipeline."""
    
    def test_classifier_to_chain_to_action(self):
        """Test complete flow: classify -> reasoning chain -> action mapping."""
        classifier = PatternClassifier(threshold=0.3)
        classifier.add_pattern(Pattern(
            id="greeting",
            tokens=["hello", "hi"],
            weight=1.0,
            tags=["greeting"],
            response_template="Hello there!"
        ))
        
        pipeline = ContextAwareReasoningPipeline(classifier=classifier)
        result = pipeline.process("hello world")
        
        assert result['status'] == 'success'
        assert result['classification']['pattern_id'] == 'greeting'
        assert result['response'] == 'Hello there!'
    
    def test_confidence_affects_chain_selection(self):
        """Test that confidence levels affect chain evaluation."""
        scorer = ConfidenceScorer()
        
        high_conf = scorer.calculate(0.99, chain_confidences=[0.95])
        low_conf = scorer.calculate(0.1)
        
        assert high_conf.level == "very_high"
        assert low_conf.level in ("minimal", "low")
        
        assert scorer.is_reliable(high_conf) is True
        assert scorer.is_reliable(low_conf) is False
    
    def test_bayesian_updates_composition(self):
        """Test Bayesian updating composes with confidence scoring."""
        updater = BayesianConfidenceUpdater()
        scorer = ConfidenceScorer()
        
        prior = 0.5
        likelihood = 0.8
        updated = updater.update(prior, likelihood)
        
        score = scorer.calculate(updated)
        assert 0 <= score.overall <= 1


class TestMultiExtractorIntegration:
    """Tests for multiple extractors working together."""
    
    def test_composite_extracts_diverse_patterns(self):
        """Test that composite extractor finds diverse pattern types."""
        extractor = CompositePatternExtractor()
        corpus = [
            "machine learning algorithms process data",
            "deep learning neural networks are powerful",
            "natural language processing understands text",
            "computer vision recognizes images",
            "reinforcement learning optimizes decisions"
        ]
        
        results = extractor.extract_all(corpus)
        
        assert 'ngram' in results
        assert 'tfidf' in results
        assert len(results['ngram'].patterns) > 0
        assert len(results['tfidf'].patterns) > 0
    
    def test_regex_and_ngram_complementary(self):
        """Test that regex and ngram extractors find different patterns."""
        regex_ext = RegexPatternExtractor()
        ngram_ext = NGramPatternExtractor()
        
        text = "Machine learning is exciting! The learning process is gradual."
        
        regex_result = regex_ext.extract(text)
        ngram_result = ngram_ext.extract_from_text(text)
        
        regex_patterns = set(regex_result.patterns)
        ngram_patterns = set(ngram_result.patterns)
        
        assert len(regex_patterns) > 0 or len(ngram_patterns) > 0


class TestReasoningGraphIntegration:
    """Tests for reasoning graph operations."""
    
    def test_chain_building_with_context(self):
        """Test building reasoning chains with context awareness."""
        builder = ReasoningChainBuilder()
        
        chains = builder.build_from_patterns(
            ["pattern1", "pattern2"],
            {"requires_context": True}
        )
        
        assert len(chains) == 2
        
        for chain in chains:
            assert len(chain.steps) >= 1
            assert chain.tags
    
    def test_multi_step_chain_evaluation(self):
        """Test evaluating multi-step reasoning chains."""
        chain = MultiStepReasoningChain(max_depth=5)
        
        steps = [
            ReasoningNode("n1", "Start", "direct", weight=1.0, confidence=0.9),
            ReasoningNode("n2", "Middle", "causal", weight=0.8, confidence=0.7),
            ReasoningNode("n3", "End", "direct", weight=1.0, confidence=0.8)
        ]
        
        graph = chain.build_reasoning_graph(steps)
        graph.add_edge("n1", "n2", 1.0)
        graph.add_edge("n2", "n3", 1.0)
        
        path = chain.forward_chain(["n1"], {})
        assert "n1" in path
        assert len(path) >= 1
    
    def test_optimizer_improves_chain(self):
        """Test that optimizer improves reasoning chains."""
        optimizer = ReasoningChainOptimizer()
        
        steps = [
            ReasoningNode("n1", "A", "direct", confidence=0.9, weight=1.0),
            ReasoningNode("n2", "B", "direct", confidence=0.1, weight=1.0),
            ReasoningNode("n3", "C", "direct", confidence=0.7, weight=1.0)
        ]
        
        graph = ReasoningGraph()
        for step in steps:
            graph.add_node(step)
        
        pruned = optimizer.prune_low_confidence_steps(steps, threshold=0.2)
        assert len(pruned) == 2
        assert "n2" not in [s.node_id for s in pruned]
        
        strength = optimizer.calculate_chain_strength(pruned, graph)
        assert strength > 0


class TestFallbackIntegration:
    """Tests for fallback reasoning integration."""
    
    def test_fallback_preserves_confidence(self):
        """Test that fallback reasoning maintains confidence tracking."""
        engine = FallbackReasoningEngine()
        
        def primary(ctx):
            if ctx.get("fail", False):
                raise ValueError("simulated failure")
            return {"result": "success", "confidence": 0.9}
        
        def fallback(ctx):
            return {"result": "fallback_used", "confidence": 0.5}
        
        engine.register_fallback(fallback)
        
        result1, used1 = engine.execute_with_fallback({}, primary)
        assert result1["confidence"] == 0.9
        assert used1 is False
        
        result2, used2 = engine.execute_with_fallback({"fail": True}, primary)
        assert result2["confidence"] == 0.5
        assert used2 is True
    
    def test_fallback_returns_none_when_all_fail(self):
        """Test fallback returns None when all strategies fail."""
        engine = FallbackReasoningEngine(max_fallbacks=1)
        
        def primary(ctx):
            raise ValueError("simulated failure")
        
        def fallback_fails(ctx):
            raise ValueError("fallback also fails")
        
        engine.register_fallback(fallback_fails)
        
        result, used = engine.execute_with_fallback({}, primary)
        assert result is None
        assert used is True
    
    def test_consensus_integration(self):
        """Test consensus building from multiple reasoning results."""
        engine = FallbackReasoningEngine()
        
        results = [
            {"text": "a", "confidence": 0.3},
            {"text": "a", "confidence": 0.7},
            {"text": "b", "confidence": 0.6}
        ]
        
        consensus = engine.get_consensus(results)
        assert consensus["text"] == "a"
        assert consensus["confidence"] == 0.7


class TestRuleActionIntegration:
    """Tests for rule-to-action integration."""
    
    def test_rule_with_classifier_integration(self):
        """Test rule evaluation with classifier results."""
        mapper = RuleToActionMapper()
        
        def high_confidence_condition(ctx):
            return ctx.get('classification', {}).get('confidence', 0) > 0.5
        
        results = []
        action = Action(
            "process",
            ActionType.RESPONSE,
            lambda ctx: results.append(ctx.get('classification', {}).get('pattern_id'))
        )
        
        mapper.add_rule("process_high", "High confidence", high_confidence_condition, [action])
        
        result = mapper.map_to_action({
            'classification': {'pattern_id': 'test', 'confidence': 0.8}
        })
        
        assert result is not None
        assert result.success is True
        assert 'test' in results


class TestPatternClassifierPersistence:
    """Tests for pattern loading and saving."""
    
    def test_save_and_load_patterns(self, tmp_path):
        """Test saving and loading patterns preserves data."""
        classifier = PatternClassifier()
        classifier.add_pattern(Pattern(
            id="test_pattern",
            tokens=["hello", "world"],
            weight=1.0,
            tags=["greeting", "test"],
            response_template="Hello, World!"
        ))
        
        filepath = tmp_path / "patterns.json"
        assert classifier.save_patterns(str(filepath)) is True
        
        classifier2 = PatternClassifier()
        count = classifier2.load_patterns([
            {"id": "test_pattern", "tokens": ["hello", "world"], "weight": 1.0, "tags": ["greeting", "test"]}
        ])
        
        assert count == 1
        assert "test_pattern" in classifier2.patterns


class TestEndToEndScenarios:
    """End-to-end scenario tests."""
    
    def test_greeting_scenario(self):
        """Test complete greeting classification and response scenario."""
        classifier = PatternClassifier(threshold=0.3)
        classifier.add_pattern(Pattern(
            id="greet",
            tokens=["hello", "hi", "hey"],
            weight=1.0,
            tags=["greeting"],
            response_template="Hi there!"
        ))
        classifier.add_pattern(Pattern(
            id="farewell",
            tokens=["goodbye", "bye", "see ya"],
            weight=1.0,
            tags=["farewell"],
            response_template="Goodbye!"
        ))
        
        pipeline = ContextAwareReasoningPipeline(classifier=classifier)
        
        result1 = pipeline.process("hello there friend")
        assert result1['status'] == 'success'
        assert result1['classification']['pattern_id'] == 'greet'
        
        result2 = pipeline.process("goodbye for now")
        assert result2['status'] == 'success'
        assert result2['classification']['pattern_id'] == 'farewell'
    
    def test_low_confidence_fallback(self):
        """Test that low confidence inputs trigger appropriate fallback."""
        classifier = PatternClassifier(threshold=0.3)
        classifier.add_pattern(Pattern(
            id="test",
            tokens=["zxy"],
            weight=0.1
        ))
        
        pipeline = ContextAwareReasoningPipeline(classifier=classifier)
        
        result = pipeline.process("completely unrelated input xyz123")
        assert result['status'] == 'no_match'
        assert result['confidence'] == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])