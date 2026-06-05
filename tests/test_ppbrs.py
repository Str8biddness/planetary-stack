"""
PPBRS Test Suite
Unit tests for all PPBRS components.
"""
import pytest
from ppbrs.pattern_classifier import PatternClassifier, Pattern, ClassificationResult, ConfidenceLevel
from ppbrs.reasoning_chain import (
    ReasoningChainBuilder, ReasoningChain, ReasoningStep, ReasoningType,
    WeightedRuleEvaluator, ContextAwareReasoningPipeline
)
from ppbrs.confidence_scoring import (
    ConfidenceScorer, ConfidenceScore, ConfidenceComponent, ConfidenceSource,
    BayesianConfidenceUpdater
)
from ppbrs.rule_to_action import (
    RuleToActionMapper, Rule, Action, ActionType, MappingResult,
    ActionSequenceBuilder
)


class TestPatternClassifier:
    """Tests for PatternClassifier."""
    
    def test_add_pattern(self):
        classifier = PatternClassifier()
        pattern = Pattern(
            id="test_pattern",
            tokens=["hello", "world"],
            weight=1.0,
            tags=["greeting"]
        )
        classifier.add_pattern(pattern)
        assert "test_pattern" in classifier.patterns
    
    def test_exact_match(self):
        classifier = PatternClassifier(threshold=0.3)
        pattern = Pattern(
            id="greet",
            tokens=["hello", "hi"],
            weight=1.0,
            tags=["greeting"]
        )
        classifier.add_pattern(pattern)
        result = classifier.get_best_match("hello world")
        assert result is not None
        assert result.pattern_id == "greet"
    
    def test_no_match_below_threshold(self):
        classifier = PatternClassifier(threshold=0.9)
        pattern = Pattern(id="test", tokens=["hello"], weight=0.5)
        classifier.add_pattern(pattern)
        result = classifier.get_best_match("goodbye")
        assert result is None
    
    def test_fuzzy_matching(self):
        classifier = PatternClassifier(use_fuzzy=True)
        pattern = Pattern(id="typo_test", tokens=["hello"], weight=1.0)
        classifier.add_pattern(pattern)
        result = classifier.get_best_match("hello world")
        assert result is not None
    
    def test_load_patterns(self):
        classifier = PatternClassifier()
        patterns = [
            {"id": "p1", "tokens": ["test"], "weight": 1.0, "tags": ["testing"]},
            {"id": "p2", "tokens": ["demo"], "weight": 0.8, "tags": ["example"]}
        ]
        count = classifier.load_patterns(patterns)
        assert count == 2
    
    def test_confidence_levels(self):
        classifier = PatternClassifier()
        assert classifier.get_confidence_level(0.95) == ConfidenceLevel.VERY_HIGH
        assert classifier.get_confidence_level(0.8) == ConfidenceLevel.HIGH
        assert classifier.get_confidence_level(0.6) == ConfidenceLevel.MEDIUM
        assert classifier.get_confidence_level(0.2) == ConfidenceLevel.LOW
    
    def test_multiple_patterns_top_k(self):
        classifier = PatternClassifier(threshold=0.1)
        classifier.add_pattern(Pattern(id="p1", tokens=["hello"], weight=1.0))
        classifier.add_pattern(Pattern(id="p2", tokens=["hello", "world"], weight=1.0))
        results = classifier.classify("hello world", top_k=2)
        assert len(results) == 2
        assert results[0].confidence >= results[1].confidence

    def test_broad_tokens_do_not_expand_specific_candidate_set(self):
        classifier = PatternClassifier(threshold=0.1)
        for i in range(120):
            classifier.add_pattern(Pattern(
                id=f"p{i}",
                tokens=[f"signal_{i}", "common_token"],
                weight=1.0,
            ))

        candidates = classifier._get_candidates({"signal_17", "common_token"})

        assert [pattern.id for pattern in candidates] == ["p17"]

    def test_broad_tokens_still_match_when_no_specific_token_exists(self):
        classifier = PatternClassifier(threshold=0.1)
        for i in range(12):
            classifier.add_pattern(Pattern(
                id=f"p{i}",
                tokens=[f"signal_{i}", "common_token"],
                weight=1.0,
            ))

        candidates = classifier._get_candidates({"common_token"})

        assert len(candidates) == 12


