"""
KAL — Knowledge Abstraction Layer (V4)
Synthesus internal subsystem for unified knowledge retrieval.
"""

from .schemas import (
    KalQuery,
    KalKnowledgeNode,
    KalResultItem,  # V3 compat alias
    KalResult,
    KalMode,
    KalNamespace,
)
from .service import KalService
from .client import KalClient
from .partitions import (
    GameLorePartition,
    ArchitectDirectivesPartition,
    CharacterGenomePartition,
    ReasoningRulesPartition,
    AutonomyLevel,
)

__all__ = [
    # Schemas
    "KalQuery",
    "KalKnowledgeNode",
    "KalResultItem",
    "KalResult",
    "KalMode",
    "KalNamespace",
    # Service / Client
    "KalService",
    "KalClient",
    # Partitions
    "GameLorePartition",
    "ArchitectDirectivesPartition",
    "CharacterGenomePartition",
    "ReasoningRulesPartition",
    "AutonomyLevel",
]
