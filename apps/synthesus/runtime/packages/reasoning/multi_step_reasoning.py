"""
PPBRS Multi-Step Reasoning Chain Extension
Advanced multi-step reasoning with backtracking and hypothesis testing.
"""
from typing import Optional, List, Dict, Any, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
import heapq


class ReasoningStrategy(Enum):
    """Strategies for reasoning chain construction."""
    FORWARD = "forward"       # Forward chaining from premises
    BACKWARD = "backward"     # Backward chaining from goals
    BIDIRECTIONAL = "bidirectional"  # Both directions meeting
    ABDUCTIVE = "abductive"    # Best explanation inference


class HypothesisStatus(Enum):
    """Status of a hypothesis in reasoning."""
    PENDING = "pending"
    ACTIVE = "active"
    SUPPORTED = "supported"
    REFUTED = "refuted"
    UNCERTAIN = "uncertain"


@dataclass
class Hypothesis:
    """A hypothesis being evaluated in reasoning chain."""
    id: str
    content: str
    confidence: float = 0.5
    status: HypothesisStatus = HypothesisStatus.PENDING
    supporting_evidence: List[str] = field(default_factory=list)
    refuting_evidence: List[str] = field(default_factory=list)
    parent_hypothesis: Optional[str] = None


@dataclass
class ReasoningNode:
    """A node in the reasoning graph."""
    node_id: str
    content: str
    reasoning_type: str
    antecedents: List[str] = field(default_factory=list)
    consequents: List[str] = field(default_factory=list)
    confidence: float = 1.0
    weight: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReasoningGraph:
    """Graph structure for complex reasoning chains."""
    nodes: Dict[str, ReasoningNode] = field(default_factory=dict)
    edges: List[Tuple[str, str, float]] = field(default_factory=list)  # (from, to, weight)
    forward_adjacency: Dict[str, List[Tuple[str, float]]] = field(default_factory=dict)
    reverse_adjacency: Dict[str, List[Tuple[str, float]]] = field(default_factory=dict)
    _topological_cache: Optional[List[str]] = None
    _shortest_path_cache: Dict[Tuple[str, str], Tuple[List[str], float]] = field(default_factory=dict)
    _version: int = 0

    def _invalidate_caches(self) -> None:
        self._version += 1
        self._topological_cache = None
        self._shortest_path_cache.clear()
    
    def add_node(self, node: ReasoningNode) -> None:
        """Adds a ReasoningNode to the graph.

        Args:
            node: The ReasoningNode instance to add.
        """
        self.nodes[node.node_id] = node
        self.forward_adjacency.setdefault(node.node_id, [])
        self.reverse_adjacency.setdefault(node.node_id, [])
        self._invalidate_caches()
    
    def add_edge(self, from_id: str, to_id: str, weight: float = 1.0) -> None:
        """Creates a directed edge between two nodes in the graph.

        Args:
            from_id: ID of the source node.
            to_id: ID of the target node.
            weight: Relative weight or cost of the edge. Defaults to 1.0.
        """
        if from_id in self.nodes and to_id in self.nodes:
            if any(src == from_id and dst == to_id for src, dst, _ in self.edges):
                return
            self.edges.append((from_id, to_id, weight))
            if to_id not in self.nodes[from_id].consequents:
                self.nodes[from_id].consequents.append(to_id)
            if from_id not in self.nodes[to_id].antecedents:
                self.nodes[to_id].antecedents.append(from_id)
            self.forward_adjacency.setdefault(from_id, []).append((to_id, weight))
            self.reverse_adjacency.setdefault(to_id, []).append((from_id, weight))
            self._invalidate_caches()
    
    def get_topological_order(self) -> List[str]:
        """Get nodes in topological order."""
        if self._topological_cache is not None:
            return list(self._topological_cache)

        in_degree = {n: 0 for n in self.nodes}
        for to, incoming in self.reverse_adjacency.items():
            in_degree[to] += len(incoming)
        
        queue = deque([n for n, d in in_degree.items() if d == 0])
        result = []
        
        while queue:
            node_id = queue.popleft()
            result.append(node_id)
            for to_id, _ in self.forward_adjacency.get(node_id, []):
                in_degree[to_id] -= 1
                if in_degree[to_id] == 0:
                    queue.append(to_id)
        
        self._topological_cache = list(result)
        return result