class TestReasoningChain:
    """Tests for ReasoningChain."""
    
    def test_define_chain(self):
        builder = ReasoningChainBuilder()
        step = ReasoningStep(
            step_id="step1",
            description="Test step",
            reasoning_type=ReasoningType.DIRECT
        )
        builder.define_chain("test_chain", [step])
        assert "test_chain" in builder.defined_chains
    
    def test_build_from_patterns(self):
        builder = ReasoningChainBuilder()
        chains = builder.build_from_patterns(["pattern1", "pattern2"], {})
        assert len(chains) == 2
    
    def test_evaluate_chain(self):
        builder = ReasoningChainBuilder()
        chain = ReasoningChain(
            chain_id="test",
            steps=[
                ReasoningStep("s1", "Test", ReasoningType.DIRECT, weight=1.0),
                ReasoningStep("s2", "Test2", ReasoningType.CAUSAL, weight=0.8)
            ]
        )
        result = builder.evaluate_chain(chain, {})
        assert result.final_confidence > 0
        assert len(result.path_taken) == 2
    
    def test_fallback_logic(self):
        builder = ReasoningChainBuilder(min_confidence=0.8)
        chain = ReasoningChain(
            chain_id="low_conf",
            steps=[ReasoningStep("s1", "Low", ReasoningType.DIRECT, weight=0.1, confidence=0.1)]
        )
        result = builder.evaluate_chain(chain, {})
        assert result.fallback_used is True
    
    def test_combine_chains(self):
        builder = ReasoningChainBuilder()
        chain1 = ReasoningChain(chain_id="c1", steps=[], tags=["t1"])
        chain2 = ReasoningChain(chain_id="c2", steps=[], tags=["t2"])
        combined = builder.combine_chains([chain1, chain2])
        assert "t1" in combined.tags
        assert "t2" in combined.tags


class TestWeightedRuleEvaluator:
    """Tests for WeightedRuleEvaluator."""
    
    def test_add_rule(self):
        evaluator = WeightedRuleEvaluator()
        def condition(ctx): return ctx.get("value", 0) > 5
        def consequence(ctx): return "high"
        evaluator.add_rule(condition, consequence, weight=2.0)
        assert len(evaluator.rules) == 1
    
    def test_evaluate(self):
        evaluator = WeightedRuleEvaluator()
        evaluator.add_rule(lambda ctx: ctx.get("x", 0) > 1, lambda ctx: None)
        activated = evaluator.evaluate({"x": 5})
        assert len(activated) == 1
    
    def test_evaluate_no_match(self):
        evaluator = WeightedRuleEvaluator()
        evaluator.add_rule(lambda ctx: ctx.get("x", 0) > 10, lambda ctx: None)
        activated = evaluator.evaluate({"x": 5})
        assert len(activated) == 0
    
    def test_apply_top_rule(self):
        evaluator = WeightedRuleEvaluator()
        evaluator.add_rule(lambda ctx: True, lambda ctx: "matched", weight=2.0)
        result = evaluator.apply_top_rule({})
        assert result == "matched"
    
    def test_apply_fallback(self):
        evaluator = WeightedRuleEvaluator()
        evaluator.add_rule(lambda ctx: False, lambda ctx: None)
        fallback_called = []
        result = evaluator.apply_fallback({}, lambda ctx: fallback_called.append(True) or "fallback")
        assert result == "fallback"

    def test_apply_top_rule_short_circuits_lower_weight_candidates(self):
        evaluator = WeightedRuleEvaluator()
        calls = []
        evaluator.add_rule(lambda ctx: calls.append("low") or True, lambda ctx: "low", weight=0.5)
        evaluator.add_rule(lambda ctx: calls.append("high") or True, lambda ctx: "high", weight=2.0)
        evaluator.add_rule(lambda ctx: calls.append("middle") or True, lambda ctx: "middle", weight=1.0)

        result = evaluator.apply_top_rule({})

        assert result == "high"
        assert calls == ["high"]

    def test_apply_fallback_uses_threshold_when_no_rule_can_activate(self):
        evaluator = WeightedRuleEvaluator(activation_threshold=0.75)
        calls = []
        evaluator.add_rule(lambda ctx: calls.append("low") or True, lambda ctx: "low", weight=0.5)

        result = evaluator.apply_fallback({}, lambda ctx: "fallback")

        assert result == "fallback"
        assert calls == []


