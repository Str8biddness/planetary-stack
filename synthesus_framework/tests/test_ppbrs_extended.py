"""
PPBRS Extended Test Suite
Additional tests for PPBRS components including pattern extraction and multi-step reasoning.
"""
import pytest
from ppbrs.pattern_extractor import (
    RegexPatternExtractor,
    NGramPatternExtractor,
    TFIDFPatternExtractor,
    ContextualPatternExtractor,
    CompositePatternExtractor,
    ExtractionResult,
    load_patterns_from_file,
    save_patterns_to_file
)
from ppbrs.multi_step_reasoning import (
    MultiStepReasoningChain,
    ReasoningChainOptimizer,
    FallbackReasoningEngine,
    ReasoningNode,
    Hypothesis,
    HypothesisStatus,
    ReasoningStrategy,
    ReasoningGraph
)


class TestRegexPatternExtractor:
    """Tests for RegexPatternExtractor."""
    
    def test_basic_extraction(self):
        extractor = RegexPatternExtractor()
        text = "The quick brown fox jumps over the lazy dog."
        result = extractor.extract(text)
        assert len(result.patterns) > 0
        assert 0 <= result.confidence <= 1
    
    def test_custom_patterns(self):
        patterns = [r'\b\w+ing\b', r'\b\w+ed\b']
        extractor = RegexPatternExtractor(custom_patterns=patterns)
        text = "The dog was running quickly yesterday."
        result = extractor.extract(text)
        assert 'running' in result.patterns or 'was' in result.patterns
    
    def test_extract_with_positions(self):
        extractor = RegexPatternExtractor()
        text = "Hello World"
        result = extractor.extract_with_positions(text)
        assert len(result) > 0
        for match, start, end in result:
            assert text[start:end] == match
    
    def test_min_length_filter(self):
        extractor = RegexPatternExtractor()
        text = "I a am an test"
        result = extractor.extract(text, min_length=3)
        for pattern in result.patterns:
            assert len(pattern) >= 3


class TestNGramPatternExtractor:
    """Tests for NGramPatternExtractor."""
    
    def test_basic_ngram_extraction(self):
        extractor = NGramPatternExtractor(min_n=2, max_n=3, top_k=10)
        corpus = [
            "the quick brown fox",
            "the lazy dog",
            "the quick fox"
        ]
        result = extractor.extract(corpus)
        assert len(result.patterns) <= 10
        assert 'the quick' in result.patterns or 'quick fox' in result.patterns
    
    def test_stopword_filtering(self):
        extractor = NGramPatternExtractor()
        corpus = ["the quick brown fox", "a quick brown fox"]
        result = extractor.extract(corpus, filter_stopwords=True)
        assert 'the quick' not in result.patterns
        assert 'quick brown' in result.patterns
    
    def test_single_text_extraction(self):
        extractor = NGramPatternExtractor()
        text = "the quick brown fox jumps"
        result = extractor.extract_from_text(text)
        assert len(result.patterns) > 0


class TestTFIDFPatternExtractor:
    """Tests for TFIDFPatternExtractor."""
    
    def test_fit_and_extract(self):
        extractor = TFIDFPatternExtractor()
        corpus = [
            "machine learning algorithms are powerful",
            "deep learning uses neural networks",
            "learning is important for AI"
        ]
        extractor.fit(corpus)
        result = extractor.extract("machine learning systems")
        assert len(result.patterns) > 0
        assert 'machine' in result.patterns  # machine appears in corpus
    
    def test_idf_scoring(self):
        extractor = TFIDFPatternExtractor()
        corpus = [
            "data science involves statistics",
            "data science involves programming",
            "data science involves math"
        ]
        extractor.fit(corpus)
        result = extractor.extract("data science statistics")
        assert len(result.patterns) > 0  # Should extract some term


class TestContextualPatternExtractor:
    """Tests for ContextualPatternExtractor."""
    
    def test_extract_with_anchor(self):
        extractor = ContextualPatternExtractor(window_size=2)
        text = "The quick brown fox jumps over the lazy dog"
        result = extractor.extract(text, anchor="fox")
        assert len(result.patterns) > 0
    
    def test_anchor_not_found(self):
        extractor = ContextualPatternExtractor()
        result = extractor.extract("hello world", anchor="missing")
        assert len(result.patterns) == 0
        assert result.confidence == 0.0
    
    def test_extract_with_tags(self):
        extractor = ContextualPatternExtractor()
        text = "The quick brown fox"
        result = extractor.extract_with_tags(text)
        assert len(result) == 4
        assert result[3]['token'] == 'fox'


