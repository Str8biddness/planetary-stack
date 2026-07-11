"""Back-compat: PatternLM implementation lives in ml/__init__.py (historical layout)."""
from __future__ import annotations

import importlib

# ml package __init__ defines the real PatternLM class.
PatternLM = importlib.import_module("ml").PatternLM  # type: ignore

__all__ = ["PatternLM"]
