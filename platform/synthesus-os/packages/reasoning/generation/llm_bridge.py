import logging
import json
import httpx
import asyncio
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class LLMBridge:
    """
    Bridge to a local CPU-based LLM server (like llama.cpp or Ollama).
    Provides the 'Voice' for the Quadbrain Executive.
    """
    def __init__(self, api_url: str = "http://localhost:8080/v1"):
        self.api_url = api_url
        self.client = httpx.AsyncClient(timeout=60.0)

    async def generate(self, prompt: str, system_prompt: str = "You are Ghostkey, a sovereign AI sentinel.") -> str:
        """Generates a response using the local LLM."""
        try:
            payload = {
                "model": "local-model",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 150
            }
            
            response = await self.client.post(f"{self.api_url}/chat/completions", json=payload)
            if response.status_code == 200:
                data = response.json()
                return data['choices'][0]['message']['content'].strip()
            else:
                logger.error(f"LLM API Error: {response.status_code} - {response.text}")
                return ""
        except Exception as e:
            logger.error(f"LLM Bridge Error: {e}")
            return ""

    async def close(self):
        await self.client.aclose()

class FallbackGenerator:
    """Deterministic fallback if the LLM server is offline."""
    def generate(self, plan: Dict[str, Any]) -> str:
        summary = plan.get("summary", "System status nominal.")
        explanations = plan.get("key_points", [])
        
        response = f"Ghostkey Logic: {summary}"
        if explanations:
            response += "\nDetailed reasoning:\n- " + "\n- ".join(explanations)
        return response
