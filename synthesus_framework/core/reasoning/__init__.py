"""
Synthesus Reasoning Layer - Core reasoning components

This module provides the Python-based reasoning layer for Synthesus 3.0,
including task decomposition, domain routing, answer verification, and
cross-domain synthesis.

Components:
- planner: TaskDecomposer, DomainRouter, CriticVerifier
- reranker: CrossEncoderReranker
- synthesizer: CrossDomainSynthesizer
"""

from core.reasoning.planner import TaskDecomposer, DomainRouter, CriticVerifier
from core.reasoning.reranker import CrossEncoderReranker
from core.reasoning.synthesizer import CrossDomainSynthesizer

__all__ = [
    "TaskDecomposer",
    "DomainRouter",
    "CriticVerifier",
    "CrossEncoderReranker",
    "CrossDomainSynthesizer",
]
