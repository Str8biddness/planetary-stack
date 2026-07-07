"""
Query Decomposer - Task Decomposition for Complex Reasoning Queries

Position in pipeline: Entry point of the reasoning layer, responsible for
breaking down complex multi-faceted queries into parallelizable sub-tasks.

Related components:
- core/reasoning/planner.py (parent module containing TaskDecomposer)
- core/reasoning/domain_router.py (routes decomposed sub-tasks to domains)
- core/reasoning/synthesizer.py (merges results from sub-tasks)
"""

from __future__ import annotations

import re

from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
import uuid

from .utils import DomainKeywords, classify_domain

@dataclass
class DecomposedTask:
    """
    Represents a single sub-task derived from query decomposition.
    """
    task_id: str
    description: str
    domain: str
    query: str
    priority: int = 0
    dependencies: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class DecompositionResult:
    """
    Container for the result of query decomposition.
    """
    original_query: str
    sub_tasks: List[DecomposedTask]
    strategy: str
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

class QueryDecomposer:
    """
    Decomposes complex, multi-faceted queries into parallelizable sub-tasks.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}
        self.max_sub_tasks = self.config.get("max_sub_tasks", 10)
        self.strategy = self.config.get("decomposition_strategy", "parallel")
        self.complexity_threshold = self.config.get("complexity_threshold", 0.5)
        self._decomposition_history: List[DecompositionResult] = []
    
    def decompose(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None
    ) -> DecompositionResult:
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")
        
        context = context or {}
        complexity = self._calculate_complexity(query)
        
        if complexity < self.complexity_threshold:
            # Single-task decomposition
            task_id = f"task_{uuid.uuid4().hex[:8]}"
            sub_tasks = [
                DecomposedTask(
                    task_id=task_id,
                    description=f"Handle query: {query}",
                    domain=classify_domain(query),
                    query=query,
                    priority=1,
                )
            ]
            result = DecompositionResult(
                original_query=query,
                sub_tasks=sub_tasks,
                strategy="single",
                confidence=0.9,
                metadata={"complexity": complexity}
            )
        else:
            # Multi-task decomposition
            sub_tasks = self._rule_based_decompose(query, context)
            if len(sub_tasks) > self.max_sub_tasks:
                sub_tasks = sub_tasks[: self.max_sub_tasks]
            
            result = DecompositionResult(
                original_query=query,
                sub_tasks=sub_tasks,
                strategy=self.strategy,
                confidence=min(0.5 + (complexity * 0.3), 0.95),
                metadata={"complexity": complexity, "task_count": len(sub_tasks)},
            )
        
        self._decomposition_history.append(result)
        return result
    
    def _calculate_complexity(self, query: str) -> float:
        score = 0.0
        q = query.lower()
        
        # Structure factors
        if "?" in q: score += 0.2
        if " and " in q or " or " in q or " but " in q: score += 0.3
        if len(q.split()) > 20: score += 0.3
        
        # Domain factors
        domain_hits = sum(1 for d, kws in DomainKeywords.KEYWORDS.items() if any(kw in q for kw in kws))
        score += min(domain_hits * 0.15, 0.45)
        
        return min(score, 1.0)
    
    def _rule_based_decompose(
        self, query: str, context: Optional[Dict[str, Any]] = None
    ) -> List[DecomposedTask]:
        sub_tasks = []
        segments = self._split_query_segments(query)
        
        for i, segment in enumerate(segments):
            if not segment.strip(): continue
            task_id = f"task_{uuid.uuid4().hex[:8]}"
            sub_tasks.append(
                DecomposedTask(
                    task_id=task_id,
                    description=segment[:100],
                    domain=classify_domain(segment),
                    query=segment,
                    priority=i,
                )
            )
        return sub_tasks

    def _split_query_segments(self, query: str) -> List[str]:
        # Split on sentence boundaries and common conjunctions
        delimiters = r"[.!?]+|\b(?:and|but|or|then|also)\b"
        segments = re.split(delimiters, query, flags=re.IGNORECASE)
        return [s.strip() for s in segments if s.strip()]
