# AGENT_LOG.md — session continuity for memory-provenance build

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
