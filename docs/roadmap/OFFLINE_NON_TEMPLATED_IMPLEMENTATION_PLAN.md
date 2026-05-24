# Implementation Plan: Fully Offline, Non-Templated Language Generation

Goal: make Synthesus produce language locally, without external LLM API dependencies, and without template-style fallback output as the default behavior.

## Success Criteria

- All query paths generate responses via local generation logic first.
- No runtime path requires external LLM APIs.
- Network-capable tool paths are disabled by default (or hard-gated).
- Template fallback responses are removed or converted to explicit error/degraded markers.
- End-to-end tests prove offline operation and non-templated behavior.

## Phase 0: Contract Lock and Feature Flags

### Tasks

- Add explicit runtime mode flags:
  - `SYNTHESUS_OFFLINE_ONLY=true`
  - `SYNTHESUS_NO_TEMPLATE_FALLBACK=true`
  - `SYNTHESUS_DISABLE_REMOTE_ACCEL=true`
  - `SYNTHESUS_DISABLE_WEB_TOOLS=true`
- Centralize flag reads in one config module (used by API, cognitive, tools, accelerators).

### Deliverables

- New configuration module and wiring in:
  - `api/production_server.py`
  - `cognitive/cognitive_engine.py`
  - `cognitive/agent_dispatcher.py`
  - `accelerators/*`
  - `core/generation/spine.py`

### Acceptance

- Boot logs clearly print effective offline mode and disabled subsystems.

## Phase 1: Remove Template Dominance in Generation

### Tasks

- Refactor `core/generation/spine.py`:
  - Make local decode attempts mandatory-first.
  - Replace string-template fallback sentences with:
    - iterative decode retries (different sampling profiles),
    - constrained regeneration,
    - last-resort explicit degraded marker if all attempts fail.
- Ensure empty `raw_text` and low-confidence paths still go through generative flow where appropriate.
- Enforce structured response-plan creation in low-confidence branches.

### Deliverables

- Updated `GenerationSpine.generate(...)`, `_generate_from_context(...)`, and fallback handling.
- Retry policy and deterministic failure marker spec.

### Acceptance

- No default user-facing canned fallback templates remain in spine.

## Phase 2: Enforce Local-Only Dependencies

### Tasks

- In `api/production_server.py`:
  - hard-disable remote adapters when offline-only mode is enabled.
- In `accelerators/`:
  - block remote adapter registration under offline-only mode.
- In cognitive tooling:
  - disable web scraper/tool paths under offline-only mode.
- Audit and gate any HTTP calls in runtime path (`httpx`, `requests`) behind explicit opt-in.

### Deliverables

- Local-only execution guards across API and tool dispatch.
- Runtime warning/error if a disallowed network path is requested.

### Acceptance

- Query flow succeeds with network blocked.
- No outbound network calls occur in offline mode.

## Phase 3: Make Language Generation the Primary Output Mode

### Tasks

- Update cognitive/RAG handoff:
  - treat retrieved/pattern text as context hints, not final surface text.
  - run a local rewrite/final generation pass in spine for natural output.
- Keep retrieval grounding and constraints, but move final wording to local generation.
- Add provenance metadata:
  - grounding source,
  - generation mode,
  - decode attempts,
  - constraint satisfaction.

### Deliverables

- Unified handoff interface from cognitive/RAG to spine (context + constraints).
- Updated response schema docs to expose generation metadata safely.

### Acceptance

- High percentage of outputs are generated text rather than direct template emits.

## Phase 4: Frontend + SDK Contract Consolidation

### Tasks

- Keep canonical API namespace as `/api/v1/*`.
- Maintain temporary shims (`/query`, `/api/query`) only as compatibility wrappers.
- Update SDKs and legacy UI payloads to v1 keys (`character`, `query`, `mode`).
- Remove or deprecate dead endpoints/legacy feedback flows.

### Deliverables

- Contract matrix for frontend + SDK payloads.
- Deprecation timeline and compatibility policy.

### Acceptance

- Built-in frontend and SDKs all hit one canonical contract.

## Phase 5: Test Gates for Offline + Non-Templated Guarantees

### Tasks

- Add strict offline test suite:
  - block/monkeypatch network libraries and assert zero calls.
- Add non-templated generation tests:
  - reject known template signatures in output.
  - enforce minimum lexical variation across repeated prompts.
- Add API integration tests for:
  - query path under offline mode,
  - generation metrics and recommendation states,
  - degraded marker behavior when generation models are unavailable.

### Deliverables

- New test modules:
  - `tests/test_offline_contract.py`
  - `tests/test_non_templated_generation.py`
  - `tests/test_generation_pipeline_e2e.py`

### Acceptance

- CI passes with offline mode enabled and template-leak checks enforced.

## Phase 6: Operationalization

### Tasks

- Add startup health checks for model availability (`vocab_*.pkl`).
- Define runbook for local model refresh/training.
- Add dashboard metrics:
  - generated-vs-template ratio,
  - decode failure rate,
  - offline guard violations.

### Deliverables

- Ops documentation and monitoring widgets/JSON metrics fields.

### Acceptance

- Operators can verify quality and offline compliance in production quickly.

## Execution Order (Recommended)

1. Phase 0 (flags and mode contract)
2. Phase 2 (hard offline enforcement)
3. Phase 1 (remove template fallback behavior)
4. Phase 3 (make generation primary wording path)
5. Phase 5 (lock behavior with tests)
6. Phase 4 (client migration cleanup)
7. Phase 6 (ops hardening)

## Risks and Mitigations

- Risk: output quality drops while removing templates.
  - Mitigation: staged rollout with A/B metrics and decode retry tuning.
- Risk: legacy clients break.
  - Mitigation: compatibility shims + migration window + explicit SDK updates.
- Risk: hidden network dependencies remain.
  - Mitigation: strict network-deny test harness in CI.

## Definition of Done

- Offline-only mode is default-safe and enforced.
- No external LLM API dependency in runtime query pipeline.
- Template fallback strings are not used as default response generation.
- Frontend path is fully wired to canonical API and verified end-to-end.
- Test suite explicitly guarantees offline + non-templated behavior.
