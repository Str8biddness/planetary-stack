"""Compatibility exports for the real Red Team implementation in reasoning."""

from reasoning.breach.breach_engine import (
    AttackCategory,
    AttackSeverity,
    AttackVector,
    BreachEngine,
)
from reasoning.breach.brute_simulator import (
    AttackPattern,
    BruteForceSimulator,
    CredentialPressureConfig,
    LoginAttempt,
    TrafficGenerator,
)
from reasoning.breach.exploit_modeler import (
    AttackNode,
    AttackPhase,
    AttackTree,
    ExploitModeler,
)
from reasoning.breach.memory_matcher import (
    MemoryPatternMatcher,
    VulnerabilitySignature,
    VulnType,
)

__all__ = [
    "AttackCategory",
    "AttackNode",
    "AttackPattern",
    "AttackPhase",
    "AttackSeverity",
    "AttackTree",
    "AttackVector",
    "BreachEngine",
    "BruteForceSimulator",
    "CredentialPressureConfig",
    "ExploitModeler",
    "LoginAttempt",
    "MemoryPatternMatcher",
    "TrafficGenerator",
    "VulnerabilitySignature",
    "VulnType",
]
