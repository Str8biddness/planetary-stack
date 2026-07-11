"""SW-3 — Merge expert candidates via QuadBrainOrchestrator → one answer.

Uses the existing CHAL quad-brain arbiter (serialized knowledge→executive→
cgpu→critic). Does not spawn parallel model copies.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Sequence

from .registry import ExpertResult, SwarmAnswer

logger = logging.getLogger(__name__)

try:
    from core.chal.quad_brain import QuadBrainOrchestrator
    from core.chal.hypervisor import (
        HypervisorBudget,
        HypervisorDecision,
        HypervisorRoute,
    )
except ImportError:  # package-path fallback
    from packages.core.chal.quad_brain import QuadBrainOrchestrator  # type: ignore
    from packages.core.chal.hypervisor import (  # type: ignore
        HypervisorBudget,
        HypervisorDecision,
        HypervisorRoute,
    )

try:
    from memory_provenance import (
        Provenance,
        Verification,
        classify,
        VERIFICATION_WEIGHT,
    )
except ImportError:
    try:
        from knowledge.memory_provenance import (  # type: ignore
            Provenance,
            Verification,
            classify,
            VERIFICATION_WEIGHT,
        )
    except ImportError:
        Provenance = None  # type: ignore
        Verification = None  # type: ignore
        classify = None  # type: ignore
        VERIFICATION_WEIGHT = {0: 0.3, 1: 0.7, 2: 1.0}  # type: ignore


def _tier_int(source: dict[str, Any]) -> int:
    if source.get("verification") is not None:
        try:
            return int(source["verification"])
        except (TypeError, ValueError):
            pass
    name = str(source.get("verification_name") or "").upper()
    if name == "VERIFIED":
        return 2
    if name == "GROUNDED":
        return 1
    if name == "UNVERIFIED":
        return 0
    prov = source.get("provenance")
    if classify is not None and prov is not None:
        try:
            return int(classify(prov))
        except Exception:
            pass
    return 0


def _normalize_source(src: dict[str, Any], *, expert_id: str) -> dict[str, Any]:
    """Ensure C-001 provenance + verification fields on every source."""
    out = dict(src)
    out.setdefault("expert_id", expert_id)
    if out.get("provenance") is None:
        # Expert draft text is LLM generation unless marked otherwise
        out["provenance"] = (
            Provenance.LLM_GENERATION.value
            if Provenance is not None
            else "llm_generation"
        )
    if out.get("verification") is None and classify is not None:
        out["verification"] = int(classify(out["provenance"]))
    elif out.get("verification") is None:
        out["verification"] = _tier_int(out)
    if out.get("verification_name") is None:
        v = int(out["verification"])
        out["verification_name"] = {0: "UNVERIFIED", 1: "GROUNDED", 2: "VERIFIED"}.get(
            v, "UNVERIFIED"
        )
    return out


def _expert_as_source(result: ExpertResult) -> dict[str, Any]:
    """Represent a healthy expert answer as a retrieval-like source with tiers."""
    # Expert model text is a draft (UNVERIFIED) unless sources already ground it.
    max_tier = 0
    for s in result.sources:
        if isinstance(s, dict):
            max_tier = max(max_tier, _tier_int(s))
    if max_tier >= 1:
        prov = "grounded_cited"
        ver = 1
    else:
        prov = "llm_generation"
        ver = 0
    return {
        "source": f"expert:{result.expert_id}",
        "expert_id": result.expert_id,
        "persona": result.persona,
        "namespace": result.namespace,
        "pattern": (result.text or "")[:240],
        "score": float(result.confidence),
        "provenance": prov,
        "verification": ver,
        "verification_name": {0: "UNVERIFIED", 1: "GROUNDED", 2: "VERIFIED"}[ver],
        "provenance_refs": list(result.provenance_refs),
    }


class SwarmArbiter:
    """Merge expert candidates into one grounded SwarmAnswer via QuadBrain."""

    def __init__(self, orchestrator: QuadBrainOrchestrator | None = None) -> None:
        self.orchestrator = orchestrator or QuadBrainOrchestrator()

    def merge(
        self,
        *,
        query: str,
        expert_results: Sequence[ExpertResult],
        model_id: str | None = None,
    ) -> SwarmAnswer:
        t0 = time.time()
        healthy = [r for r in expert_results if not r.degraded and str(r.text).strip()]
        degraded = [r.expert_id for r in expert_results if r.degraded]

        sources: list[dict[str, Any]] = []
        for r in expert_results:
            for s in r.sources:
                if isinstance(s, dict):
                    sources.append(_normalize_source(s, expert_id=r.expert_id))
            if not r.degraded and r.text.strip():
                sources.append(_expert_as_source(r))

        # Sort sources verified > grounded > unverified (C-001 weights)
        def _sort_key(s: dict[str, Any]) -> tuple:
            tier = _tier_int(s)
            weight = (
                VERIFICATION_WEIGHT.get(Verification(tier), 0.3)  # type: ignore[arg-type]
                if Verification is not None and tier in (0, 1, 2)
                else {0: 0.3, 1: 0.7, 2: 1.0}.get(tier, 0.3)
            )
            return (-weight, -float(s.get("score") or 0.0))

        sources_sorted = sorted(sources, key=_sort_key)

        if not healthy:
            # All experts degraded — loud empty answer, no fabricated persona text.
            logger.warning(
                "swarm arbiter DEGRADED: no healthy expert results (degraded=%s)",
                degraded,
            )
            return SwarmAnswer(
                response="",
                contributing_experts=[],
                arbitration={
                    "status": "DEGRADED",
                    "reason": "all_experts_degraded",
                    "degraded_experts": degraded,
                },
                sources=sources_sorted,
                expert_results=[r.to_dict() for r in expert_results],
                degraded_experts=degraded,
                model_id=model_id,
                latency_ms=(time.time() - t0) * 1000.0,
            )

        # Build rag_context from healthy expert drafts + their grounding
        rag_parts = []
        for r in healthy:
            rag_parts.append(f"[expert:{r.expert_id} persona={r.persona} ns={r.namespace}]\n{r.text}")
        rag_context = "\n\n".join(rag_parts)

        # Prefer highest-confidence expert as bridge seed (not a second model).
        seed = max(healthy, key=lambda r: r.confidence)
        bridge_result: dict[str, Any] = {
            "response": seed.text,
            "hemisphere_used": "swarm_shared_base",
            "hypervisor_trace": {"trace_id": f"swarm-{uuid.uuid4().hex[:12]}"},
            "expert_candidates": [
                {"expert_id": r.expert_id, "confidence": r.confidence, "chars": len(r.text)}
                for r in healthy
            ],
        }

        decision = HypervisorDecision(
            trace_id=bridge_result["hypervisor_trace"]["trace_id"],
            route=HypervisorRoute.QUAD_BRAIN_PATH,
            hemisphere_mode="swarm",
            budget=HypervisorBudget(
                latency_ms=float(os_budget_ms()),
                retrieval_depth=len(healthy),
                candidate_count=max(1, len(healthy)),
                critic_passes=1,
            ),
            reasons=["swarm_expert_merge"],
            constraints=["ground_response_in_mounted_knowledge"],
        )

        arbitration = self.orchestrator.arbitrate(
            query=query,
            decision=decision,
            bridge_result=bridge_result,
            rag_context=rag_context,
            character_context={"persona": "swarm_arbiter", "character_id": "swarm"},
            constraints=["swarm_merge"],
            runtime_preset=None,
            max_tokens=256,
        )

        cgpu_text = (arbitration.selected_response or "").strip()
        selected, selected_source = _pick_user_facing_response(
            cgpu_text=cgpu_text,
            seed=seed,
            healthy=healthy,
            cgpu_source=arbitration.selected_source,
        )

        contrib = [r.expert_id for r in healthy]
        arb_meta = {
            "status": "ok",
            "selected_source": selected_source,
            "quad_brain": arbitration.to_dict()
            if hasattr(arbitration, "to_dict")
            else {"selected_response_chars": len(cgpu_text)},
            "cgpu_selected_response": cgpu_text,  # keep full critic path for traces
            "serial_order": list(getattr(arbitration, "serial_order", [])),
            "contributing_experts": contrib,
            "degraded_experts": degraded,
            "shared_model_id": model_id,
            "response_policy": "prefer_expert_seed_over_template_cgpu",
        }

        return SwarmAnswer(
            response=selected,
            contributing_experts=contrib,
            arbitration=arb_meta,
            sources=sources_sorted,
            expert_results=[r.to_dict() for r in expert_results],
            degraded_experts=degraded,
            model_id=model_id,
            latency_ms=(time.time() - t0) * 1000.0
            + float(getattr(arbitration, "latency_ms", 0.0)),
        )


def _looks_like_template_surface(text: str) -> bool:
    """CGPU/template leakage patterns that must not be the user-facing answer."""
    t = (text or "").strip()
    if not t:
        return True
    low = t.lower()
    needles = (
        "swarm: [expert:",
        "[expert:",
        "response_template",
        "handled:",
        "no route matched",
        "[module]",
        "[fallback]",
        "template_surface",
    )
    if any(n in low for n in needles):
        return True
    # Bare structured dump of expert blocks without natural language
    if low.startswith("swarm:") and "persona=" in low:
        return True
    return False


def _pick_user_facing_response(
    *,
    cgpu_text: str,
    seed: ExpertResult,
    healthy: Sequence[ExpertResult],
    cgpu_source: str,
) -> tuple[str, str]:
    """Prefer real expert prose over template-y CGPU/critic frames.

    Quad-brain trace stays in arbitration; user-facing response must not look
    fabricated or templated.
    """
    if cgpu_text and not _looks_like_template_surface(cgpu_text):
        return cgpu_text, cgpu_source

    # Prefer highest-confidence healthy expert with non-empty real text
    best = seed
    for r in healthy:
        if r.confidence > best.confidence and str(r.text).strip():
            best = r
    if str(best.text).strip():
        if cgpu_text and _looks_like_template_surface(cgpu_text):
            logger.info(
                "arbiter: preferring expert_seed=%s over template CGPU surface",
                best.expert_id,
            )
        return best.text.strip(), f"expert_seed:{best.expert_id}"

    # Last resort: whatever CGPU had (may be empty)
    return cgpu_text, cgpu_source or "empty"


def os_budget_ms() -> float:
    import os

    if os.environ.get("SYNTHESUS_FAST_MODE", "1") != "0":
        return 15_000.0
    return 60_000.0


class SwarmRuntime:
    """End-to-end: schedule experts → arbitrate → SwarmAnswer."""

    def __init__(self, scheduler: "SwarmScheduler", arbiter: SwarmArbiter | None = None) -> None:
        from .scheduler import SwarmScheduler as _SS  # noqa: F401 — type hint only

        self.scheduler = scheduler
        self.arbiter = arbiter or SwarmArbiter()

    def answer(self, request) -> SwarmAnswer:
        t0 = time.time()
        results = self.scheduler.run(request)
        model_ids = {r.model_id for r in results if r.model_id}
        # Prefer the shared client base model
        model_id = None
        if hasattr(self.scheduler, "model"):
            model_id = getattr(self.scheduler.model, "base_model", None)
        if not model_id and model_ids:
            model_id = next(iter(model_ids))
        ans = self.arbiter.merge(
            query=request.query,
            expert_results=results,
            model_id=model_id,
        )
        ans.latency_ms = (time.time() - t0) * 1000.0
        return ans