class MultiStepReasoningChain:
    """
    Advanced multi-step reasoning with backtracking and hypothesis testing.
    Extends basic reasoning chains with graph-based evaluation.
    """
    
    def __init__(self, max_depth: int = 10, backtrack_limit: int = 3):
        """Initializes the MultiStepReasoningChain.

        Args:
            max_depth: Maximum recursion depth for chaining. Defaults to 10.
            backtrack_limit: Maximum number of backtracking attempts allowed. Defaults to 3.
        """
        self.max_depth = max_depth
        self.backtrack_limit = backtrack_limit
        self.hypotheses: Dict[str, Hypothesis] = {}
        self.graph = ReasoningGraph()
        self._current_path: List[str] = []
        self._backtrack_count = 0
    
    def add_hypothesis(self, hypothesis: Hypothesis) -> None:
        """Adds a hypothesis to the internal pool for evaluation.

        Args:
            hypothesis: The Hypothesis object to add.
        """
        self.hypotheses[hypothesis.id] = hypothesis
    
    def evaluate_hypothesis(self, hypothesis_id: str, evidence: Dict[str, Any]) -> Hypothesis:
        """Evaluates a hypothesis against provided evidence and updates its status.

        Args:
            hypothesis_id: Unique identifier of the hypothesis.
            evidence: Dictionary of facts to check against the hypothesis content.

        Returns:
            The updated Hypothesis object with new confidence and status.
        """
        hypothesis = self.hypotheses.get(hypothesis_id)
        if not hypothesis:
            return Hypothesis(id=hypothesis_id, content="", confidence=0.0, 
                           status=HypothesisStatus.UNCERTAIN)
        
        hypothesis.status = HypothesisStatus.ACTIVE
        
        supporting = 0
        refuting = 0
        
        for key, value in evidence.items():
            if key in hypothesis.content.lower():
                supporting += 1
                hypothesis.supporting_evidence.append(key)
            elif f"not {key}" in hypothesis.content.lower() or f"no {key}" in hypothesis.content.lower():
                refuting += 1
                hypothesis.refuting_evidence.append(key)
        
        if supporting > refuting:
            hypothesis.confidence = min(1.0, 0.5 + (supporting - refuting) * 0.1)
            hypothesis.status = HypothesisStatus.SUPPORTED
        elif refuting > supporting:
            hypothesis.confidence = max(0.0, 0.5 - (refuting - supporting) * 0.1)
            hypothesis.status = HypothesisStatus.REFUTED
        else:
            hypothesis.status = HypothesisStatus.UNCERTAIN
        
        return hypothesis
    
    def build_reasoning_graph(self, steps: List[ReasoningNode]) -> ReasoningGraph:
        """Constructs a ReasoningGraph from a sequence of reasoning steps.

        Args:
            steps: List of ReasoningNode objects to include in the graph.

        Returns:
            The newly constructed ReasoningGraph.
        """
        self.graph = ReasoningGraph()
        
        for step in steps:
            self.graph.add_node(step)
        
        for i, step in enumerate(steps[:-1]):
            self.graph.add_edge(step.node_id, steps[i+1].node_id, step.weight)
        
        return self.graph
    
    def forward_chain(self, start_nodes: List[str], evidence: Dict[str, Any]) -> List[str]:
        """Executes forward chaining reasoning from a set of starting nodes.

        Args:
            start_nodes: List of node IDs to begin reasoning from.
            evidence: Contextual evidence that might influence traversal.

        Returns:
            A list of node IDs representing the inferred reasoning path.
        """
        visited = set()
        queue = deque(start_nodes)
        path = []
        
        while queue and len(path) < self.max_depth:
            node_id = queue.popleft()
            if node_id in visited:
                continue
            
            visited.add(node_id)
            path.append(node_id)
            
            for consequent, _ in self.graph.forward_adjacency.get(node_id, []):
                if consequent not in visited:
                    queue.append(consequent)
        
        self._current_path = path
        return path
    
    def backward_chain(self, goal_node: str, evidence: Dict[str, Any]) -> List[str]:
        """Executes backward chaining reasoning starting from a desired goal.

        Args:
            goal_node: The target node ID to work backward from.
            evidence: Contextual evidence for validation.

        Returns:
            A list of node IDs forming a valid path to the goal.
        """
        visited = set()
        path = []

        def dfs(node_id: str) -> None:
            if node_id in visited or len(path) >= self.max_depth:
                return

            visited.add(node_id)
            for antecedent, _ in reversed(self.graph.reverse_adjacency.get(node_id, [])):
                dfs(antecedent)
                if len(path) >= self.max_depth:
                    return
            path.append(node_id)

        if goal_node in self.graph.nodes:
            dfs(goal_node)
        return path
    
    def find_shortest_path(self, start: str, end: str) -> Tuple[List[str], float]:
        """Finds the shortest reasoning path between two nodes using Dijkstra's algorithm.

        Args:
            start: Source node ID.
            end: Target node ID.

        Returns:
            A tuple containing (list of node IDs in path, total path weight).
        """
        if start not in self.graph.nodes or end not in self.graph.nodes:
            return [], 0.0

        cache_key = (start, end)
        cached = self.graph._shortest_path_cache.get(cache_key)
        if cached is not None:
            path, cost = cached
            return list(path), cost
        
        distances = {n: float('inf') for n in self.graph.nodes}
        distances[start] = 0.0
        previous = {n: None for n in self.graph.nodes}
        
        pq = [(0.0, start)]
        visited = set()
        
        while pq:
            dist, node_id = heapq.heappop(pq)
            
            if node_id in visited:
                continue
            visited.add(node_id)
            
            if node_id == end:
                break
            
            for to_id, weight in self.graph.forward_adjacency.get(node_id, []):
                new_dist = dist + weight
                if new_dist < distances[to_id]:
                    distances[to_id] = new_dist
                    previous[to_id] = node_id
                    heapq.heappush(pq, (new_dist, to_id))
        
        path = []
        current = end
        while current is not None:
            path.append(current)
            current = previous.get(current)
        
        path.reverse()
        cost = distances.get(end, float('inf'))
        self.graph._shortest_path_cache[cache_key] = (list(path), cost)
        return path, cost
    
    def backtrack_if_needed(self, current_confidence: float) -> bool:
        """Determines if the reasoning process should backtrack based on confidence.

        Args:
            current_confidence: The confidence score of the current reasoning branch.

        Returns:
            True if backtracking should occur, False otherwise.
        """
        if current_confidence < 0.3 and self._backtrack_count < self.backtrack_limit:
            self._backtrack_count += 1
            return True
        return False
    
    def get_alternative_paths(self, current_path: List[str]) -> List[List[str]]:
        """Identifies potential alternative reasoning paths branching from the current one.

        Args:
            current_path: The sequence of node IDs currently being explored.

        Returns:
            A list of alternative paths, each represented as a list of node IDs.
        """
        alternatives = []
        
        if not current_path:
            return alternatives
        
        last_node = current_path[-1]
        for to_id, _ in self.graph.forward_adjacency.get(last_node, []):
            if to_id not in current_path:
                path, _ = self.find_shortest_path(current_path[0], to_id)
                if path and path != current_path:
                    alternatives.append(path)
        
        return alternatives[:3]


