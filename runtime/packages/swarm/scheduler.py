"""SW-2 — Swarm scheduler: one model server, fan-out expert deltas.

Shares ONE SharedOllamaClient / base model. Missing experts degrade loudly —
never fabricate persona output.

v1 delta semantics (honest boundary):
  - Behavioral delta = system_prompt + retrieval namespace (cheap, always applied).
  - LoRA / weight adapter_ref is validated as DATA only (base-compat, no exec).
  - Adapters are NOT hot-swapped into Ollama in this revision; ExpertResult
    records adapter_applied=False and adapter_status=validated_not_applied
    when the manifest exists. Missing adapters degrade that expert only.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable, Mapping, Optional, Sequence

from .adapters.loader import AdapterLoader
from .model_client import SharedOllamaClient
from .registry import Expert, ExpertRegistry, ExpertResult, SwarmRequest

logger = logging.getLogger(__name__)


def _fast_mode() -> bool:
    return os.environ.get("SYNTHESUS_FAST_MODE", "1") != "0"


def _budget_timeout_s(budget: Mapping[str, Any]) -> float:
    """Map request budget + FAST_MODE to a per-expert HTTP timeout."""
    if "timeout_s" in budget:
        return float(budget["timeout_s"])
    if "latency_ms" in budget:
        return max(5.0, float(budget["latency_ms"]) / 1000.0)
    return 45.0 if _fast_mode() else 120.0


def _budget_max_tokens(budget: Mapping[str, Any]) -> int | None:
    if "max_tokens" in budget:
        return int(budget["max_tokens"])
    if _fast_mode():
        return int(budget.get("fast_max_tokens", 128))
    return budget.get("max_tokens")  # type: ignore[return-value]


class SwarmScheduler:
    """Fan out expert calls through a single shared model client."""

    def __init__(
        self,
        registry: ExpertRegistry,
        *,
        model_client: SharedOllamaClient | None = None,
        adapter_loader: AdapterLoader | None = None,
        base_model: str | None = None,
        retrieval_fn: Callable[[str, Expert], list[dict[str, Any]]] | None = None,
    ) -> None:
        self.registry = registry
        self.model = model_client or SharedOllamaClient(base_model=base_model)
        self.adapters = adapter_loader or AdapterLoader(
            expected_base_model=self.model.base_model
        )
        # Optional: (query, expert) -> list of source dicts with C-001 tiers
        self.retrieval_fn = retrieval_fn

    def run(self, request: SwarmRequest) -> list[ExpertResult]:
        timeout_s = _budget_timeout_s(request.budget)
        max_tokens = _budget_max_tokens(request.budget)
        results: list[ExpertResult] = []

        for expert_id in request.expert_ids:
            t0 = time.time()
            expert = self.registry.get(expert_id)
            if expert is None:
                logger.warning(
                    "swarm DEGRADED: expert_not_found id=%s — no fabricated persona",
                    expert_id,
                )
                results.append(
                    ExpertResult(
                        expert_id=expert_id,
                        text="",
                        confidence=0.0,
                        provenance_refs=[],
                        degraded=True,
                        degrade_reason="expert_not_found",
                        latency_ms=(time.time() - t0) * 1000.0,
                        model_id=self.model.base_model,
                    )
                )
                continue

            # Adapter is DATA — missing/invalid → that expert degrades, swarm continues.
            # v1: successful validation does NOT hot-swap weights (prompt delta only).
            adapter_status = "none"
            adapter_applied = False
            if expert.adapter_ref:
                validation = self.adapters.validate(expert.adapter_ref)
                if not validation.ok:
                    logger.warning(
                        "swarm DEGRADED: expert=%s adapter=%s reason=%s",
                        expert.expert_id,
                        expert.adapter_ref,
                        validation.reason,
                    )
                    results.append(
                        ExpertResult(
                            expert_id=expert.expert_id,
                            text="",
                            confidence=0.0,
                            provenance_refs=[],
                            degraded=True,
                            degrade_reason=validation.reason,
                            persona=expert.persona,
                            namespace=expert.namespace,
                            latency_ms=(time.time() - t0) * 1000.0,
                            model_id=self.model.base_model,
                            adapter_applied=False,
                            adapter_status=validation.reason,
                        )
                    )
                    continue
                adapter_status = "validated_not_applied"
                adapter_applied = False  # explicit: no LoRA hot-swap in v1
            else:
                adapter_status = "persona_prompt_delta_only"

            sources: list[dict[str, Any]] = []
            if self.retrieval_fn is not None:
                try:
                    sources = list(self.retrieval_fn(request.query, expert) or [])
                except Exception as e:
                    logger.warning(
                        "retrieval DEGRADED for expert=%s: %s", expert.expert_id, e
                    )
                    sources = []

            # Namespace-scoped grounding hint (not a second model).
            ground_bits = []
            for src in sources[:5]:
                if isinstance(src, dict):
                    bit = src.get("pattern") or src.get("text") or src.get("source")
                    if bit:
                        ground_bits.append(str(bit))
            ground_block = ""
            if ground_bits:
                ground_block = (
                    f"\n\n[namespace={expert.namespace} grounding]\n"
                    + "\n".join(f"- {b}" for b in ground_bits)
                )

            system = (
                f"{expert.system_prompt.strip()}\n"
                f"You are the '{expert.persona}' expert (id={expert.expert_id}, "
                f"domain={expert.domain}, namespace={expert.namespace}). "
                f"Stay in character. Do not claim to be other experts. "
                f"You MUST begin your reply with the exact token "
                f"{expert.expert_id.upper()}:"
            )
            user_prompt = f"{request.query.strip()}{ground_block}"

            gen = self.model.generate(
                prompt=user_prompt,
                system_prompt=system,
                timeout_s=timeout_s,
                max_tokens=max_tokens,
            )

            if gen.degraded or not gen.text.strip():
                reason = gen.degrade_reason or "empty_or_failed_generation"
                logger.warning(
                    "swarm DEGRADED: expert=%s generation failed: %s",
                    expert.expert_id,
                    reason,
                )
                results.append(
                    ExpertResult(
                        expert_id=expert.expert_id,
                        text="",
                        confidence=0.0,
                        provenance_refs=[f"namespace:{expert.namespace}"],
                        degraded=True,
                        degrade_reason=reason,
                        persona=expert.persona,
                        namespace=expert.namespace,
                        latency_ms=gen.latency_ms,
                        model_id=gen.model_id,
                        sources=sources,
                        adapter_applied=adapter_applied,
                        adapter_status=adapter_status,
                    )
                )
                continue

            prov_refs = [f"namespace:{expert.namespace}", f"model:{gen.model_id}"]
            if expert.adapter_ref:
                prov_refs.append(f"adapter_ref:{expert.adapter_ref}")
                prov_refs.append(f"adapter_status:{adapter_status}")
            for src in sources:
                if isinstance(src, dict) and src.get("source"):
                    prov_refs.append(str(src["source"]))

            conf = 0.75
            if sources:
                conf = 0.85
            results.append(
                ExpertResult(
                    expert_id=expert.expert_id,
                    text=gen.text.strip(),
                    confidence=conf,
                    provenance_refs=prov_refs,
                    degraded=False,
                    persona=expert.persona,
                    namespace=expert.namespace,
                    latency_ms=gen.latency_ms,
                    model_id=gen.model_id,
                    sources=sources,
                    adapter_applied=adapter_applied,
                    adapter_status=adapter_status,
                )
            )

        # Safety: all generations must share one model id when healthy
        healthy_models = {r.model_id for r in results if not r.degraded and r.model_id}
        if len(healthy_models) > 1:
            logger.error(
                "swarm invariant VIOLATED: multiple model ids used: %s",
                healthy_models,
            )

        return results
