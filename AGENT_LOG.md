# AGENT_LOG.md — session continuity for memory-provenance build

## 2026-07-11 — SW-1..SW-5 Persona-Clone Expert Swarm

### What
New package `runtime/packages/swarm/` (disjoint from `foreman/`):
- **SW-1** `registry.py` — Expert registry (persona + system_prompt + namespace + optional adapter_ref). Deltas only.
- **SW-2** `scheduler.py` + `model_client.py` — ONE shared Ollama base model; fan-out expert system prompts; missing expert/adapter → degraded, no fabricated text.
- **SW-3** `arbiter.py` — merge via `QuadBrainOrchestrator`; SwarmAnswer.sources carry C-001 verification tiers.
- **SW-4** `adapters/` — LoRA/persona-delta DATA validation; refuse executables; base-compat check.
- **SW-5** `envelope_firecracker.py` — loud BLOCKED/NotImplementedError on single-GPU local host.

### Why
GPU-bound inference: never N model copies. Isolation between cooperating experts is forbidden on one GPU.

### Proof
`pytest runtime/tests/test_persona_clone_swarm.py` → 11 passed (real Ollama llama3.2:3b).

### Pre-review hardening (same branch)
- Honest v1 boundary: `adapter_applied=False`, `adapter_status=persona_prompt_delta_only|validated_not_applied`.
- Arbiter prefers expert seed prose over template CGPU surfaces (`swarm: [expert:…]`).
- Export `SwarmRuntime` + `README.md` quick start.
- Stricter persona-marker tests; all `model_id`s must be the single base.

### Branch
`feat/persona-clone-swarm` — commit per section; do not merge without review.

---

## 2026-07-11 — REQUEST CHANGES fix (reviewer anti-collapse hole)

### Coordination note — C-001 unfreeze (Law #4 security exception)
- **Spec rev:** MEMORY_BLUEPRINT.md r1 → **r2**
- **Why unfreeze frozen contract:** Reviewer found `gate()` trusted a caller-supplied
  `verification` tier, so `gate({provenance:grounded_cited, verification:2})` returned
  VERIFIED. Latent (writeback re-derives) but contract-level hole.
- **Fix:** `gate()` always re-derives via `classify(provenance)`; caller tier ignored.
  Same for `resolve_legacy_metadata` / `annotate_metadata` authority.

### Blocker fix — C-004 human proof (invert polarity)
- **Hole:** `_event_is_external_confirm` only rejected self-declared bots. Omitting
  markers + `{action:"confirm"}` looked like a human confirm. API-key auth is not
  human auth → agents with the key could forge VERIFIED (model collapse path).
- **Fix (Foreman allow-list lesson):** deny-by-default positive human proof:
  1. `actor_kind == "human"`
  2. `channel ∈ HUMAN_CHANNELS` allow-list
  3. `confirmed_by` acceptable human identity (blocks `auth:…`, agents, placeholders)
  4. **Server-issued single-use `human_attestation`** minted only after
     `X-Synthesus-Human-Session` matches `SYNTHESUS_HUMAN_SESSION_SECRET`
- **C-005:** `POST /api/v1/human/attestation` for minting; `/api/v1/feedback` never
  invents human proof from the API key; passes client fields through only.
- **Reviewer probe now fails:**
  `verify_human_confirm_proof({action:"confirm", answer_id:"a1"}) → False
  (missing_human_actor_kind)`

### Files touched this fix
- `runtime/packages/knowledge/memory_provenance.py` (C-001 r2)
- `runtime/packages/knowledge/feedback_verification.py` (C-004)
- `runtime/packages/api/production_server.py` (C-005)
- `runtime/tests/test_memory_provenance.py` (C-006)
- `MEMORY_BLUEPRINT.md` (r2)
- this log

---

## 2026-07-11 — feat/memory-provenance (build agent)

### Mission
Implement provenance + verification-tagged memory model so crystallized Mc grows
only from verified external signal. Anti-collapse invariant: no path lets
`LLM_GENERATION` become `VERIFIED` or long-term ground truth without an external
event.

### C-001 — Frozen contract
- **What:** Added `runtime/packages/knowledge/memory_provenance.py` with
  `Provenance`, `Verification`, `VERIFICATION_WEIGHT`, `classify()`, `gate()`,
  plus helpers `annotate_metadata`, `resolve_legacy_metadata`, `weight_for`.
- **Why:** Center-line contract every consumer imports; gate is the anti-collapse
  valve (`LLM_GENERATION` → always `(False, UNVERIFIED)` even if tier is forged).
- **Proof:** unit smoke + `tests/test_memory_provenance.py` C-001 cases green.

### C-002 — Storage + retrieval (`rag_pipeline.py`)
- **What:** `add_patterns` / `append_patterns` enrich metadata with provenance
  fields; `ingest_documents` tags `USER_DOCUMENT`/`VERIFIED`; `retrieve()` ranks
  by `similarity × VERIFICATION_WEIGHT` and returns `verification` on each source.
  Legacy metadata loads via `resolve_legacy_metadata` (user_docs→VERIFIED; else GROUNDED).
- **Why:** Verified knowledge must out-rank drafts at equal similarity.

