import os
import time
import requests
from typing import Tuple, Dict, Any, Union

from packages.core.chal.frames import CognitiveTask, TelemetryRecord
from packages.core.sllm_coordinator import SllmCoordinator

class LLMGenerationDevice(SllmCoordinator):
    """
    Wraps Ollama as a CHAL cognitive device.
    Fulfills C-201 Callout:
    - Input: CognitiveTask -> output text + telemetry
    - Real Ollama call
    - On timeout/error: returns a structured error frame (never a fabricated string).
    - Honors budget_ms. Emits TelemetryRecord every call.
    """
    # Who the model is. Establishes identity so it knows it is Synthesus (not a
    # generic Llama, and not the old 'Ghostkey' default). Overridable via env.
    DEFAULT_SYSTEM_PROMPT = (
        "You are Synthesus, a private AI that runs entirely on the user's own machine — "
        "nothing they do leaves their computer. You can ground your answers in the user's "
        "own files and documents through their expansion drive. Be clear, direct, and "
        "genuinely helpful. When knowledge context is provided, ground your answer in it "
        "and do not invent facts; if you don't know, say so plainly. Your name is "
        "Synthesus — never claim to be any other assistant, model, or persona."
    )

    def __init__(self, engine=None):
        super().__init__(engine)
        self.model_name = os.getenv("SYNTHESUS_MODEL", "llama3.2:3b")
        self.api_url = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/generate")
        self.system_prompt = os.getenv("SYNTHESUS_SYSTEM_PROMPT", self.DEFAULT_SYSTEM_PROMPT)

    def generate(self, task: CognitiveTask, system_prompt: str = None) -> Tuple[Union[str, Dict[str, Any]], TelemetryRecord]:
        start_time = time.time()
        budget_ms = task.budgets.get("latency_ms", 60000.0)
        timeout_s = budget_ms / 1000.0

        try:
            import json
            settings_path = os.path.join(
                os.environ.get("SYNTHESUS_HOME", os.path.expanduser("~/.local/share/synthesus")),
                "settings.json"
            )
            settings = {}
            if os.path.exists(settings_path):
                with open(settings_path, "r") as f:
                    settings = json.load(f)
            
            provider = os.getenv("SYNTHESUS_LLM_PROVIDER") or settings.get("llm_provider", "ollama")
            model_name = settings.get("model") or self.model_name
            api_key = settings.get("api_key", "").strip()
            
            sys_prompt = system_prompt or self.system_prompt
            prompt = task.query

            if provider != "ollama" and not api_key:
                raise ValueError(f"API key missing for provider: {provider}")

            if provider == "openai":
                url = "https://api.openai.com/v1/chat/completions"
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                payload = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": prompt}
                    ]
                }
                response = requests.post(url, headers=headers, json=payload, timeout=timeout_s)
                response.raise_for_status()
                output = response.json()["choices"][0]["message"]["content"]
            elif provider == "anthropic":
                url = "https://api.anthropic.com/v1/messages"
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                }
                payload = {
                    "model": model_name,
                    "max_tokens": 4096,
                    "system": sys_prompt,
                    "messages": [{"role": "user", "content": prompt}]
                }
                response = requests.post(url, headers=headers, json=payload, timeout=timeout_s)
                response.raise_for_status()
                output = response.json()["content"][0]["text"]
            elif provider == "gemini":
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
                payload = {
                    "systemInstruction": {"parts": [{"text": sys_prompt}]},
                    "contents": [{"parts": [{"text": prompt}]}]
                }
                response = requests.post(url, json=payload, timeout=timeout_s)
                response.raise_for_status()
                output = response.json()["candidates"][0]["content"]["parts"][0]["text"]
            else: # ollama
                payload = {
                    "model": model_name,
                    "system": sys_prompt,
                    "prompt": prompt,
                    "stream": False
                }
                response = requests.post(self.api_url, json=payload, timeout=timeout_s)
                response.raise_for_status()
                output = response.json().get("response", "")
            
            latency_ms = (time.time() - start_time) * 1000.0
            telemetry = TelemetryRecord(
                trace_id=task.trace_id,
                component="llm_device",
                latency_ms=latency_ms,
                confidence=0.9,
                metadata={"model": model_name, "provider": provider, "status": "success"}
            )
            return output, telemetry
            
        except requests.exceptions.Timeout:
            latency_ms = (time.time() - start_time) * 1000.0
            error_frame = {
                "error": "TimeoutError",
                "message": f"{provider} generation exceeded budget of {budget_ms}ms"
            }
            telemetry = TelemetryRecord(
                trace_id=task.trace_id,
                component="llm_device",
                latency_ms=latency_ms,
                confidence=0.0,
                fallback_used=True,
                metadata={"model": model_name if 'model_name' in locals() else self.model_name, "status": "timeout"}
            )
            return error_frame, telemetry
            
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000.0
            error_frame = {
                "error": type(e).__name__,
                "message": str(e)
            }
            telemetry = TelemetryRecord(
                trace_id=task.trace_id,
                component="llm_device",
                latency_ms=latency_ms,
                confidence=0.0,
                fallback_used=True,
                metadata={"model": model_name if 'model_name' in locals() else self.model_name, "status": "error"}
            )
            return error_frame, telemetry
