"""Synthesus 2.0 Core Package"""

# Lazy-safe imports — some submodules have broken deps in the repo.
# We import only what's needed at module level and let the rest
# fail gracefully when first accessed.

try:
    from .rag_pipeline import RAGPipeline
except Exception:
    RAGPipeline = None

try:
    from .hemisphere_bridge import HemisphereBridge
except Exception:
    HemisphereBridge = None

# These may fail due to missing deps (Character class, ELSBridge, etc.)
# so we wrap them in try/except to avoid crashing the API gateway.
try:
    from .pattern_engine import PatternEngine
except Exception:
    PatternEngine = None

try:
    from .memory_store import MemoryStore
except Exception:
    MemoryStore = None

try:
    from .reasoning_core import ReasoningCore
except Exception:
    ReasoningCore = None

try:
    from .character_factory import CharacterFactory
except Exception:
    CharacterFactory = None

try:
    from .synth_runtime import SynthRuntime
except Exception:
    SynthRuntime = None

__version__ = "2.0.0"
__all__ = [
    "SynthRuntime", "ReasoningCore", "RAGPipeline",
    "PatternEngine", "MemoryStore", "HemisphereBridge",
    "CharacterFactory"
]
