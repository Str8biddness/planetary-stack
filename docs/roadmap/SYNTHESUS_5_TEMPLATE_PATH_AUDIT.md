# Synthesus 5 Template Path Audit

This document records the Phase 6 classification of direct fallback/template response surfaces found under `packages/`.

The executable audit is `tools/audit_template_surfaces.py`. It scans Python source for legacy template signatures and fails when a matched path is not classified. The regression test is `tests/test_template_surface_audit.py`.

## Classification Rules

| Status | Meaning |
|---|---|
| `firmware_context_only` | Template text is metadata inside a CHAL/PPBRS firmware signal and must not be final user-facing text. |
| `guard_definition` | The file defines leakage signatures or quarantine behavior. |
| `non_user_facing` | Template text is used for traces, ingest, training data, or internal prompts. |
| `allowed_labeled_exception` | Template text is an explicit safety/platform/NPC-script boundary allowed by Synthesus 5 law. |
| `legacy_quarantine_required` | A legacy surface can still emit template/fallback wording outside the explicit Synthesus 5 CHAL path and needs later removal or labeled degraded-state handling. |

## Current Results

The audit currently classifies 89 matched package-level Python template signatures across 17 paths. The remaining `legacy_quarantine_required` paths are:

- `packages/api/fastapi_server.py` — legacy character router can return direct `response_template` text and character fallback strings.
- `packages/api/production_server.py` — legacy pattern ingestion/lookup preserves `response_template` and response text for compatibility outside the explicit CHAL route.
- `packages/core/cognitive/cognitive_engine.py` — legacy cognitive character behavior still reads pattern templates and fallback text outside the explicit CHAL hypervisor path.
- `packages/core/cognitive/response_compositor.py` — older response composition can realize classic `response_template` strings directly.
- `packages/core/els_bridge.py` — ELS pattern storage persists `response_template` data for legacy pattern recall.
- `packages/core/pattern_engine.py` — PatternEngine stores templated output structures that must be consumed through firmware/generation boundaries.
- `packages/reasoning/generation/spine.py` — generation fallback wording exists as a degraded surface and needs an explicit degraded-state label before Phase 6 closes.

The PPBRS normal path is classified as `firmware_context_only`: `packages/reasoning/reasoning_chain.py` stores legacy template text only in `chal_firmware_signal.module_message.payload.template_context`, while `response` remains empty and `user_facing` remains false.

## Validation Command

```bash
python tools/audit_template_surfaces.py --fail-on-unclassified
python -m pytest -q tests/test_template_surface_audit.py
```
