"""
KAL Backend — Abstract base class for knowledge retrieval backends.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..schemas import KalQuery, KalResult


class KalBackend(ABC):
    """Interface that all KAL backends must implement."""

    @abstractmethod
    async def query(self, kal_query: KalQuery) -> KalResult:
        """Execute a knowledge retrieval query and return results."""
        ...