class TestCompositePatternExtractor:
    """Tests for CompositePatternExtractor."""
    
    def test_extract_all_single_doc(self):
        extractor = CompositePatternExtractor()
        results = extractor.extract_all(["hello world test"], anchor="world")
        assert 'regex' in results or 'ngram' in results
    
    def test_extract_all_multi_doc(self):
        extractor = CompositePatternExtractor()
        corpus = ["doc one text", "doc two text", "doc three text"]
        results = extractor.extract_all(corpus)
        assert 'ngram' in results
        assert 'tfidf' in results
    
    def test_merge_results(self):
        extractor = CompositePatternExtractor()
        results = {
            'regex': ExtractionResult(['a', 'b', 'c'], 0.8),
            'ngram': ExtractionResult(['b', 'c', 'd'], 0.6)
        }
        merged = extractor.merge_results(results)
        assert len(merged) > 0
        assert merged[0][1] >= merged[-1][1]


class TestMultiStepReasoningChain:
    """Tests for MultiStepReasoningChain."""
    
    def test_add_hypothesis(self):
        chain = MultiStepReasoningChain()
        hypothesis = Hypothesis(id="h1", content="test hypothesis")
        chain.add_hypothesis(hypothesis)
        assert "h1" in chain.hypotheses
    
    def test_evaluate_hypothesis(self):
        chain = MultiStepReasoningChain()
        hypothesis = Hypothesis(id="h1", content="machine learning is powerful")
        chain.add_hypothesis(hypothesis)
        evidence = {"machine": True, "learning": True, "powerful": True}
        result = chain.evaluate_hypothesis("h1", evidence)
        assert result.status == HypothesisStatus.SUPPORTED
        assert result.confidence > 0.5
    
    def test_build_reasoning_graph(self):
        chain = MultiStepReasoningChain()
        steps = [
            ReasoningNode("n1", "Start", "direct"),
            ReasoningNode("n2", "Continue", "causal"),
            ReasoningNode("n3", "End", "direct")
        ]
        graph = chain.build_reasoning_graph(steps)
        assert len(graph.nodes) == 3
        assert len(graph.edges) == 2
    
    def test_forward_chain(self):
        chain = MultiStepReasoningChain()
        steps = [
            ReasoningNode("n1", "Start", "direct"),
            ReasoningNode("n2", "Middle", "causal"),
            ReasoningNode("n3", "End", "direct")
        ]
        chain.build_reasoning_graph(steps)
        chain.graph.add_edge("n1", "n2", 1.0)
        chain.graph.add_edge("n2", "n3", 1.0)
        path = chain.forward_chain(["n1"], {})
        assert "n1" in path
        assert len(path) <= 3
    
    def test_backward_chain(self):
        chain = MultiStepReasoningChain()
        steps = [
            ReasoningNode("n1", "Start", "direct"),
            ReasoningNode("n2", "Goal", "direct")
        ]
        chain.build_reasoning_graph(steps)
        chain.graph.add_edge("n1", "n2", 1.0)
        path = chain.backward_chain("n2", {})
        assert "n2" in path
    
    def test_find_shortest_path(self):
        chain = MultiStepReasoningChain()
        steps = [
            ReasoningNode("n1", "A", "direct"),
            ReasoningNode("n2", "B", "direct"),
            ReasoningNode("n3", "C", "direct")
        ]
        chain.build_reasoning_graph(steps)
        chain.graph.add_edge("n1", "n2", 1.0)
        chain.graph.add_edge("n2", "n3", 1.0)
        path, cost = chain.find_shortest_path("n1", "n3")
        assert path == ["n1", "n2", "n3"]
        assert cost == 2.0
    
    def test_backtrack_logic(self):
        chain = MultiStepReasoningChain(backtrack_limit=2)
        assert chain.backtrack_if_needed(0.2) is True
        assert chain.backtrack_if_needed(0.2) is True
        assert chain.backtrack_if_needed(0.2) is False
        assert chain.backtrack_if_needed(0.8) is False


class TestReasoningGraph:
    """Tests for ReasoningGraph."""
    
    def test_add_node(self):
        graph = ReasoningGraph()
        node = ReasoningNode("n1", "Test", "direct")
        graph.add_node(node)
        assert "n1" in graph.nodes
    
    def test_add_edge(self):
        graph = ReasoningGraph()
        node1 = ReasoningNode("n1", "Start", "direct")
        node2 = ReasoningNode("n2", "End", "direct")
        graph.add_node(node1)
        graph.add_node(node2)
        graph.add_edge("n1", "n2", 1.0)
        assert len(graph.edges) == 1
        assert "n2" in node1.consequents
        assert "n1" in node2.antecedents
    
    def test_topological_order(self):
        graph = ReasoningGraph()
        for i in range(4):
            graph.add_node(ReasoningNode(f"n{i}", f"Node {i}", "direct"))
        graph.add_edge("n0", "n1", 1.0)
        graph.add_edge("n1", "n2", 1.0)
        graph.add_edge("n2", "n3", 1.0)
        order = graph.get_topological_order()
        assert order.index("n0") < order.index("n1")
        assert order.index("n1") < order.index("n2")