class TestContextAwareReasoningPipeline:
    """Tests for ContextAwareReasoningPipeline."""
    
    def test_process_no_match(self):
        pipeline = ContextAwareReasoningPipeline()
        result = pipeline.process("unknown input xyz123")
        assert result['status'] == 'no_match'
        assert result['confidence'] == 0.0
        assert result['response'] == ''
        assert result['user_facing'] is False
        assert result['chal_firmware_signal']['checkpoint']['state']['fallback_used'] is True
    
    def test_process_with_match(self):
        classifier = PatternClassifier()
        classifier.add_pattern(Pattern(
            id="test",
            tokens=["test"],
            weight=1.0,
            response_template="Matched!"
        ))
        pipeline = ContextAwareReasoningPipeline(classifier=classifier)
        result = pipeline.process("this is a test")
        assert result['status'] == 'success'
        assert result['classification']['confidence'] > 0
        assert result['response'] == ''
        assert result['user_facing'] is False
        assert result['chal_firmware_signal']['module_message']['payload']['template_context'] == "Matched!"
        assert result['chal_firmware_signal']['constraints']

    def test_weighted_rules_use_tag_index(self):
        evaluator = WeightedRuleEvaluator()
        calls = []
        evaluator.add_rule(lambda ctx: calls.append("chat") or True, lambda ctx: "chat", tags=["chat"])
        evaluator.add_rule(lambda ctx: calls.append("ops") or True, lambda ctx: "ops", tags=["ops"])
        evaluator.add_rule(lambda ctx: calls.append("shared") or True, lambda ctx: "shared")

        activated = evaluator.evaluate({"tags": ["ops"]})

        assert [item["rule"]["tags"] for item in activated] == [["ops"], []]
        assert calls == ["ops", "shared"]

    def test_weighted_rules_use_trigger_value_index(self):
        evaluator = WeightedRuleEvaluator()
        calls = []
        evaluator.add_rule(
            lambda ctx: calls.append("cpu") or True,
            lambda ctx: "cpu",
            trigger_values={"signal": "cpu_spike"},
        )
        evaluator.add_rule(
            lambda ctx: calls.append("disk") or True,
            lambda ctx: "disk",
            trigger_values={"signal": "disk_full"},
        )
        evaluator.add_rule(lambda ctx: calls.append("shared") or True, lambda ctx: "shared")

        activated = evaluator.evaluate({"signal": "disk_full"})

        assert [item["rule"]["trigger_values"] for item in activated] == [{"signal": "disk_full"}, {}]
        assert calls == ["disk", "shared"]


class TestConfidenceScorer:
    """Tests for ConfidenceScorer."""
    
    def test_basic_calculation(self):
        scorer = ConfidenceScorer()
        score = scorer.calculate(0.8)
        assert 0 <= score.overall <= 1
        assert score.level is not None
    
    def test_with_context_factors(self):
        scorer = ConfidenceScorer()
        score = scorer.calculate(0.7, context_factors={"relevance": 0.9, "coherence": 0.8})
        assert len(score.components) > 1
    
    def test_with_chain_confidences(self):
        scorer = ConfidenceScorer()
        score = scorer.calculate(0.6, chain_confidences=[0.8, 0.7, 0.9])
        assert score.factors['chain_avg'] > 0
    
    def test_calculate_entropy(self):
        scorer = ConfidenceScorer()
        entropy = scorer.calculate_entropy([0.25, 0.25, 0.25, 0.25])
        assert entropy > 0
    
    def test_is_reliable(self):
        scorer = ConfidenceScorer(base_threshold=0.3)
        reliable_score = scorer.calculate(0.8, chain_confidences=[0.7, 0.8])
        assert scorer.is_reliable(reliable_score) is True
        
        unreliable_score = scorer.calculate(0.2)
        assert scorer.is_reliable(unreliable_score) is False
    
    def test_merge_scores(self):
        scorer = ConfidenceScorer()
        score1 = scorer.calculate(0.8)
        score2 = scorer.calculate(0.6)
        merged = scorer.merge_scores([score1, score2])
        assert merged.overall == (score1.overall + score2.overall) / 2

    def test_calculate_preserves_component_shape_with_single_pass_factors(self):
        scorer = ConfidenceScorer()
        score = scorer.calculate(
            0.6,
            context_factors={"grounding": 0.8, "recency": 0.4},
            chain_confidences=[0.5, 0.7],
            evidence_boost=0.2,
        )

        assert [component.source for component in score.components] == [
            ConfidenceSource.PATTERN_MATCH,
            ConfidenceSource.CONTEXTUAL,
            ConfidenceSource.CONTEXTUAL,
            ConfidenceSource.CHAIN_INFERENCE,
            ConfidenceSource.EVIDENCE,
        ]
        assert score.factors["pattern"] == 0.6
        assert score.factors["context_avg"] == pytest.approx(0.6)
        assert score.factors["chain_avg"] == pytest.approx(0.6)
        assert score.factors["evidence_boost"] == 0.2


