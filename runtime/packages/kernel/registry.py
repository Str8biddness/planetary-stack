# accelerators/registry.py

from typing import List, Dict, Any, Optional
from .adapter import AcceleratorAdapter

class AcceleratorRegistry:
    """
    Registry for accelerator adapters.
    """

    def __init__(self):
        self.adapters: List[AcceleratorAdapter] = []

    def register_adapter(self, adapter: AcceleratorAdapter):
        self.adapters.append(adapter)

    def list_accelerators(self) -> List[Dict[str, Any]]:
        return [adapter.describe() for adapter in self.adapters]

    def get_best_accelerator(self, criteria: Dict[str, Any]) -> Optional[AcceleratorAdapter]:
        # For now, just return the first adapter (CPU-only)
        if self.adapters:
            return self.adapters[0]
        return None
