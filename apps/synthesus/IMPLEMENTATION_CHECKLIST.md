# IMPLEMENTATION_CHECKLIST.md — memory-provenance build

Read `AGENTS.md` (laws) and `MEMORY_BLUEPRINT.md` (spec) first. Own only your section's
files. The frozen contract (C-001) is read-only for everyone but its owner. Branch:
`feat/memory-provenance`. Commit + push to the branch; PR; do not merge (Review Gate).

## SECTION C-001 — Frozen contract   Owner: ______   (build FIRST; blocks all)
- Goal: callout C-001 — `gate()` rejects `LLM_GENERATION`; `classify()` mapping correct.
- Repo: synthesus-public
- Files owned: `runtime/packages/knowledge/memory_provenance.py` (NEW)
- Depends on: none
- Tasks:
  - [ ] Implement `Provenance`, `Verification`, `VERIFICATION_WEIGHT`, `classify()`, `gate()` per the frozen contract in the blueprint.
  - [ ] DoD: pasted `python -m pytest`/`python -c` output showing `gate({provenance:"llm_generation"...}) -> (False, UNVERIFIED)` and the full `classify()` mapping.

## SECTION C-002 — Storage + retrieval   Owner: ______
- Goal: C-002 — items store provenance+verification; `retrieve()` weights by tier + returns tier; backward-compatible.
- Files owned: `runtime/packages/knowledge/rag_pipeline.py`
- Depends on: C-001 (import read-only)
- Tasks:
  - [ ] `add_patterns`/`append_patterns`: accept + persist `provenance`, `verification`, `provenance_refs`, `origin_voice`, timestamps in metadata; default legacy items to their existing meaning (user_document→VERIFIED for ingested files).
  - [ ] `retrieve()`: score = similarity × `VERIFICATION_WEIGHT[tier]`; include the tier in each returned result.
  - [ ] DoD: pasted test — a VERIFIED item out-ranks an UNVERIFIED item at equal similarity; old metadata without the fields still loads.

## SECTION C-003 — Crystallization gate   Owner: ______
- Goal: C-003 — a raw generation is never written to long-term memory as a fact; grounded answers persist WITH provenance_refs.
- Files owned: `runtime/packages/core/chal/memory_writeback.py`
- Depends on: C-001
- Tasks:
  - [ ] Apply `gate()` before any long-term write; classify the writeback candidate's provenance from its trace (grounded+cited → GROUNDED with refs; else LLM_GENERATION → not persisted as fact / session-only).
  - [ ] DoD: pasted test — an ungrounded answer produces NO long-term fact; a grounded one persists as GROUNDED with its source refs.

## SECTION C-004 — Feedback → verification bridge   Owner: ______
- Goal: C-004 — a user confirm/correction upgrades the linked memory item to VERIFIED; only a real external event triggers it.
- Files owned: `runtime/packages/knowledge/feedback_verification.py` (NEW)
- Depends on: C-001
- Tasks:
  - [ ] `upgrade_from_feedback(feedback_event)`: locate the item by answer/trace id, set provenance=USER_CONFIRMED, verification=VERIFIED, confirmed_ts/by. A correction stores the corrected text as VERIFIED.
  - [ ] DoD: pasted test — an UNVERIFIED item becomes VERIFIED only when fed a real feedback event; no self-trigger path.

## SECTION C-005 — API wiring   Owner: ______   (single owner of production_server.py)
- Goal: C-005 — writeback calls the gate; `/api/v1/feedback` calls C-004; query response returns each source's verification tier. Existing endpoints unchanged.
- Files owned: `runtime/packages/api/production_server.py`
- Depends on: C-002, C-003, C-004
- Tasks:
  - [ ] Wire `_apply_chal_memory_writeback` → C-003 gate; wire `store_feedback` → C-004 upgrade; surface each source's `verification` tier in the query response.
  - [ ] DoD: pasted run — a query returns sources with tiers; a confirm upgrades an item; `curl /api/v1/health` and an existing endpoint still respond.

## SECTION C-006 — Adversarial tests + review   Owner: ______   (reviewer ≠ any author)
- Goal: C-006 — prove the anti-collapse invariant + weighting + upgrade + backward compat.
- Files owned: `runtime/tests/test_memory_provenance.py` (NEW)
- Depends on: C-001..C-005
- Tasks:
  - [ ] Tests: (a) no path promotes LLM_GENERATION → VERIFIED without an external event; (b) generation never persisted as long-term fact; (c) retrieval weighting; (d) feedback upgrade; (e) legacy metadata loads.
  - [ ] DoD: pasted `pytest` output all green + a written statement of how the reviewer *tried and failed* to make a raw generation crystallize as a fact.
```
