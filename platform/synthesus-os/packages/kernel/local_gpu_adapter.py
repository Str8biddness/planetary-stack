# accelerators/local_gpu_adapter.py

import requests
import time
from typing import Dict, Any
from .adapter import AcceleratorAdapter

class LocalGpuAdapter(AcceleratorAdapter):
    """
    AcceleratorAdapter for local GPU endpoint via HTTP.
    """

    def __init__(self, endpoint_url: str, model_name: str = None):
        self.endpoint_url = endpoint_url
        self.model_name = model_name or "local_gpu_model"
        self.max_context = 4096  # Placeholder
        self.tokens_per_second_estimate = 100  # Placeholder for GPU

    def describe(self) -> Dict[str, Any]:
        return {
            "id": "local_gpu",
            "type": "local_gpu",
            "endpoint_url": self.endpoint_url[:20] + "..." if self.endpoint_url else None,  # redact
            "model_name": self.model_name,
            "max_context": self.max_context,
            "tokens_per_second_estimate": self.tokens_per_second_estimate,
            "cost_hint": 0.01,  # Placeholder for local cost
        }

    def run_inference(self, request: Dict[str, Any]) -> Dict[str, Any]:
        try:
            payload = {
                "prompt": request.get("prompt", ""),
                "max_tokens": request.get("max_tokens", 100),
                "temperature": request.get("temperature", 0.7),
                "model": self.model_name,
            }
            headers = {"Content-Type": "application/json"}
            start_time = time.time()
            response = requests.post(self.endpoint_url, json=payload, headers=headers, timeout=60)
            latency_ms = (time.time() - start_time) * 1000

            if response.status_code == 200:
                data = response.json()
                return {
                    "response": data.get("text", ""),
                    "metrics": {
                        "latency_ms": round(latency_ms, 2),
                        "tokens_used": data.get("usage", {}).get("total_tokens", len(payload["prompt"].split())),
                    }
                }
            else:
                return {"error": f"Local GPU API error: {response.status_code} - {response.text}"}
        except Exception as e:
            return {"error": f"Local GPU network or request error: {str(e)}"}

    def is_healthy(self) -> bool:
        # Optional probe: ping /health if available, else assume healthy
        try:
            response = requests.get(self.endpoint_url.replace("/generate", "/health"), timeout=5)
            return response.status_code == 200
        except:
            return True  # No-op: assume healthy if URL set