class ReasoningChainOptimizer:
    """Optimize reasoning chains for efficiency and accuracy."""
    
    @staticmethod
    def prune_low_confidence_steps(steps: List[ReasoningNode], threshold: float = 0.2) -> List[ReasoningNode]:
        """Removes reasoning steps that fall below a minimum confidence threshold.

        Args:
            steps: List of ReasoningNode objects to evaluate.
            threshold: Minimum confidence score to retain a step. Defaults to 0.2.

        Returns:
            A pruned list of ReasoningNode objects.
        """
        return [s for s in steps if s.confidence >= threshold]
    
    @staticmethod
    def merge_similar_steps(steps: List[ReasoningNode]) -> List[ReasoningNode]:
        """Consolidates consecutive steps that share the same reasoning type and confidence.

        Args:
            steps: List of ReasoningNode objects.

        Returns:
            A list of ReasoningNode objects with similar adjacent steps merged.
        """
        if not steps:
            return []
        
        merged = [steps[0]]
        
        for step in steps[1:]:
            last = merged[-1]
            if (step.reasoning_type == last.reasoning_type and 
                step.confidence == last.confidence):
                last.consequents.extend(step.consequents)
            else:
                merged.append(step)
        
        return merged
    
    @staticmethod
    def calculate_chain_strength(steps: List[ReasoningNode], graph: ReasoningGraph) -> float:
        """Computes the aggregate strength score for a reasoning chain.

        Args:
            steps: List of ReasoningNode objects in the chain.
            graph: The ReasoningGraph context.

        Returns:
            The average weighted confidence of the steps as a float.
        """
        if not steps:
            return 0.0
        
        weights = []
        for step in steps:
            node = graph.nodes.get(step.node_id)
            if node:
                weights.append(node.weight * node.confidence)
            else:
                weights.append(step.weight * step.confidence)
        
        return sum(weights) / len(weights)
    
    @staticmethod
    def find_bottlenecks(steps: List[ReasoningNode], graph: ReasoningGraph) -> List[str]:
        """Identifies nodes that represent logical bottlenecks with low confidence.

        Args:
            steps: List of nodes in the chain.
            graph: The ReasoningGraph context.

        Returns:
            A list of node IDs identified as bottlenecks.
        """
        bottlenecks = []
        
        for step in steps:
            node = graph.nodes.get(step.node_id)
            if node and len(node.antecedents) > 2 and node.confidence < 0.5:
                bottlenecks.append(node.node_id)
        
        return bottlenecks


