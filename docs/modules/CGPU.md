# CGPU Render Accelerator

The Cognitive GPU is the Synthesus 5 surface rendering device. It turns grounded cognitive state into candidate natural-language surfaces, NPC/persona dialogue, and concise business-bot answers. It does not own facts or safety decisions.

## Contract

Runtime code lives in `packages/reasoning/generation/cgpu.py`.

- `CGPUFrame` is the CHAL input frame for `chal://cgpu/render`.
- `CGPUCandidate` is one rendered surface plus its critic result.
- `CGPUOutputFrame` is the candidate-set output consumed by the hypervisor or future Quad Brain arbiter.
- `CGPURenderer.render()` emits candidates, critic feedback metadata, provenance, grounding state, and safety-arbitration trace flags.

The reusable schema contract is mirrored in `docs/openapi.yaml`, `docs/openapi.json`, and `docs/api_schema.json` as `CGPUFrame` and `CGPUOutputFrame`. These schemas document the CHAL device boundary; `/api/v1/query` still uses the legacy-compatible `QueryResponse` envelope. Explicit `mode="chal"` calls now expose typed Cognitive Hypervisor records under `debug.cognitive_hypervisor` using the `CognitiveHypervisorTrace` component. When the hypervisor selects `route="quad_brain_path"`, `CognitiveHypervisorTrace.quad_brain` is typed as `QuadBrainArbitration` and contains the CGPU role output inside the serialized four-brain arbiter trace; standalone CGPU candidate-set records should use the same debug envelope after runtime arbitration wires them in.

## Boundary

CGPU may:

- render several phrasings from the same grounded state
- render NPC/persona-style dialogue from persona metadata
- render concise business-bot surfaces
- apply critic rewrite hints to repair missing required content

CGPU must not:

- invent facts outside the frame's grounded state, plan anchors, or explicit persona metadata
- bypass critic/safety arbitration
- emit blocked candidates as selected output
- treat PPBRS or legacy templates as final user-facing prose

## Template Leakage Guard

Runtime guard code lives in `packages/reasoning/generation/template_guard.py`. The guard classifies surface text before emission and blocks normal-path legacy template signatures, including `[module]`, `[fallback]`, `response_template`, `Handled:`, and `No route matched`.

`CognitiveHypervisor` now applies the guard after hemisphere bridge dispatch. If a normal Synthesus 5 path receives a legacy-shaped surface, it replaces the text with a degraded CHAL quarantine message and records the matched signatures in `telemetry.template_guard`. Safety, platform, identity/rights, and explicit NPC-script exceptions are allowed only when labeled through the template surface boundary.

`GenerationSpine` also labels primary-generation failures through `SpineOutput.degraded_state` instead of emitting classic fallback phrasing. The degraded surface uses non-legacy wording and records `surface="degraded_state"`, `reason="primary_generation_unavailable"`, and whether any known legacy template signature reached the degraded text.

## Quad Brain Runtime Wiring

`CognitiveHypervisor` now invokes `packages/core/chal/quad_brain.py` for `quad_brain_path`. The serialized arbiter feeds Knowledge/Grounding facts into Executive Reasoning, builds a bounded `ResponsePlan`, calls `CGPURenderer`, then sends the selected candidate through Critic/Metacognition before emission.

The runtime trace is exposed at `telemetry.quad_brain` and mirrored into `bridge_result.quad_brain_arbitration`. It includes the four brain outputs, fixed `serial_order`, CGPU candidate diagnostics, template-guard status, and a state contract that explicitly records serialized arbitration and no parallel brain spawning.

The Quad Brain state contract now includes a per-role state-transition chain. CGPU consumes `executive.response_plan`, `knowledge.facts`, and `character_context`, then emits `cgpu.candidates` and `cgpu.selected_candidate` for the critic. This keeps CGPU render output inspectable as an intermediate device frame, not a direct final response path.

## Validation

Focused validation:

```bash
python -m py_compile packages/reasoning/generation/cgpu.py packages/reasoning/generation/__init__.py tests/test_cgpu_renderer.py
PYTHONPATH=/home/workspace/Synthesus_4.0/packages:/home/workspace/Synthesus_4.0/packages/core:/home/workspace/Synthesus_4.0/packages/reasoning:/home/workspace/Synthesus_4.0/packages/kernel python -m pytest -q tests/test_cgpu_renderer.py tests/test_generation_spine_integration.py
```

The test coverage verifies multiple grounded candidates, persona/NPC mode, business-bot mode, critic rewrite, and blocked-candidate selection behavior.
