from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any

class Device(ABC):
    """Base class for all AIVM Virtual Devices."""
    
    @abstractmethod
    def snapshot(self) -> bytes:
        """Lose-less capture of device state."""
        pass

    @abstractmethod
    def restore(self, blob: bytes) -> None:
        """Deterministic state restoration."""
        pass

    @abstractmethod
    def fingerprint(self) -> str:
        """Content hash of current device state."""
        pass
