"""Re-export real LootBalancer from core/ (core/ml was a pass stub)."""
from loot_balancer import LootBalancer  # noqa: F401

__all__ = ["LootBalancer"]
