"""Re-export real DialogueRanker from core/ (core/ml was a pass stub)."""
from __future__ import annotations

try:
    from core.dialogue_ranker import DialogueRanker  # type: ignore
except ModuleNotFoundError:
    from ..dialogue_ranker import DialogueRanker  # type: ignore

__all__ = ["DialogueRanker"]