class TestBayesianConfidenceUpdater:
    """Tests for BayesianConfidenceUpdater."""
    
    def test_update(self):
        updater = BayesianConfidenceUpdater()
        result = updater.update(0.5, 0.8)
        assert 0 <= result <= 1
    
    def test_update_from_evidence(self):
        updater = BayesianConfidenceUpdater()
        result = updater.update_from_evidence(0.5, 0.9, evidence_weight=0.3)
        assert 0 <= result <= 1


class TestRuleToActionMapper:
    """Tests for RuleToActionMapper."""
    
    def test_add_rule(self):
        mapper = RuleToActionMapper()
        def condition(ctx): return True
        actions = [Action("a1", ActionType.RESPONSE, lambda ctx: "result")]
        mapper.add_rule("r1", "Test Rule", condition, actions)
        assert "r1" in mapper.rules
    
    def test_evaluate_rules(self):
        mapper = RuleToActionMapper()
        mapper.add_rule("r1", "Test", lambda ctx: ctx.get("active", False), [], weight=2.0)
        results = mapper.evaluate_rules({"active": True})
        assert len(results) == 1

    def test_evaluate_rules_prefilters_by_tags(self):
        mapper = RuleToActionMapper()
        calls = []
        mapper.add_rule("chat", "Chat", lambda ctx: calls.append("chat") or True, [], tags=["chat"])
        mapper.add_rule("ops", "Ops", lambda ctx: calls.append("ops") or True, [], tags=["ops"])
        mapper.add_rule("shared", "Shared", lambda ctx: calls.append("shared") or True, [])

        results = mapper.evaluate_rules({"tags": ["ops"]})

        assert [rule.rule_id for rule, _ in results] == ["ops", "shared"]
        assert calls == ["ops", "shared"]

    def test_evaluate_rules_prefilters_by_trigger_values_and_tags(self):
        mapper = RuleToActionMapper()
        calls = []
        mapper.add_rule(
            "cpu_ops",
            "CPU ops",
            lambda ctx: calls.append("cpu_ops") or True,
            [],
            tags=["ops"],
            metadata={"trigger_values": {"signal": "cpu_spike"}},
        )
        mapper.add_rule(
            "disk_ops",
            "Disk ops",
            lambda ctx: calls.append("disk_ops") or True,
            [],
            tags=["ops"],
            metadata={"trigger_values": {"signal": "disk_full"}},
        )
        mapper.add_rule(
            "disk_chat",
            "Disk chat",
            lambda ctx: calls.append("disk_chat") or True,
            [],
            tags=["chat"],
            metadata={"trigger_values": {"signal": "disk_full"}},
        )
        mapper.add_rule("shared_ops", "Shared ops", lambda ctx: calls.append("shared_ops") or True, [], tags=["ops"])

        results = mapper.evaluate_rules({"tags": ["ops"], "signal": "disk_full"})

        assert [rule.rule_id for rule, _ in results] == ["disk_ops", "shared_ops"]
        assert calls == ["disk_ops", "shared_ops"]
    
    def test_execute_action(self):
        mapper = RuleToActionMapper()
        result_holder = []
        action = Action("a1", ActionType.RESPONSE, lambda ctx: result_holder.append("executed") or "done")
        context = {"current_rule": "test"}
        res = mapper.execute_action(action, context)
        assert res.success is True
        assert "executed" in result_holder
    
    def test_map_to_action(self):
        mapper = RuleToActionMapper()
        mapper.add_rule("r1", "Test", lambda ctx: True, [
            Action("a1", ActionType.RESPONSE, lambda ctx: "result")
        ])
        result = mapper.map_to_action({})
        assert result is not None
        assert result.success is True

    def test_map_to_action_short_circuits_lower_priority_candidates(self):
        mapper = RuleToActionMapper()
        calls = []
        mapper.add_rule(
            "low",
            "Low priority",
            lambda ctx: calls.append("low") or True,
            [Action("low_action", ActionType.RESPONSE, lambda ctx: "low")],
            priority=1,
            weight=10.0,
        )
        mapper.add_rule(
            "high",
            "High priority",
            lambda ctx: calls.append("high") or True,
            [Action("high_action", ActionType.RESPONSE, lambda ctx: "high")],
            priority=5,
            weight=0.1,
        )

        result = mapper.map_to_action({})

        assert result is not None
        assert result.rule_id == "high"
        assert result.output == "high"
        assert calls == ["high"]

    def test_map_to_action_uses_score_upper_bound_within_priority(self):
        mapper = RuleToActionMapper()
        calls = []
        mapper.add_rule(
            "best",
            "Best score",
            lambda ctx: calls.append("best") or True,
            [Action("best_action", ActionType.RESPONSE, lambda ctx: "best")],
            weight=2.0,
            tags=["ops"],
        )
        mapper.add_rule(
            "impossible_to_beat",
            "Impossible to beat",
            lambda ctx: calls.append("impossible_to_beat") or True,
            [Action("impossible_action", ActionType.RESPONSE, lambda ctx: "impossible")],
            weight=1.0,
            tags=["ops"],
        )

        result = mapper.map_to_action({"tags": ["ops"]})

        assert result is not None
        assert result.rule_id == "best"
        assert result.output == "best"
        assert calls == ["best"]
    
    def test_get_statistics(self):
        mapper = RuleToActionMapper()
        mapper.add_rule("r1", "Test", lambda ctx: True, [
            Action("a1", ActionType.RESPONSE, lambda ctx: "done")
        ])
        mapper.map_to_action({})
        stats = mapper.get_statistics()
        assert stats['total_executions'] >= 1