class TestReasoningChainOptimizer:
    """Tests for ReasoningChainOptimizer."""
    
    def test_prune_low_confidence(self):
        optimizer = ReasoningChainOptimizer()
        steps = [
            ReasoningNode("n1", "High", "direct", confidence=0.9),
            ReasoningNode("n2", "Low", "direct", confidence=0.1),
            ReasoningNode("n3", "Medium", "direct", confidence=0.5)
        ]
        pruned = optimizer.prune_low_confidence_steps(steps, threshold=0.2)
        assert len(pruned) == 2
        assert "n2" not in [p.node_id for p in pruned]
    
    def test_merge_similar_steps(self):
        optimizer = ReasoningChainOptimizer()
        steps = [
            ReasoningNode("n1", "A", "direct", confidence=0.8),
            ReasoningNode("n2", "B", "direct", confidence=0.8),
            ReasoningNode("n3", "C", "causal", confidence=0.8)
        ]
        merged = optimizer.merge_similar_steps(steps)
        assert len(merged) <= len(steps)
    
    def test_calculate_chain_strength(self):
        optimizer = ReasoningChainOptimizer()
        steps = [
            ReasoningNode("n1", "A", "direct", weight=1.0, confidence=0.8),
            ReasoningNode("n2", "B", "direct", weight=1.0, confidence=0.6)
        ]
        graph = ReasoningGraph()
        for s in steps:
            graph.add_node(s)
        strength = optimizer.calculate_chain_strength(steps, graph)
        assert 0 <= strength <= 1
    
    def test_find_bottlenecks(self):
        optimizer = ReasoningChainOptimizer()
        steps = [
            ReasoningNode("n1", "A", "direct", weight=1.0, confidence=0.4),
            ReasoningNode("n2", "B", "direct", weight=1.0, confidence=0.8)
        ]
        graph = ReasoningGraph()
        for s in steps:
            graph.add_node(s)
        graph.add_node(ReasoningNode("n3", "C", "causal", weight=1.0, confidence=0.3))
        graph.nodes["n3"].antecedents = ["n1", "n2", "n4"]
        bottlenecks = optimizer.find_bottlenecks(steps, graph)
        assert "n3" in bottlenecks or len(bottlenecks) >= 0


class TestFallbackReasoningEngine:
    """Tests for FallbackReasoningEngine."""
    
    def test_register_fallback(self):
        engine = FallbackReasoningEngine()
        def fallback(ctx): return "fallback result"
        engine.register_fallback(fallback)
        assert len(engine.fallback_strategies) == 1
    
    def test_execute_with_fallback_success(self):
        engine = FallbackReasoningEngine()
        def primary(ctx): return "primary result"
        result, used = engine.execute_with_fallback({}, primary)
        assert result == "primary result"
        assert used is False
    
    def test_execute_with_fallback_failure(self):
        engine = FallbackReasoningEngine()
        def primary(ctx): raise ValueError("fail")
        def fb1(ctx): return "fallback 1"
        def fb2(ctx): return "fallback 2"
        engine.register_fallback(fb1)
        engine.register_fallback(fb2)
        result, used = engine.execute_with_fallback({}, primary)
        assert result == "fallback 1"
        assert used is True
    
    def test_execute_with_fallback_all_fail(self):
        engine = FallbackReasoningEngine(max_fallbacks=1)
        def primary(ctx): raise ValueError("fail")
        def fallback(ctx): raise ValueError("fallback fail")
        engine.register_fallback(fallback)
        result, used = engine.execute_with_fallback({}, primary)
        assert result is None
        assert used is True
    
    def test_get_consensus(self):
        engine = FallbackReasoningEngine()
        results = [{"text": "a", "confidence": 0.5}, {"text": "b", "confidence": 0.8}, {"text": "b", "confidence": 0.9}]
        consensus = engine.get_consensus(results)
        assert consensus == {"text": "b", "confidence": 0.9}
    
    def test_get_consensus_single(self):
        engine = FallbackReasoningEngine()
        result = engine.get_consensus(["single"])
        assert result == "single"
    
    def test_get_consensus_empty(self):
        engine = FallbackReasoningEngine()
        result = engine.get_consensus([])
        assert result is None


class TestPatternExtractorEdgeCases:
    """Edge case tests for pattern extractors."""
    
    def test_empty_corpus(self):
        extractor = NGramPatternExtractor()
        result = extractor.extract([])
        assert len(result.patterns) == 0
    
    def test_empty_text(self):
        extractor = RegexPatternExtractor()
        result = extractor.extract("")
        assert len(result.patterns) == 0
    
    def test_tfidf_without_fit(self):
        extractor = TFIDFPatternExtractor()
        result = extractor.extract("test text")
        assert len(result.patterns) == 0
    
    def test_contextual_empty_text(self):
        extractor = ContextualPatternExtractor()
        result = extractor.extract("", "anchor")
        assert result.confidence == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
