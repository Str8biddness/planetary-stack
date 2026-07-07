"""
KAL Domain Partition Metadata — V4

Defines the structured metadata models for each namespace partition.
These are validation/typing models that standardize how metadata is
tagged and filtered in KAL queries. They don't change storage — they
define the shape of the metadata payload within KalKnowledgeNode.

Partition types:
  - GameLorePartition: faction, world_state_flag, temporal_epoch
  - ArchitectDirectivesPartition: autonomy_level, tool_whitelist, safety_override
  - CharacterGenomePartition: archetype, relationship_trust_gate, emotion_trigger
  - ReasoningRulesPartition: synthetic_core_priority, requires_escalation
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────
# Autonomy levels (for Architect Directives)
# ──────────────────────────────────────────────────

class AutonomyLevel(str, Enum):
    ADVISOR = "ADVISOR"
    COPILOT = "COPILOT"
    AUTOPILOT = "AUTOPILOT"


# ──────────────────────────────────────────────────
# Partition models
# ──────────────────────────────────────────────────

class GameLorePartition(BaseModel):
    """Metadata for game lore knowledge nodes."""
    faction: str = ""
    world_state_flag: str = ""
    temporal_epoch: int = 0


class ArchitectDirectivesPartition(BaseModel):
    """Metadata for architect directive nodes (safety, autonomy, tools)."""
    autonomy_level: AutonomyLevel = AutonomyLevel.ADVISOR
    tool_whitelist: List[str] = Field(default_factory=list)
    safety_override: bool = False


class CharacterGenomePartition(BaseModel):
    """Metadata for character genome nodes."""
    archetype: str = ""
    relationship_trust_gate: float = 0.0
    emotion_trigger: str = ""


class ReasoningRulesPartition(BaseModel):
    """Metadata for reasoning rule nodes."""
    synthetic_core_priority: int = 0
    requires_escalation: bool = False


# ──────────────────────────────────────────────────
# Partition registry
# ──────────────────────────────────────────────────

PARTITION_MODELS: Dict[str, type] = {
    "game_lore": GameLorePartition,
    "architect_directives": ArchitectDirectivesPartition,
    "character_genome": CharacterGenomePartition,
    "reasoning_rules": ReasoningRulesPartition,
}


def validate_partition_metadata(namespace: str, metadata: Dict[str, Any]) -> Optional[BaseModel]:
    """Validate metadata against the partition model for a namespace.

    Returns the validated model instance, or None if namespace has no partition model.
    """
    model_cls = PARTITION_MODELS.get(namespace)
    if model_cls is None:
        return None
    # Extract only partition-specific fields to avoid validation errors
    partition_fields = {k: v for k, v in metadata.items() if k in model_cls.model_fields}
    return model_cls(**partition_fields)