### C-003 — Crystallization gate (`memory_writeback.py`)
- **What:** `classify_writeback_provenance` + `gate()` before any long-term store.
  Grounded+cited traces → `GROUNDED_CITED` with `provenance_refs`; raw/trace-only
  → `LLM_GENERATION` → rejected (`session_only`, reason
  `gate_rejected_llm_generation_or_unverified`). CHAL ref list preserved under
  `chal_provenance`.
- **Why:** Stop ungrounded LLM answers from crystallizing into Mc.

### C-004 — Feedback bridge (`feedback_verification.py`)
- **What:** `upgrade_from_feedback(event, items=...)` upgrades a linked item to
  `USER_CONFIRMED`/`VERIFIED` only for real external confirms/corrections.
  Self-triggered / model-origin events refused. Corrections rewrite content as VERIFIED.
- **Why:** Sole promotion path from draft → verified is the user.

### C-005 — API wiring (`production_server.py`)
- **What:** `_apply_chal_memory_writeback` passes full `trace` into writeback (gate).
  `/api/v1/feedback` calls C-004 and returns `verification_upgrade`. Query sources
  already surface tiers from C-002 retrieve. Health endpoint unchanged.
- **Why:** End-to-end external signal path.

### C-006 — Adversarial tests (`test_memory_provenance.py`)
- **What:** Tests (a)–(e) plus multi-vector adversarial summary that forges tier,
  launders via crystallized target, self-triggers feedback, etc. — all fail closed.
- **Collateral:** Updated `test_chal_memory_policy.py` /
  `test_chal_api_memory_writeback.py` expectations for C-001 metadata shape and
  gate rejection of ungrounded critic-only writebacks (required by anti-collapse).

### Anti-collapse statement (reviewer attempt)
Tried and failed to crystallize a raw generation as a fact by:
1. Forging `verification=2` on `provenance=llm_generation` through `gate()` → forced UNVERIFIED, rejected.
2. `annotate_metadata(..., verification=VERIFIED)` on LLM_GENERATION → forced UNVERIFIED.
3. Writeback with only `trace://` self-ref / critic-only provenance → gate rejects, zero store records.
4. `target_memory_type=crystallized` laundering → still gate-rejected.
5. Feedback with `self_triggered=True` or `origin=llm` → upgrade refused; tier stays UNVERIFIED.
6. Low rating (2) → no upgrade.

The only successful path to VERIFIED was a real external confirm/correction event
via `upgrade_from_feedback`, which sets `USER_CONFIRMED`.

### Test commands (from `runtime/` with venv)
```
python -m pytest tests/test_memory_provenance.py tests/test_chal_memory_policy.py tests/test_chal_api_memory_writeback.py -q
```
All green at handoff (35 passed when API deps present; 2 skipped without fastapi).

## 2026-07-11 — Multi-phase autonomous finish (native-kernel / polish / module-audit)

### Phase 1 feat/native-kernel — DONE
- Compile fixes: resonance_observer includes, geometric_optics pybind, GeometricEngine shared_ptr, voice_vcu memory, test_emul link.
- IPC: main.cpp JSON query parse + dual keys; bridge.py IPC payload; hemisphere_bridge resolves `kernel/build/zo_kernel`, KernelBridge auto-IPC.
- Proof: `make` builds `zo_kernel` + `_synthesus_kernel*.so`; stdin IPC JSON response; log `KernelBridge initialized in ipc mode`; left query `source=cpp_kernel`.

### Phase 2 feat/polish — DONE
- `scikit-learn==1.8.0` pin in runtime/requirements.txt; retrieve without InconsistentVersionWarning.
- llm_device DEFAULT_SYSTEM_PROMPT VERBATIM codes; live Ollama answered `ZXQ-7741-BETA`.
- production_server startup RAG embedder warm-up; cold ingest 4.66s vs after-warm ~0s.

### Phase 3 feat/module-audit — DONE
- CAPABILITY_LEDGER.md: REAL/STUB/BROKEN with import evidence.
- Fixed: core/memory/__init__.py garbage, unpc_engine/__init__.py syntax, production_server loot/dialogue imports use real core modules not ml stubs.
- Honest stubs left as STUB (core/ml pass classes).

Do NOT merge — Claude reviews.

## 2026-07-11 — feat/launch-smoke (final pre-QC pass)

Merged into this branch: native-kernel, polish, module-audit.

Additional launch polish:
- production_server: HemisphereBridge() uses package kernel path resolver (not PROJ_ROOT/zo_kernel)
- install.sh: SYNTHESUS_HUMAN_SESSION_SECRET + scikit-learn==1.8.0 pin in pip critical list
- core/ml/*: re-export real reasoning/core modules (no pass stubs)
- tools/redeploy_install.sh: safe rsync preserve env/venv/data
- tools/launch_smoke.sh: real HTTP/kernel/sklearn checks
- LAUNCH_CHECKLIST.md + kernel/README.md (IPC vs pybind honesty)

Proof: ml re-exports → reasoning/core real files; zo_kernel IPC ok;
redeploy generates human secret; smoke pass=4 offline (health fail until runtime up).
