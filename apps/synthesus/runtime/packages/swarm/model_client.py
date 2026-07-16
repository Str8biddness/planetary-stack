"""Shared single-model Ollama client — ONE resident base, many prompts.

Never loads a second model. All experts call the same generate endpoint with
different system prompts (cheap deltas).
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import requests

logger = logging.getLogger(__name__)


@dataclass
class GenerateResult:
    text: str
    model_id: str
    latency_ms: float
    degraded: bool = False
    degrade_reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class SharedOllamaClient:
    """One base model on one server. Expert identity = system prompt only."""

    def __init__(
        self,
        *,
        base_model: str | None = None,
        api_url: str | None = None,
        default_timeout_s: float = 120.0,
    ) -> None:
        self.base_model = (
            base_model
            or os.environ.get("SYNTHESUS_MODEL")
            or os.environ.get("OLLAMA_MODEL")
            or "llama3.2:3b"
        )
        self.api_url = (
            api_url
            or os.environ.get("OLLAMA_API_URL")
            or "http://127.0.0.1:11434/api/generate"
        )
        self.default_timeout_s = default_timeout_s
        self._call_count = 0
        self._models_requested: set[str] = set()

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def models_requested(self) -> set[str]:
        return set(self._models_requested)

    def generate(
        self,
        *,
        prompt: str,
        system_prompt: str,
        timeout_s: float | None = None,
        max_tokens: int | None = None,
    ) -> GenerateResult:
        """Generate with the shared base model. Always uses self.base_model only."""
        model = self.base_model
        self._models_requested.add(model)
        self._call_count += 1
        timeout = timeout_s if timeout_s is not None else self.default_timeout_s

        # Honor SYNTHESUS_FAST_MODE for shorter generations.
        fast = os.environ.get("SYNTHESUS_FAST_MODE", "1") != "0"
        options: dict[str, Any] = {}
        if max_tokens is not None:
            options["num_predict"] = int(max_tokens)
        elif fast:
            options["num_predict"] = 128

        payload: dict[str, Any] = {
            "model": model,
            "system": system_prompt,
            "prompt": prompt,
            "stream": False,
        }
        if options:
            payload["options"] = options

        t0 = time.time()
        try:
            resp = requests.post(self.api_url, json=payload, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            text = str(data.get("response") or "").strip()
            latency = (time.time() - t0) * 1000.0
            if not text:
                return GenerateResult(
                    text="",
                    model_id=model,
                    latency_ms=latency,
                    degraded=True,
                    degrade_reason="empty_model_response",
                    raw=data if isinstance(data, dict) else {},
                )
            return GenerateResult(
                text=text,
                model_id=model,
                latency_ms=latency,
                degraded=False,
                raw=data if isinstance(data, dict) else {},
            )
        except requests.exceptions.Timeout:
            latency = (time.time() - t0) * 1000.0
            logger.warning("shared model timeout after %.0fms model=%s", latency, model)
            return GenerateResult(
                text="",
                model_id=model,
                latency_ms=latency,
                degraded=True,
                degrade_reason="model_timeout",
            )
        except Exception as e:
            latency = (time.time() - t0) * 1000.0
            logger.warning("shared model error: %s", e)
            return GenerateResult(
                text="",
                model_id=model,
                latency_ms=latency,
                degraded=True,
                degrade_reason=f"model_error:{type(e).__name__}:{e}",
            )
