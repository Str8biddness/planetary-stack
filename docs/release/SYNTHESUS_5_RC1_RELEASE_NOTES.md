# Synthesus 5 RC1 Release Notes

## Position

Synthesus 5 RC1 is a bounded synthetic intelligence runtime, not a frontier-model claim. The release candidate packages the CHAL-controlled conversation path for inspection, demos, and private beta preparation.

## Shippable Surfaces

- `/api/v1/query` with `mode="chal"` for Cognitive Hypervisor routing.
- `/api/v1/query` with `mode="business_bot"` for concise operator/business responses.
- Quad Brain trace telemetry for grounding, executive reasoning, CGPU rendering, and critic/metacognition.
- Typed degraded-state telemetry for budget exhaustion, device fault, and template quarantine.
- Legacy-template leak regression checks on normal-path CHAL responses.
- Deterministic Phase 8 comparison harness for legacy-vs-Synthesus-5 quality, latency, safety, grounding, naturalness, and template leakage.

## Commercial Boundary

RC1 is suitable for controlled demos and private-beta packaging after the runtime release gate passes. Paid consumer launch remains blocked until Knowledge Cloud generated artifacts validate from cold start and release evidence shows no critical gate failures.

## Known Launch Blocker

The current generated Knowledge Cloud bundle has a known FAISS/embedder dimension mismatch. CHAL mount and KAL boundaries are healthy, but paid launch must not claim full grounded retrieval readiness until `tools/validate_knowledge_cold_start.py` passes against aligned artifacts.

## Validation Commands

```bash
python tools/synthesus5_release_gate.py
python tools/synthesus5_release_gate.py --run-focused-suite --run-runtime --fail-on-blocker
SYNTHESUS_KNOWLEDGE_SYNC_MODE=off python tools/synthesus5_focused_suite.py
```

## RC1 Packaging Decision

- Demo package: allowed when static release gate passes.
- Private beta: allowed only after the focused suite and runtime CHAL smoke pass and user-facing limitations are disclosed.
- Paid consumer launch: blocked until all critical release-gate checks pass, including Knowledge Cloud cold-start integrity.
