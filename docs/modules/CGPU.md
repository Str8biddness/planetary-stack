# CGPU Render Accelerator

The Cognitive GPU is the Synthesus 5 surface rendering device. It turns grounded cognitive state into candidate natural-language surfaces, NPC/persona dialogue, and concise business-bot answers. It does not own facts or safety decisions.

## Contract

Runtime code lives in `packages/reasoning/generation/cgpu.py`.

- `CGPUFrame` is the CHAL input frame for `chal://cgpu/render`.
- `CGPUCandidate` is one rendered surface plus its critic result.
- `CGPUOutputFrame` is the candidate-set output consumed by the hypervisor or future Quad Brain arbiter.
- `CGPURenderer.render()` emits candidates, critic feedback metadata, provenance, grounding state, and safety-arbitration trace flags.

The reusable schema contract is mirrored in `docs/openapi.yaml`, `docs/openapi.json`, and `docs/api_schema.json` as `CGPUFrame` and `CGPUOutputFrame`. These schemas document the CHAL device boundary; `/api/v1/query` still uses the legacy-compatible `QueryResponse` envelope and should expose CGPU/hypervisor records under `debug` only after the runtime wiring lands.

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

## Validation

Focused validation:

```bash
python -m py_compile packages/reasoning/generation/cgpu.py packages/reasoning/generation/__init__.py tests/test_cgpu_renderer.py
PYTHONPATH=/home/workspace/Synthesus_4.0/packages:/home/workspace/Synthesus_4.0/packages/core:/home/workspace/Synthesus_4.0/packages/reasoning:/home/workspace/Synthesus_4.0/packages/kernel python -m pytest -q tests/test_cgpu_renderer.py tests/test_generation_spine_integration.py
```

The test coverage verifies multiple grounded candidates, persona/NPC mode, business-bot mode, critic rewrite, and blocked-candidate selection behavior.
