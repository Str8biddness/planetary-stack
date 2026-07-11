# AGENTS.md — laws for any agent working in this repo

**Before writing a single line of code, read, in order:**
1. This file (the laws).
2. `MEMORY_BLUEPRINT.md` — the controlling spec for the current build (the provenance +
   verification-tagged memory model). Find your callout `C-NNN` and its tolerance.
3. `IMPLEMENTATION_CHECKLIST.md` — the section you own and its **disjoint file list**.

Do not touch files outside your section's owned list. The frozen contract (C-001,
`runtime/packages/knowledge/memory_provenance.py`) is **read-only** for everyone except
its owner.

## Workflow for recruited agents
- Work on a **feature branch** (`feat/memory-provenance`), never directly on `main`.
- **Commit + push to your branch frequently** (never leave work as only-local commits).
- Open a **PR**; do **not** merge to `main` yourself — an independent reviewer verifies
  against your callout's tolerance first (Law #8). Only a passed review merges.

## THE LAWS (non-negotiable)
1. **NO MOCK IMPLEMENTATIONS OF ANYTHING.** No hardcoded result strings, no
   `return "success"` placeholders, no `sleep()` pretending to work, no canned output, no
   tests asserting hardcoded literals instead of running real code. Can't build it yet →
   mark it `BLOCKED` with a reason. **A real error beats a fake success.**
2. **TEST OR IT DIDN'T HAPPEN.** Work is done only with **pasted real run output** proving
   the callout's tolerance.
3. **CITE YOUR CALLOUT.** Every commit/PR names the `C-NNN` it advances and shows proof.
4. **STAY IN YOUR LANE.** Edit only files your section owns. The frozen contract is
   read-only except for its owner.
5. **DEGRADE LOUDLY.** Unavailable subsystem → log an explicit reason and report DEGRADED.
   Never silently substitute a fake.
6. **NO NEW GRAND CLAIMS.** Claim only what passes its tolerance.
7. **DOCUMENT AS YOU BUILD.** Every change leaves an `AGENT_LOG.md` entry (what/why/which
   callout). The next agent picks up without re-deriving.
8. **REVIEW BEFORE MERGE.** No section is done on the author's say-so. An independent
   reviewer adversarially checks each section against its tolerance (is it a mock? a hollow
   test? does a raw generation slip through the gate?). Authors don't self-approve.
9. **ISOLATE WORKSPACES.** Own clone / worktree + branch. Commit + push frequently;
   integrate via PR.

## The one domain law for THIS build (the reason the feature exists)
**NEVER crystallize a raw LLM generation as a fact.** The only path from `unverified` to a
higher trust tier is an **external** signal (a user confirmation, or grounding against real
user sources). A model may never self-promote its own output to "verified." Violating this
re-introduces model collapse — it is a GATE failure, not a style nit.
