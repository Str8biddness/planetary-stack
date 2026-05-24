"""
Breach Module - Red Team Adversarial System for Synthesus 4.0

This module implements the Red Team (Breach Persona) architecture as defined in AGENTS.md.
It provides adversarial discovery, vulnerability scanning, exploit modeling, and
brute-force simulation capabilities for automated security hardening.

Modules:
    - breach_engine: Core Red Team orchestration and abductive reasoning
    - memory_matcher: Sandbox memory pattern scanning for insecure primitives
    - exploit_modeler: Attack tree generation and vulnerability path analysis
    - brute_simulator: Credential pressure and timing attack training

Architecture:
    Red Team (Breach) -> EmulationTool (Sandbox) -> Blue Team (Ghostkey Sentinel)
"""

from .breach_engine import BreachEngine, AttackVector
from .memory_matcher import MemoryPatternMatcher, VulnerabilitySignature
from .exploit_modeler import ExploitModeler, AttackTree, AttackNode
from .brute_simulator import BruteForceSimulator, CredentialPressureConfig

__all__ = [
    "BreachEngine",
    "AttackVector",
    "MemoryPatternMatcher",
    "VulnerabilitySignature",
    "ExploitModeler",
    "AttackTree",
    "AttackNode",
    "BruteForceSimulator",
    "CredentialPressureConfig",
]
