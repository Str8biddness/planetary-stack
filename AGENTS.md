# Planetary Stack Agent Contract

This repository is the integration home for Planetary OS, Synthesus, CHAL,
vSource, Unisync, AIVM, and the Knowledge Cloud.

## Before changing code

1. Read `MIGRATION_CHECKLIST.md` and identify the active phase.
2. Read `docs/ARCHITECTURE.md` and preserve the declared ownership boundaries.
3. Read the nearest nested `AGENTS.md` before changing an imported component.
4. Do not modify an imported component and its former standalone repository in
   the same change unless the synchronization route is explicit.

## Engineering laws

- No simulated success, fake worker results, unsafe `eval`/raw bytecode
  execution, or security-by-obscurity.
- Every completed checklist item needs a real validation command and result.
- Public nodes are untrusted. Authentication, authorization, isolation,
  accounting, and result verification are architectural requirements.
- The WebSocket desktop is a client surface. It must not become the trust
  boundary or the distributed scheduler.
- Large Knowledge Cloud artifacts stay in Git LFS or the artifact mirror.
  Never convert them into ordinary Git blobs.
- Preserve component license files and provenance while the repository uses
  mixed licensing.
- Degrade explicitly when optional hardware or services are unavailable.

## Repository workflow

- Work on a branch.
- Keep commits scoped to one migration or implementation gate.
- Update `MIGRATION_CHECKLIST.md` when a gate changes state.
- Prefer root-level integration tests plus the component's own tests.
- Do not retire a standalone repository until its monorepo replacement has
  passed the same or stronger release gate.