class FallbackReasoningEngine:
    """
    Fallback reasoning with graceful degradation.
    """
    
    def __init__(self, max_fallbacks: int = 3):
        """Initializes the FallbackReasoningEngine.

        Args:
            max_fallbacks: Maximum number of fallback strategies to attempt. Defaults to 3.
        """
        self.max_fallbacks = max_fallbacks
        self.fallback_strategies: List[Callable] = []
    
    def register_fallback(self, strategy: Callable[[Dict], Any]) -> None:
        """Registers a new strategy to be used as a fallback.

        Args:
            strategy: A callable that accepts a context and returns a result.
        """
        self.fallback_strategies.append(strategy)
    
    def execute_with_fallback(self, context: Dict[str, Any], 
                            primary_fn: Callable[[Dict], Any]) -> Tuple[Any, bool]:
        """Executes a primary function and sequentially attempts fallbacks if it fails.

        Args:
            context: Context dictionary to pass to the reasoning functions.
            primary_fn: The main reasoning function to execute first.

        Returns:
            A tuple containing (result, used_fallback).
        """
        try:
            result = primary_fn(context)
            return result, False
        except Exception as e:
            print(f"Primary reasoning failed: {e}")
            
            for i, fallback in enumerate(self.fallback_strategies[:self.max_fallbacks]):
                try:
                    result = fallback(context)
                    print(f"Fallback {i+1} succeeded")
                    return result, True
                except Exception as e2:
                    print(f"Fallback {i+1} failed: {e2}")
                    continue
            
            return None, True
    
    def get_consensus(self, results: List[Any]) -> Optional[Any]:
        """Derives a single consensus result from multiple reasoning outputs.

        Args:
            results: A list of results from different reasoning attempts.

        Returns:
            The consensus result, or the highest confidence result if available.
        """
        if not results:
            return None
        
        if len(results) == 1:
            return results[0]
        
        if all(r == results[0] for r in results):
            return results[0]
        
        conf_values = []
        for r in results:
            if isinstance(r, dict) and 'confidence' in r:
                conf_values.append(r['confidence'])
        
        if conf_values:
            best_idx = conf_values.index(max(conf_values))
            return results[best_idx]
        
        return results[0]
