import time
import json
import os
import sys
import numpy as np
from pathlib import Path
from typing import Dict, List

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ppbrs.pattern_classifier import PatternClassifier, Pattern
from ppbrs.reasoning_chain import WeightedRuleEvaluator
from ppbrs.rule_to_action import RuleToActionMapper, Action, ActionType
from ppbrs.confidence_scoring import ConfidenceScorer
from ppbrs.multi_step_reasoning import MultiStepReasoningChain, Hypothesis, ReasoningNode

def benchmark_pattern_matching(n_patterns=1000, n_queries=100):
    print(f"Baselining Pattern Matching ({n_patterns} patterns, {n_queries} queries)...")
    classifier = PatternClassifier()
    
    # Seed patterns
    for i in range(n_patterns):
        classifier.add_pattern(Pattern(
            id=f"pattern_{i}", 
            tokens=[f"token_{i}", f"token_{i+1}", "common_token"]
        ))
    
    latencies = []
    for i in range(n_queries):
        query = f"I am looking for token_{i % n_patterns} and some common_token"
        start = time.perf_counter()
        classifier.classify(query)
        latencies.append(time.perf_counter() - start)
    
    return {
        "p50": np.percentile(latencies, 50) * 1000,
        "p95": np.percentile(latencies, 95) * 1000,
        "avg": np.mean(latencies) * 1000
    }

def benchmark_rule_evaluation(n_rules=500, n_evals=100):
    print(f"Baselining Rule Evaluation ({n_rules} rules, {n_evals} evals)...")
    mapper = RuleToActionMapper()
    
    # Seed rules
    for i in range(n_rules):
        action = Action(
            action_id=f"action_{i}",
            action_type=ActionType.RESPONSE,
            handler=lambda ctx, i=i: f"result_{i}"
        )
        mapper.add_rule(
            rule_id=f"rule_{i}",
            name=f"rule_{i}",
            condition=lambda ctx, i=i: ctx.get("key") == i,
            actions=[action],
            weight=1.0,
            tags=[f"tag_{i % 10}"],
            metadata={"trigger_values": {"key": i}},
        )
    
    latencies = []
    for i in range(n_evals):
        ctx = {"key": i % n_rules, "tags": [f"tag_{i % 10}"]}
        start = time.perf_counter()
        mapper.evaluate_rules(ctx)
        latencies.append(time.perf_counter() - start)
        
    return {
        "p50": np.percentile(latencies, 50) * 1000,
        "p95": np.percentile(latencies, 95) * 1000,
        "avg": np.mean(latencies) * 1000
    }

def benchmark_action_mapping(n_rules=500, n_evals=100):
    print(f"Baselining Action Mapping ({n_rules} rules, {n_evals} evals)...")
    mapper = RuleToActionMapper()

    for i in range(n_rules):
        action = Action(
            action_id=f"action_{i}",
            action_type=ActionType.RESPONSE,
            handler=lambda ctx, i=i: f"result_{i}",
        )
        mapper.add_rule(
            rule_id=f"rule_{i}",
            name=f"rule_{i}",
            condition=lambda ctx, i=i: ctx.get("key") == i,
            actions=[action],
            weight=float(n_rules - i),
            tags=[f"tag_{i % 10}"],
            metadata={"trigger_values": {"key": i}},
        )

    latencies = []
    for i in range(n_evals):
        ctx = {"key": i % n_rules, "tags": [f"tag_{i % 10}"]}
        start = time.perf_counter()
        mapper.map_to_action(ctx)
        latencies.append(time.perf_counter() - start)

    return {
        "p50": np.percentile(latencies, 50) * 1000,
        "p95": np.percentile(latencies, 95) * 1000,
        "avg": np.mean(latencies) * 1000
    }

def benchmark_weighted_top_rule(n_rules=500, n_evals=100):
    print(f"Baselining Weighted Top Rule ({n_rules} rules, {n_evals} evals)...")
    evaluator = WeightedRuleEvaluator()

    for i in range(n_rules):
        evaluator.add_rule(
            condition=lambda ctx, i=i: ctx.get("key") == i,
            consequence=lambda ctx, i=i: f"result_{i}",
            weight=float(n_rules - i),
            tags=[f"tag_{i % 10}"],
            trigger_values={"key": i},
        )

    latencies = []
    for i in range(n_evals):
        ctx = {"key": i % n_rules, "tags": [f"tag_{i % 10}"]}
        start = time.perf_counter()
        evaluator.apply_top_rule(ctx)
        latencies.append(time.perf_counter() - start)

    return {
        "p50": np.percentile(latencies, 50) * 1000,
        "p95": np.percentile(latencies, 95) * 1000,
        "avg": np.mean(latencies) * 1000
    }

