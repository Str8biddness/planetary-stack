# accelerators/adapter.py

from abc import ABC, abstractmethod
from typing import Dict, Any

class AcceleratorAdapter(ABC):
    """
    Base protocol for accelerator adapters (CPU, GPU, remote).
    """

    @abstractmethod
    def describe(self) -> Dict[str, Any]:
        """Return metadata: id, type, max_context, tokens_per_second_estimate, cost_hint, etc."""
        pass

    @abstractmethod
    def run_inference(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Run inference: request has model_name, prompt, params. Return response + metrics."""
        pass

class CPUOnlyAdapter(AcceleratorAdapter):
    """
    Dummy adapter that delegates to local CPU inference (existing Synthesus logic).
    """

    def __init__(self, local_inference_func):
        self.local_inference_func = local_inference_func

    def describe(self) -> Dict[str, Any]:
        return {
            "id": "cpu_local",
            "type": "cpu",
            "max_context": 4096,  # Placeholder
            "tokens_per_second_estimate": 10,  # Placeholder
            "cost_hint": 0,  # Free
        }

    def run_inference(self, request: Dict[str, Any]) -> Dict[str, Any]:
        # Delegate to existing local inference
        response = self.local_inference_func(request["prompt"], request.get("params", {}))
        return {
            "response": response,
            "metrics": {
                "latency_ms": 1000,  # Placeholder
                "tokens_used": len(request["prompt"].split()),  # Rough estimate
            }
        }