class TestActionSequenceBuilder:
    """Tests for ActionSequenceBuilder."""
    
    def test_add_sequence(self):
        builder = ActionSequenceBuilder()
        builder.add_sequence("seq1", ["a1", "a2", "a3"])
        assert "seq1" in builder.sequences
    
    def test_add_dependency(self):
        builder = ActionSequenceBuilder()
        builder.add_dependency("a2", ["a1"])
        assert builder.dependencies["a2"] == ["a1"]
    
    def test_get_executable_sequence(self):
        builder = ActionSequenceBuilder()
        builder.add_sequence("seq1", ["a1", "a2", "a3"])
        builder.add_dependency("a2", ["a1"])
        builder.add_dependency("a3", ["a2"])
        satisfied = {"a1": True}
        result = builder.get_executable_sequence("seq1", satisfied)
        assert "a2" in result
        assert "a3" in result


class TestPatternClassifierEdgeCases:
    """Edge case tests for PatternClassifier."""
    
    def test_empty_pattern_tokens(self):
        classifier = PatternClassifier()
        pattern = Pattern(id="empty", tokens=[], weight=1.0)
        classifier.add_pattern(pattern)
        result = classifier.get_best_match("anything")
        assert result is None
    
    def test_empty_input_string(self):
        classifier = PatternClassifier()
        classifier.add_pattern(Pattern(id="test", tokens=["hello"]))
        result = classifier.get_best_match("")
        assert result is None
    
    def test_whitespace_only_input(self):
        classifier = PatternClassifier()
        classifier.add_pattern(Pattern(id="test", tokens=["hello"]))
        result = classifier.get_best_match("   ")
        assert result is None
    
    def test_unicode_patterns(self):
        classifier = PatternClassifier()
        pattern = Pattern(id="unicode", tokens=["héllo", "wörld"], weight=1.0)
        classifier.add_pattern(pattern)
        result = classifier.get_best_match("héllo wörld")
        assert result is not None
        assert result.pattern_id == "unicode"
    
    def test_special_characters(self):
        classifier = PatternClassifier()
        pattern = Pattern(id="special", tokens=["@#$%", "test!"], weight=1.0)
        classifier.add_pattern(pattern)
        result = classifier.get_best_match("@#$% test!")
        assert result is not None
    
    def test_case_insensitive(self):
        classifier = PatternClassifier()
        classifier.add_pattern(Pattern(id="case", tokens=["HELLO"]))
        result = classifier.get_best_match("hello")
        assert result is not None
        assert result.confidence > 0


