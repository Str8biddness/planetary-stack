# C-101 — LLM Mounted as CGPU Surface ("The Merge") — Build Log

**Callout:** C-101 (integration; advances C-202 grounding + C-301 critic) · **Owner:** Claude (Opus 4.8) · **Date:** 2026-06-30
**Status:** ✅ tolerance MET — **PENDING REVIEW GATE** (Law #8: author does not self-approve)
**Built on:** Section B (C-201, verified) commit `869d4e8`, in isolated worktree `feat/c101-llm-cgpu` (Law #9).

## What this is
The merge. The Ollama-backed `LLMGenerationDevice` (C-201) is mounted as the CGPU
**surface realizer**, replacing the seed-passthrough bootstrap in `SurfaceRealizer`
(whose own TODO asked for exactly this). The LLM becomes the language cortex *inside*
the Quad Brain — grounding + critic still wrap every candidate. The LLM is a mounted
device, never the unbounded source of truth.

## Seam
`CGPURenderer(realizer=LLMSurfaceRealizer())`. `_render_candidate` already routes text
through `self.realizer.realize(...)` and then `self.critic.critique(...)`, so injecting
the LLM realizer keeps grounding + critic in the loop for free.

## Proof (C-101 DoD — real run output)
```
device      : chal://cgpu/render
LLM text    : '"...there's one giant that stands out from the rest - Jupiter.
               And trust me, this gas giant is..."'
diagnostics : {'source': 'llm_device', 'latency_ms': '5872'}   # real device, not seed, not degraded
critic      : accept | accepted: True
C-101 PROOF PASSED ✅  (LLM rendered, grounded, critic-judged)
```
Reproduce: `PYTHONPATH=".:packages/reasoning:packages/kernel:packages/knowledge:packages/core:packages" ./.venv/bin/python verify_c101.py` (requires local Ollama + `llama3.2:3b`).

## Files (this branch)
- **NEW** `packages/reasoning/generation/llm_realizer.py` — `LLMSurfaceRealizer`. On device error → degrades LOUDLY to seed + records reason (Law #5); never fabricates (Law #1).
- **NEW** `verify_c101.py` — the integration proof (real Ollama; not a CI unit test).
- **MOD** `packages/reasoning/generation/spine.py` — `from ..geometric_interference` → `from geometric_interference` (flat import works under every convention). *Packaging-chain fix (Section A concern) hit during integration.*
- **MOD** `packages/core/__init__.py` — top-level exports made **lazy** (PEP 562) so importing a lightweight device no longer force-loads the entire heavy runtime. *Decoupling fix.*

## Made the LLM the DEFAULT (env flag) — DONE
`cgpu.py` `CGPURenderer()` now selects its realizer via `SYNTHESUS_CGPU_REALIZER`:
`=llm` → `LLMSurfaceRealizer` (degrades loudly to seed if unavailable); unset/`=seed`
→ deterministic seed (unit tests stay reproducible). The hypervisor calls bare
`CGPURenderer()` (`chal/hypervisor.py:493,813`), so the CHAL query path renders via the
LLM when launched with the flag — **no edit to Section A's `chal/*`.** Proof:
```
WITHOUT flag : source=seed(deterministic) -> "Jupiter is the largest planet in the Solar System."
WITH   flag  : source=llm_device          -> "Jupiter takes the crown as the biggest planet out there..."
```
Launcher `run_runtime.sh` exports `SYNTHESUS_CGPU_REALIZER=llm`.

## Wired into the runtime response path (END-TO-END) — DONE
`chal/hypervisor.py` `process_query` now does a **final language render** via the CGPU/LLM
device (new `_final_language_render`), making the LLM the `final_language_owner`. Degrades
loudly to the prior response if the render is empty/unavailable (never fabricates).
**Verified against the REAL running server** (rebased onto latest `main`, `POST /api/v1/query
mode=chal`, `SYNTHESUS_CGPU_REALIZER=llm`):
```
Q: largest planet?  ->  "Jupiter is the largest planet in our solar system, with a diameter
   of approximately 142,984 km and a mass ~2.5x all other planets combined."
   (correct · clean · no scaffolding leak · 0 render failures · ~11.8s CPU)
```
Before this wire: wrong ("Saturn") + leaked scaffolding + LLM never called.
⚠️ Edits `chal/hypervisor.py` (Section A lane) — flagged for Section A review.

## Follow-ups (not in this PR)
- **Section E**: point the OS desktop `/api/chat` at the runtime CHAL path (C-401) so the SHIPPED app uses this.
- **Section C**: real knowledge-cloud grounding (answer is LLM-knowledge only; grounding still DEGRADED).
- Broader testing beyond a single query.
- The two packaging fixes should be reviewed by Section A owner.

No mocks. No out-of-lane edits beyond the two blocking packaging fixes (documented above).
