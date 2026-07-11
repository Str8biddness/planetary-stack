"""Re-export real LootBalancer from core/ (core/ml was a pass stub)."""
from __future__ import annotations

try:
    from core.loot_balancer import LootBalancer  # type: ignore
except ModuleNotFoundError:
    from ..loot_balancer import LootBalancer  # type: ignore

__all__ = ["LootBalancer"]