def benchmark_confidence_scoring(n_scores=5000):
    print(f"Baselining Confidence Scoring ({n_scores} scores)...")
    scorer = ConfidenceScorer()
    context_factors = {
        "relevance": 0.82,
        "recency": 0.72,
        "coherence": 0.91,
        "grounding": 0.77,
    }
    chain_confidences = [0.67, 0.79, 0.84]

    latencies = []
    for i in range(n_scores):
        pattern_confidence = 0.45 + ((i % 50) / 100)
        start = time.perf_counter()
        scorer.calculate(
            pattern_confidence,
            context_factors=context_factors,
            chain_confidences=chain_confidences,
            evidence_boost=0.15,
        )
        latencies.append(time.perf_counter() - start)

    return {
        "p50": np.percentile(latencies, 50) * 1000,
        "p95": np.percentile(latencies, 95) * 1000,
        "avg": np.mean(latencies) * 1000
    }

def benchmark_graph_traversal(n_nodes=100, n_edges=300, n_walks=50):
    print(f"Baselining Graph Traversal ({n_nodes} nodes, {n_edges} edges)...")
    chain = MultiStepReasoningChain()
    
    # Seed graph
    for i in range(n_nodes):
        node = ReasoningNode(
            node_id=f"h_{i}",
            content=f"hypothesis {i} content with token_{i}",
            reasoning_type="deduction"
        )
        chain.graph.add_node(node)
        chain.add_hypothesis(Hypothesis(id=f"h_{i}", content=f"h_{i}"))
    
    for i in range(n_edges):
        u = i % n_nodes
        v = (i + 1) % n_nodes
        chain.graph.add_edge(f"h_{u}", f"h_{v}", 0.8)
        
    latencies = []
    for i in range(n_walks):
        start_node = f"h_{i % n_nodes}"
        end_node = f"h_{(i + 10) % n_nodes}"
        start = time.perf_counter()
        chain.find_shortest_path(start_node, end_node)
        latencies.append(time.perf_counter() - start)
        
    return {
        "p50": np.percentile(latencies, 50) * 1000,
        "p95": np.percentile(latencies, 95) * 1000,
        "avg": np.mean(latencies) * 1000
    }

def benchmark_graph_shortest_path_cache(n_nodes=100, n_edges=300, n_walks=500):
    print(f"Baselining Graph Shortest-Path Cache ({n_nodes} nodes, {n_edges} edges, {n_walks} walks)...")
    chain = MultiStepReasoningChain()

    for i in range(n_nodes):
        node = ReasoningNode(
            node_id=f"h_{i}",
            content=f"hypothesis {i} content with token_{i}",
            reasoning_type="deduction",
        )
        chain.graph.add_node(node)
        chain.add_hypothesis(Hypothesis(id=f"h_{i}", content=f"h_{i}"))

    for i in range(n_edges):
        u = i % n_nodes
        v = (i + 1) % n_nodes
        chain.graph.add_edge(f"h_{u}", f"h_{v}", 0.8)

    chain.find_shortest_path("h_0", "h_10")

    latencies = []
    for _ in range(n_walks):
        start = time.perf_counter()
        chain.find_shortest_path("h_0", "h_10")
        latencies.append(time.perf_counter() - start)

    return {
        "p50": np.percentile(latencies, 50) * 1000,
        "p95": np.percentile(latencies, 95) * 1000,
        "avg": np.mean(latencies) * 1000
    }

if __name__ == "__main__":
    results = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "metrics": {}
    }
    
    results["metrics"]["pattern_matching"] = benchmark_pattern_matching()
    results["metrics"]["rule_evaluation"] = benchmark_rule_evaluation()
    results["metrics"]["action_mapping"] = benchmark_action_mapping()
    results["metrics"]["weighted_top_rule"] = benchmark_weighted_top_rule()
    results["metrics"]["confidence_scoring"] = benchmark_confidence_scoring()
    results["metrics"]["graph_traversal"] = benchmark_graph_traversal()
    results["metrics"]["graph_shortest_path_cache"] = benchmark_graph_shortest_path_cache()
    
    print("\nBenchmark Results (ms):")
    print(json.dumps(results, indent=2))
    
    # Save to logs
    log_path = Path("tools/ppbrs_dev_log.md")
    
    with open(log_path, "a") as f:
        if os.path.getsize(log_path) == 0:
            f.write("# PPBRS Optimization Dev Log\n\n")
        
        f.write(f"## Baseline - {results['timestamp']}\n\n")
        f.write("| Component | p50 (ms) | p95 (ms) | Avg (ms) |\n")
        f.write("| --- | --- | --- | --- |\n")
        for comp, metrics in results["metrics"].items():
            f.write(f"| {comp} | {metrics['p50']:.4f} | {metrics['p95']:.4f} | {metrics['avg']:.4f} |\n")
        f.write("\n")
