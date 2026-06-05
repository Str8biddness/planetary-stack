# Synthesus Commercial Packaging

## Product Thesis

Synthesus should monetize as bounded synthetic intelligence infrastructure: inspectable NPCs, business bots, and agent runtimes with memory, grounding, safety, and traceability. The product should not sell vague AGI claims.

## Buyer-Facing Packages

### 1. NPC Runtime API

For game studios, simulation teams, and interactive fiction builders.

- Character runtime endpoint.
- Persona and memory boundaries.
- Quad Brain trace mode for debugging behavior.
- Optional character-pack authoring workflow.

Pricing shape: per-seat studio plan plus usage-based API calls.

### 2. Business Bot API

For operators who need bounded workflow answers, not freeform assistants.

- `mode="business_bot"` API preset.
- Concise recommended next step surface.
- Debug trace for route, degraded state, and provenance.
- Safety/template-quarantine telemetry.

Pricing shape: monthly workspace subscription plus metered requests.

### 3. Managed Knowledge Cloud Bundle

For teams that need deployable grounded retrieval hardware.

- Validated Knowledge Cloud artifacts.
- Source provenance manifests.
- Cold-start integrity checks.
- Golden-query health evidence.

Pricing shape: managed bundle subscription or enterprise support add-on.

### 4. Enterprise AIVM Runtime

For teams that need private bounded synthetic agents.

- CHAL runtime deployment.
- AIVM device isolation.
- Audit traces.
- Custom memory/provenance policy.

Pricing shape: annual license plus integration services.

## Launch Gates

Run:

```bash
python tools/synthesus5_release_gate.py --run-focused-suite --run-runtime --fail-on-blocker
```

Do not start paid launch unless:

- CHAL API smoke passes.
- Focused Synthesus 5 suite passes through the release gate.
- Knowledge Cloud cold-start integrity passes.
- Release notes are current.
- API contract docs match runtime telemetry.
- Template leakage audit remains clean for normal-path responses.

## MVP Consumer Funnel

1. Public technical landing page: bounded NPC/business-bot runtime, not AGI.
2. Live demo: one NPC character, one business-bot workflow, trace inspector.
3. Private beta signup: studios and operators.
4. Paid pilot: API key, usage cap, support channel, signed limitation statement.
5. Expansion: managed Knowledge Cloud and custom character packs.

## What Not To Sell Yet

- Autonomous general intelligence.
- Guaranteed factual oracle behavior.
- Unbounded agent swarms.
- Full Knowledge Cloud readiness while cold-start integrity is blocked.

## Packaging Standard

Every commercial release needs:

- Release notes in `docs/release/`.
- Product packaging docs in `docs/product/`.
- A release-gate JSON report under ignored `tools/results/`.
- A clean agent log entry.
- A checklist update tied to Phase 9 or Phase 10.
