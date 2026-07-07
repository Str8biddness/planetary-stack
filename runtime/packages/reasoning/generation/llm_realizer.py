"""
LLM-backed surface realizer — mounts the CHAL LLM Generation Device (C-201) as
the CGPU render surface. This is "the merge": the open-source LLM becomes the
language cortex *inside* the Quad Brain, replacing the seed-passthrough bootstrap
in ``SurfaceRealizer`` — while grounding + the critic still wrap every candidate.

The LLM is a mounted device, never the unbounded source of truth
(Blueprint General Note #4). On device failure it degrades LOUDLY to the seed
bootstrap and records the reason (Law #5) — it never fabricates output (Law #1).

Advances: C-202 (grounded generation) + C-301 (critic remains in the loop).
"""
from __future__ import annotations

from .response_plan import GenerationTrace
from .surface_realizer import RealizationRequest, RealizationResult, SurfaceRealizer


class LLMSurfaceRealizer(SurfaceRealizer):
    """Realize candidate text via the Ollama-backed ``LLMGenerationDevice``."""

    def __init__(self, device=None, budget_ms: float = 30000.0):
        # Lazy import avoids any core<->reasoning import cycle at module load.
        if device is None:
            from packages.core.chal.devices.llm_device import LLMGenerationDevice
            device = LLMGenerationDevice()
        self._device = device
        self._budget_ms = float(budget_ms)

    def realize(self, request: RealizationRequest) -> RealizationResult:
        from packages.core.chal.frames import CognitiveTask
        from .prompt_composer import PromptComposer

        # Compose the per-turn SYSTEM prompt from runtime state: identity + persona
        # (intent/style) + grounding discipline + constraints. Grounding TEXT stays
        # in the user prompt (_build_prompt) where the model already reads it, so we
        # compose with inline_grounding=False — the composer just enforces the
        # must_ground contract without duplicating the context.
        plan = request.plan
        composed = PromptComposer().compose(
            persona={"voice": f"intent={plan.intent}, style={plan.style}"},
            grounding=[{"source": "knowledge", "text": request.context}] if request.context else None,
            constraints={"format": "; ".join(plan.key_points)} if plan.key_points else None,
            inline_grounding=False,
        )

        prompt = self._build_prompt(request)
        task = CognitiveTask(
            task_id="cgpu-realize",
            query=prompt,
            budgets={"latency_ms": self._budget_ms},
        )
        output, telemetry = self._device.generate(task, system_prompt=composed.system_prompt)

        diagnostics = {
            "source": "llm_device",
            "latency_ms": f"{telemetry.latency_ms:.0f}",
            "composed_prompt": "true",
            "enforcement": composed.enforcement,   # hard contract -> Critic verifies
        }
        if isinstance(output, dict):
            # Structured error frame from the device — degrade LOUDLY to the seed
            # bootstrap (Law #5). Do not fabricate a success (Law #1).
            text = request.seed_text.strip()
            diagnostics["degraded"] = "true"
            diagnostics["error"] = str(output.get("error", "unknown"))
        else:
            text = output.strip() or request.seed_text.strip()

        trace = GenerationTrace(
            text=text,
            constraints_satisfied=self._constraints_satisfied(text, request.plan),
            forbidden_triggered=self._forbidden_triggered(text, request.plan),
            decode_attempts=max(1, request.max_attempts),
        )
        return RealizationResult(text=text, trace=trace, diagnostics=diagnostics)

    def _build_prompt(self, request: RealizationRequest) -> str:
        plan = request.plan
        parts = [
            "You are the Synthesus generation surface. Write a single, clear, "
            "natural-language response. Do not include meta-commentary or labels.",
            f"Intent: {plan.intent}. Style: {plan.style}.",
        ]
        if request.context:
            parts.append(f"Grounded context (rely only on these facts):\n{request.context}")
        if plan.key_points:
            parts.append("Cover these points: " + "; ".join(plan.key_points))
        if plan.required_phrases:
            parts.append("Include these verbatim: " + "; ".join(plan.required_phrases))
        if plan.forbidden_phrases:
            parts.append("Never use these phrases: " + "; ".join(plan.forbidden_phrases))
        if request.seed_text:
            parts.append(f"Rough draft to improve:\n{request.seed_text}")
        parts.append("Response:")
        return "\n\n".join(parts)
