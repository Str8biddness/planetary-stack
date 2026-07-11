# MEMORY_BLUEPRINT.md — Provenance + Verification-Tagged Memory Model

| Field | Value |
|---|---|
| **Project** | Synthesus — anti-collapse crystallized memory (Mc) |
| **Repo / address** | `/home/dakin/synthesus-public` → `runtime/packages/knowledge/`, `runtime/packages/core/chal/`, `runtime/packages/api/` |
| **Scale** | 1 frozen contract + 5 consuming sections |
| **Rev** | r1 (2026-07-10) — initial |
| **Status** | DESIGNED — to build |

## Purpose (the axis / center line)
Synthesus grows its own crystallized intelligence (Mc) **only from verified, external
signal** — the user's real files, facts the user states, and answers the user confirms.
**Raw LLM generations are drafts, never facts.** Every memory item records **where it came
from (provenance)** and **how trustworthy it is (verification tier)**, and retrieval weights
`verified > grounded > unverified` so a guess can never later pose as ground truth. This is
the valve that lets Mc grow without model collapse.

## Legend
- **object line** = built & verified · **hidden line** = designed, to-build ·
  **center line** = the frozen contract (C-001) · **dimension line** = an interface
  contract with a tolerance · **phantom line** = deferred/out-of-scope.
- Tolerances are **GATE** (hard pass/fail — a security property) or **TARGET** (validate).

## Grounding (real files this extends — read them first)
- `runtime/packages/knowledge/rag_pipeline.py` — memory items are metadata dicts already
  carrying `{namespace, domain, source}` (see `retrieve()` ~L132, `add_patterns` ~L226,
  `append_patterns` ~L286). We ADD provenance + verification to that metadata.
- `runtime/packages/core/chal/memory_writeback.py` — `apply_memory_writeback(...)`, the
  existing crystallization path (called by `production_server._apply_chal_memory_writeback`
  ~L649).
- `runtime/packages/api/production_server.py` — `/api/v1/feedback` (~L2572) = the external
  confirmation intake; the query handler returns `sources`.

---

## FROZEN CONTRACT — C-001 (center line; read-only for all but its owner)
**File (NEW):** `runtime/packages/knowledge/memory_provenance.py`

```python
# Provenance: WHERE a memory item came from.
class Provenance(str, Enum):
    USER_DOCUMENT   = "user_document"    # ingested from the user's files (the drive)
    USER_STATED     = "user_stated"      # a fact the user typed/asserted
    USER_CONFIRMED  = "user_confirmed"   # an answer the user explicitly confirmed
    GROUNDED_CITED  = "grounded_cited"   # derived from + citing real user sources
    LLM_GENERATION  = "llm_generation"   # raw model output — a DRAFT, not knowledge

# Verification: HOW trustworthy (higher = more trusted).
class Verification(int, Enum):
    UNVERIFIED = 0   # llm_generation, no external check
    GROUNDED   = 1   # derived from real sources, traceable
    VERIFIED   = 2   # externally confirmed (user doc / user stated / user confirmed)

VERIFICATION_WEIGHT = {Verification.VERIFIED: 1.0, Verification.GROUNDED: 0.7,
                       Verification.UNVERIFIED: 0.3}

# The fields every memory item's metadata gains (added to the existing dict):
#   provenance: str (Provenance), verification: int (Verification),
#   provenance_refs: list[str]  (source ids/files it was derived from),
#   origin_voice: str|None      (which LLM produced it, if generated),
#   created_ts: float, confirmed_ts: float|None, confirmed_by: str|None

def classify(provenance: Provenance) -> Verification: ...
    # USER_* -> VERIFIED; GROUNDED_CITED -> GROUNDED; LLM_GENERATION -> UNVERIFIED

def gate(item: dict) -> tuple[bool, Verification]:
    """The crystallization gate. Returns (may_crystallize_to_longterm, tier).
    GATE LAW: LLM_GENERATION may NEVER be crystallized to long-term Mc as a fact
    (returns False). Only VERIFIED and GROUNDED persist. UNVERIFIED is session-only."""
```
**Tolerance C-001 [GATE]:** `gate()` returns `False` for any `LLM_GENERATION` item;
`classify()` maps USER_* → VERIFIED, GROUNDED_CITED → GROUNDED, LLM_GENERATION → UNVERIFIED.
Unit test with pasted output.

---

