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

        # Get budget (default 8000ms if not specified)
        # Default generous enough to survive an Ollama COLD start (model load can take
        # ~12s+ on first call / after idle unload). An 8s default timed out on cold
        # models and silently dropped to the seed realizer — the "canned responses" bug.
        budget_ms = task.budgets.get("latency_ms", 60000.0)
        timeout_s = budget_ms / 1000.0

        try:
            payload = {
                "model": self.model_name,
                # Composed per-turn system prompt when supplied by the realizer;
                # else the static Synthesus identity.
                "system": system_prompt or self.system_prompt,
                "prompt": task.query,
                "stream": False
            }
            
            response = requests.post(self.api_url, json=payload, timeout=timeout_s)
            response.raise_for_status()
            
            data = response.json()
            output = data.get("response", "")
            
            latency_ms = (time.time() - start_time) * 1000.0
            telemetry = TelemetryRecord(
                trace_id=task.trace_id,
                component="llm_device",
                latency_ms=latency_ms,
                confidence=0.9,
                metadata={"model": self.model_name, "status": "success"}
            )
            return output, telemetry
            
        except requests.exceptions.Timeout:
            latency_ms = (time.time() - start_time) * 1000.0
            error_frame = {
                "error": "TimeoutError",
                "message": f"Ollama generation exceeded budget of {budget_ms}ms"
            }
            telemetry = TelemetryRecord(
                trace_id=task.trace_id,
                component="llm_device",
                latency_ms=latency_ms,
                confidence=0.0,
                fallback_used=True,
                metadata={"model": self.model_name, "status": "timeout"}
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
                metadata={"model": self.model_name, "status": "error"}
            )
            return error_frame, telemetry