class TestConfidenceScorerEdgeCases:
    """Edge case tests for ConfidenceScorer."""
    
    def test_zero_pattern_confidence(self):
        scorer = ConfidenceScorer()
        score = scorer.calculate(0.0)
        assert score.overall == 0.0
    
    def test_perfect_confidence(self):
        scorer = ConfidenceScorer()
        score = scorer.calculate(1.0)
        assert score.overall <= 1.0
    
    def test_empty_context_factors(self):
        scorer = ConfidenceScorer()
        score = scorer.calculate(0.5, context_factors={})
        assert score.overall > 0
    
    def test_empty_chain_confidences(self):
        scorer = ConfidenceScorer()
        score = scorer.calculate(0.5, chain_confidences=[])
        assert score.factors['chain_avg'] == 0.0
    
    def test_extreme_context_values(self):
        scorer = ConfidenceScorer()
        score = scorer.calculate(0.5, context_factors={"extreme": 999.0})
        assert score.overall <= 1.0
    
    def test_merge_empty_scores(self):
        scorer = ConfidenceScorer()
        merged = scorer.merge_scores([])
        assert merged.overall == 0.0
    
    def test_compare_scores(self):
        scorer = ConfidenceScorer()
        s1 = scorer.calculate(0.9)
        s2 = scorer.calculate(0.5)
        assert scorer.compare(s1, s2) == 1
        assert scorer.compare(s2, s1) == -1
        assert scorer.compare(s1, s1) == 0


class TestReasoningChainEdgeCases:
    """Edge case tests for ReasoningChain."""
    
    def test_empty_chain(self):
        builder = ReasoningChainBuilder()
        chain = ReasoningChain(chain_id="empty", steps=[])
        result = builder.evaluate_chain(chain, {})
        assert result.final_confidence == 0.0
    
    def test_combine_empty_chains(self):
        builder = ReasoningChainBuilder()
        combined = builder.combine_chains([])
        assert combined.chain_id == "empty"
    
    def test_chain_with_missing_antecedents(self):
        builder = ReasoningChainBuilder()
        step = ReasoningStep(
            step_id="orphan",
            description="Missing antecedent",
            reasoning_type=ReasoningType.CAUSAL,
            antecedents=["nonexistent"],
            weight=1.0
        )
        chain = ReasoningChain(chain_id="test", steps=[step])
        result = builder.evaluate_chain(chain, {})
        assert result.final_confidence >= 0


class TestRuleToActionEdgeCases:
    """Edge case tests for RuleToActionMapper."""
    
    def test_empty_context(self):
        mapper = RuleToActionMapper()
        mapper.add_rule("r1", "Test", lambda ctx: True, [
            Action("a1", ActionType.RESPONSE, lambda ctx: "done")
        ])
        result = mapper.map_to_action({})
        assert result is not None
        assert result.success is True
    
    def test_fallback_with_no_rules(self):
        mapper = RuleToActionMapper()
        fallback = Action("fallback", ActionType.FALLBACK, lambda ctx: "fallback_result")
        result = mapper.apply_fallback({}, fallback)
        assert result.success is True
        assert result.output == "fallback_result"
    
    def test_rule_with_tags_intersection(self):
        mapper = RuleToActionMapper()
        mapper.add_rule("r1", "Tagged", lambda ctx: True, [], tags=["a", "b"])
        results = mapper.evaluate_rules({"tags": ["a", "c"]})
        assert len(results) == 1
    
    def test_execute_action_with_exception(self):
        mapper = RuleToActionMapper()
        action = Action("fail", ActionType.RESPONSE, lambda ctx: 1/0)
        result = mapper.execute_action(action, {"current_rule": "test"})
        assert result.success is False
        assert result.error is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
