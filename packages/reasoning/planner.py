"""
Planner - Task Decomposition and Routing for Synthesus Reasoning Pipeline

Position in pipeline: This module sits at the entry point of the reasoning layer,
coordinating sub-components to process queries and synthesize answers.
"""

from __future__ import annotations

import logging
from typing import Optional, List, Dict, Any

from .query_decomposer import QueryDecomposer, DecompositionResult
from .domain_router import DomainRouter, RoutingExecutionPlan
from .verifier import AnswerVerifier, VerificationResult, VerificationStatus
from .synthesizer import CrossDomainSynthesizer

logger = logging.getLogger(__name__)

class Planner:
    """
    Main orchestrator for the Synthesus Reasoning Layer.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}
        self.decomposer = QueryDecomposer(self.config.get("decomposer"))
        self.router = DomainRouter(self.config.get("router"))
        self.verifier = AnswerVerifier(self.config.get("verifier"))
        self.synthesizer = CrossDomainSynthesizer(self.config.get("synthesizer"))

    def plan(self, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Produce a full reasoning plan for a query.
        """
        decomposition = self.decomposer.decompose(query, context)
        routing = self.router.route(decomposition.sub_tasks, context)
        
        return {
            "query": query,
            "decomposition": decomposition,
            "routing": routing,
        }

    def execute_and_verify(
        self, 
        query: str, 
        domain_contexts: Dict[str, List[str]], 
        max_revisions: int = 2
    ) -> Dict[str, Any]:
        """
        Synthesize an answer and verify it, with optional revisions.
        """
        answer = self.synthesizer.synthesize(domain_contexts, query)
        
        for i in range(max_revisions + 1):
            # In a real system, context for verification might come from RAG
            flat_context = [item for sublist in domain_contexts.values() for item in sublist]
            result = self.verifier.verify(answer, query, flat_context, revision_count=i)
            
            if result.status == VerificationStatus.PASSED or i == max_revisions:
                break
            
            answer = self.verifier.generate_revision(answer, result)
            
        return {
            "answer": answer,
            "verification": result
        }

# Backward compatibility wrappers
class TaskDecomposer(QueryDecomposer):
    def decompose_legacy(self, query: str) -> List[Dict[str, Any]]:
        result = self.decompose(query)
        return [
            {
                "task_id": t.task_id,
                "description": t.description,
                "domain_hint": t.domain,
                "dependencies": t.dependencies,
                "priority": t.priority,
            }
            for t in result.sub_tasks
        ]

class CriticVerifier(AnswerVerifier):
    def verify_legacy(self, answer: str, context: List[str], query: str) -> Dict[str, Any]:
        result = self.verify(answer, query, context)
        return {
            "is_valid": result.status == VerificationStatus.PASSED,
            "confidence_score": result.score,
            "critique": "; ".join(i.description for i in result.issues),
            "revision_hints": [i.suggestion for i in result.issues]
        }