## PLAN (top-down component layout)
```
                 [ user files ]   [ user types a fact ]   [ user confirms an answer ]
                       |                  |                          |
                       v                  v                          v
        C-002 rag_pipeline.add/append  ──────────────────────►  metadata tagged with
             (writes items w/ provenance+verification)          provenance + verification
                       |                                                 ^
   query ──► CHAL ──► answer(+sources) ──► C-003 memory_writeback.gate ──┘ (only verified/grounded persist)
                       |                                                 ^
                       └── C-005 production_server wires gate + feedback  |
                                                                          |
   user 👍/correction ──► C-004 feedback_verification.upgrade ───────────┘ (UNVERIFIED→VERIFIED, external)
                       |
        C-002 retrieve() weights results by VERIFICATION_WEIGHT  ──►  verified out-ranks guesses
```

## ELEVATION (the layered stack)
```
  API / wiring        C-005  production_server.py  (single owner)
  crystallization     C-003  memory_writeback.py  — the gate applied
  feedback bridge     C-004  feedback_verification.py (NEW)
  storage + retrieval C-002  rag_pipeline.py — tag on write, weight on read
  FROZEN CONTRACT     C-001  memory_provenance.py (NEW) — schema/enums/gate
```

## SECTION (one request's lifecycle — cut-through)
1. Query → CHAL retrieves grounding via `rag_pipeline.retrieve()` → results carry their
   verification tier; scoring = similarity × VERIFICATION_WEIGHT (C-002).
2. Answer generated by the LLM voice → it is an `LLM_GENERATION` (UNVERIFIED) by default.
3. `_apply_chal_memory_writeback` → `memory_writeback.gate()` (C-003): if the answer was
   grounded-and-cited, persist as GROUNDED with `provenance_refs`; if raw generation,
   **do NOT persist as fact** (session-only). GATE LAW enforced.
4. Later, user confirms the answer via `/api/v1/feedback` → C-004 upgrades that item to
   USER_CONFIRMED / VERIFIED (the only external promotion path).

---

## Callouts / sections (each = a checklist section, disjoint files)
| Callout | Owns (disjoint) | Tolerance |
|---|---|---|
| **C-001** frozen contract | `runtime/packages/knowledge/memory_provenance.py` (NEW) | GATE: `gate()` rejects LLM_GENERATION; `classify()` mapping correct |
| **C-002** storage+retrieval | `runtime/packages/knowledge/rag_pipeline.py` | GATE: items store provenance+verification; retrieve() weights by tier + returns tier; backward-compatible defaults |
| **C-003** crystallization gate | `runtime/packages/core/chal/memory_writeback.py` | GATE: a raw generation is never written to long-term memory as a fact; grounded answers persist WITH provenance_refs |
| **C-004** feedback bridge | `runtime/packages/knowledge/feedback_verification.py` (NEW) | GATE: a confirm/correction upgrades the linked item to VERIFIED; upgrade requires a real external event (not self-triggered) |
| **C-005** API wiring | `runtime/packages/api/production_server.py` | TARGET: writeback calls the gate; feedback endpoint calls C-004; query response returns each source's verification tier. Existing endpoints unchanged |
| **C-006** tests | `runtime/tests/test_memory_provenance.py` (NEW) | GATE: proves anti-collapse (generation never verified), retrieval weighting, feedback upgrade, backward compat |

## Bill of materials
| File | Status |
|---|---|
| `runtime/packages/knowledge/memory_provenance.py` | to-build (C-001) |
| `runtime/packages/knowledge/feedback_verification.py` | to-build (C-004) |
| `runtime/tests/test_memory_provenance.py` | to-build (C-006) |
| `runtime/packages/knowledge/rag_pipeline.py` | to-modify (C-002) |
| `runtime/packages/core/chal/memory_writeback.py` | to-modify (C-003) |
| `runtime/packages/api/production_server.py` | to-modify (C-005) |
| distillation of VERIFIED corpus → LoRA/genome adapters | **phantom (deferred, v2)** |

## Construction sequence (dependency-gated)
1. **Phase 0 — C-001 frozen contract.** Build + unit-test the schema/enums/gate. DoD:
   pasted test showing gate rejects LLM_GENERATION. Everything downstream imports this.
2. **Phase 1 — C-002, C-003, C-004** (parallel; all consume C-001 read-only). DoD each:
   pasted test proving its GATE tolerance.
3. **Phase 2 — C-005 wiring.** DoD: pasted run of a query + a feedback-confirm showing the
   end-to-end tiering; existing endpoints still respond.
4. **Phase 3 — C-006 adversarial tests + review gate.** DoD: independent reviewer confirms
   no raw generation can reach long-term Mc as a fact.

## Anti-collapse invariant (the thing the reviewer must try to break)
> There is **no code path** by which an `LLM_GENERATION` becomes `VERIFIED` (or is
> retrieved as ground truth) without an **external** event (user confirmation, or grounding
> against real user sources). If the reviewer finds one, the build fails.
