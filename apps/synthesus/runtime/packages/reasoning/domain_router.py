"""
Domain Router - Routes Sub-Tasks to Appropriate Domain Handlers

Position in pipeline: After query decomposition, the domain router determines
which domain handlers should process each sub-task.
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)

from .utils import classify_domain

class DomainType(Enum):
    """Enumeration of supported domain types in Synthesus."""
    CHARACTER = "character"
    WORLD = "world"
    STRATEGY = "strategy"
    NARRATIVE = "narrative"
    DIALOGUE = "dialogue"
    EMOTION = "emotion"
    KNOWLEDGE = "knowledge"
    CODE = "code"
    MATH = "math"
    GENERAL = "general"

@dataclass
class RouteResult:
    task_id: str
    primary_domain: DomainType
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class RoutingExecutionPlan:
    routes: List[RouteResult]
    parallel_groups: List[List[str]]  # Lists of task_ids that can run in parallel
    execution_plan: Dict[str, Any] = field(default_factory=dict)

class DomainRouter:
    """
    Routes sub-tasks to appropriate domain handlers.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}
    
    def route(
        self,
        tasks: List[Any], # List[DecomposedTask]
        context: Optional[Dict[str, Any]] = None
    ) -> RoutingExecutionPlan:
        routes = []
        for task in tasks:
            domain_str = classify_domain(task.query)
            try:
                domain = DomainType(domain_str)
            except ValueError:
                domain = DomainType.GENERAL
            
            routes.append(RouteResult(
                task_id=task.task_id,
                primary_domain=domain,
                confidence=0.8
            ))
        
        groups = self._compute_parallel_groups(routes, tasks)
        return RoutingExecutionPlan(routes=routes, parallel_groups=groups)

    def _compute_parallel_groups(self, routes: List[RouteResult], tasks: List[Any]) -> List[List[str]]:
        # Map tasks for lookup
        task_map = {t.task_id: t for t in tasks}
        groups = []
        processed = set()
        
        # Max iterations to prevent infinite loops (safety)
        max_iters = len(tasks) + 1
        iter_count = 0
        
        while len(processed) < len(tasks) and iter_count < max_iters:
            iter_count += 1
            current_group = []
            
            for task in tasks:
                if task.task_id in processed:
                    continue
                
                # Check if all dependencies are satisfied
                # A task can run if its dependencies have been processed in previous groups
                deps_satisfied = True
                for dep in task.dependencies:
                    if dep not in processed:
                        deps_satisfied = False
                        break
                
                if deps_satisfied:
                    current_group.append(task.task_id)
            
            if not current_group:
                # We have remaining tasks but none can be scheduled (circular dependency)
                remaining = [t.task_id for t in tasks if t.task_id not in processed]
                if remaining:
                    logger.warning(f"Circular dependency detected in tasks: {remaining}. Forcing parallel execution.")
                    groups.append(remaining)
                break
                
            groups.append(current_group)
            processed.update(current_group)
            
        return groups
