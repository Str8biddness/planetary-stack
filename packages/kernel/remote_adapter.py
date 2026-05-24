# accelerators/remote_adapter.py

import requests
import time
from typing import Dict, Any
from .adapter import AcceleratorAdapter

class RemoteAdapter(AcceleratorAdapter):
    """
    AcceleratorAdapter for remote model endpoints via HTTP.
    """

    def __init__(self, id: str, endpoint_url: str, api_key: str = None, model_name: str = None, max_context: int = 4096, tokens_per_second_estimate: int = 50):
        self.id = id
        self.endpoint_url = endpoint_url
        self.api_key = api_key
        self.model_name = model_name or "default"
        self.max_context = max_context
        self.tokens_per_second_estimate = tokens_per_second_estimate

    def describe(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": "remote",
            "endpoint_url": self.endpoint_url[:20] + "..." if self.endpoint_url else None,  # redact
            "model_name": self.model_name,
            "max_context": self.max_context,
            "tokens_per_second_estimate": self.tokens_per_second_estimate,
            "cost_hint": 0.01,  # Placeholder for remote cost
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
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            start_time = time.time()
            response = requests.post(self.endpoint_url, json=payload, headers=headers, timeout=30)
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
                return {"error": f"Remote API error: {response.status_code} - {response.text}"}
        except Exception as e:
            return {"error": f"Network or request error: {str(e)}"}
