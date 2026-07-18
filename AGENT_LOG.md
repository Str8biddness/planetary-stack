# Planetary Stack agent log

This is the append-only execution and handoff record for the integrated
Planetary Stack. Read this file, `AGENTS.md`, `docs/ARCHITECTURE.md`,
`MIGRATION_CHECKLIST.md`, and `FINISH_CHECKLIST.md` before continuing work.

## Current handoff

- Recorded: 2026-07-17, America/Chicago.
- Canonical repository: `Str8biddness/planetary-stack`.
- Canonical branch: `main`.
- Verified main head: `ae64d31873c751eb6faa97da2310685e9d174dac`.
- Current continuation branch: `agent/finish-readiness`.
- Current continuation checkout: `/home/dakin/planetary-stack-finish`.
- Release target: the paid same-account private-mesh product defined in
  `FINISH_CHECKLIST.md`. The public subscriber fabric is a later release.
- Current truth: the security/control-plane foundation is merged and tested,
  but the product is not finished. In particular, production end-to-end job
  wiring, Planetary Drive, certificate lifecycle, recovery, useful model
  execution, packaging, billing, and beta evidence remain open.

Do not continue from the closed stacked PRs #6 or #7. Their complete corrected
history reached `main` atomically through PR #8. Start new work from current
`origin/main` or from this continuation branch after rebasing it.

## Governing rules

1. Do not report simulated, mocked, or fixture-only behavior as physical
   acceptance.
2. A completed checkbox requires a command, result, and exact commit or
   artifact digest.
3. Preserve the trust boundaries in `docs/ARCHITECTURE.md`; the Web Desktop is
   a client, not the scheduler or security boundary.
4. Treat every network peer, workload descriptor, mutable filesystem path, and
   public node as untrusted.
5. Keep generated Knowledge Cloud artifacts in Git LFS or the artifact mirror.
6. Append new sessions below; never erase a security finding or failed attempt.
7. When a review blocks a candidate, record the rejected SHA and superseding
   SHA. Do not quietly reuse the rejected evidence.

## Integrated progression

| Gate | Merged evidence | Result |
| --- | --- | --- |
| Monorepo bootstrap | `19c43ce` plus source imports recorded in `docs/REPOSITORY_MAP.md` | Canonical sources present in one repository |
| Desktop root and optional agentic elevation | PR #1, merge `7ddfdf3` | Standard mode unprivileged; opt-in one-password session-scoped sudo; repository-root terminal |
| Knowledge Cloud production mount | PR #2, merge `b6790e6` | Manifest/hash/provenance gate, 12 mounts, 501,819 vectors at 128 dimensions, immutable base plus evolution overlay |
| Authenticated local controller | PR #3, merge `293e601` | Loopback-only `synthesusd`, required install API key, per-launch terminal capability, Unix-socket PTY backend |
| Frozen CHAL/vSource v1 contracts | PR #5, merge `cf26808` | 9 schemas; 42 adversarial tests under two hash seeds |
| Private mesh + Unisync + AIVM composite | PR #8, head `b39a8fc`, merge `ae64d31` | Exact-head independent review approved; pre-merge and post-merge GitHub smoke passed |

PR #4 was closed because it targeted the wrong branch. PR #5 is the canonical
contract merge. PR #7 was closed as superseded. GitHub marked PR #6 merged only
because its ancestor commits arrived inside the complete PR #8 merge; the
insecure intermediate state was never merged separately.

## 2026-07-17 — private mesh, transport, and execution gate

### Work completed

- Integrated the local vSource inventory, capability-constrained allocator,
  signed fenced leases, lifecycle/result verification, and durable SQLite
  state.
- Added strict signed AIVM workload/artifact admission and fail-closed host
  capability checks.
- Moved a real content-addressed object between two enrolled physical Linux
  nodes over private TCP TLS 1.3 mTLS. SSH was bootstrap/control only; it did
  not carry workload bytes.
- Bound both TLS endpoints to account/node certificate subjects, SANs, exact
  certificate and SPKI fingerprints, signed request, object digest/size,
  lease ID/digest/fence, destination role, and a context-bound receipt.
- Added durable replay fencing, locked enrollment state, explicit revocation,
  private-only listener validation, and owner-only TLS credential checks.
- Added a CPU-only rootless Podman execution gate for one operator-owned
  SHA-256 entrypoint. It requires a digest-pinned cached image, network denial,
  read-only rootfs, all capabilities dropped, no-new-privileges, private
  namespaces, cgroup v2 CPU/memory/PID limits, exact read-only input mounts,
  bounded stdout, and successful cleanup.
- Added a mandatory execution-authority verifier that consumes the exact
  manifest/account/workload/local-node/lease revision before execution.
- Sealed the complete canonical manifest bytes so mutation of the caller's
  Pydantic graph after authority consumption cannot alter resources, mounts,
  timeout, output, or evidence.

### Security review findings that changed the implementation

- Rejected an executor that trusted caller-constructed admission and lease
  objects without exact manifest-digest authority.
- Removed the writable host output mount because post-run quota checks could
  not prevent host-disk exhaustion. The accepted profile returns only a
  bounded canonical digest on stdout.
- Rejected manifest-controlled input destinations that could shadow runtime
  paths; accepted destinations are operator-owned exact paths below
  `/work/input`.
- Closed a manifest TOCTOU bug at rejected head `4d2b969`; accepted head
  `c06be6c` retained only immutable canonical bytes and added a
  mutation-after-consume regression.
- Closed a public already-open TLS socket path that skipped destination
  enrollment. Accepted head `b39a8fc` applies TLS 1.3, certificate/SPKI,
  account/node, destination-role, context, and lease checks to every upload
  path.
- A worker-generated exploratory AIVM commit `30fb743` was independently
  rejected and superseded. Do not use it as evidence or a merge base.

### Exact final validation

Candidate: `b39a8fc592862bbdf6268e67db0884dcb1fb4156`.

- `make test-contracts`: 42 passed with `PYTHONHASHSEED=1`; 42 passed with
  `PYTHONHASHSEED=4`; 9 frozen schemas validated.
- Focused TLS transport: 23 passed.
- `make test-private-mesh`: 143 passed under seed 1 and 143 passed under seed 4.
- `make test-aivm-execution`: 21 passed and 1 skipped under each seed.
- Combined AIVM admission/guard/execution: 79 passed, 1 skipped.
- Physical rootless Podman gate: 1 passed against
  `docker.io/library/archlinux@sha256:c136b06a4f786b84c1cc0d2494fabdf9be8811d15051cd4404deb5c3dc0b2e57`.
- Physical Unisync gate: two distinct enrolled nodes transferred a 65,536-byte
  object over TLS 1.3; source/destination digests matched; replay was rejected;
  central and node-local lease state became terminal.
- `py_compile` and `git diff --check`: passed.
- `make doctor`: `required_missing=0`; optional `git-lfs` and `bun` were absent
  on the ASUS validation worker.
- GitHub PR #8 `integration-smoke`: passed.
- Post-merge `main@ae64d318` workflow run `29622696458`: passed.
- Independent exact-head composite security review: APPROVE.

### Explicit non-claims

The merged gate does not provide arbitrary model execution, writable workload
outputs, production controller-to-node authority wiring, GPU isolation,
checkpoint/rescheduling, WAN relay, hostile same-UID host defense, a coherent
distributed filesystem, public third-party pooling, or production CA/HSM
operations. It is not the finished product.

## Resume procedure

```bash
cd /home/dakin/planetary-stack-finish
git status -sb
git fetch origin main
git rebase origin/main
make doctor PYTHON=/path/to/validated/python
make status
make test-contracts PYTHON=/path/to/validated/python
make test-private-mesh PYTHON=/path/to/validated/python
make test-aivm-execution PYTHON=/path/to/validated/python
```

Then select the first unchecked P0 gate in `FINISH_CHECKLIST.md`. Keep one gate
per branch/PR and append the attempt, evidence, failure, and next exact command
to this log.

## 2026-07-17 — finish-readiness audit opened

- Base SHA: `ae64d31873c751eb6faa97da2310685e9d174dac`.
- Branch: `agent/finish-readiness`.
- Objective: create the durable definition of done, then close as many P0
  release blockers as can be validated safely in this session.
- Documentation added: root `AGENT_LOG.md`, `FINISH_CHECKLIST.md`, and README
  navigation.
- Open stop-ship findings discovered during the audit:
  - `apps/synthesus/desktop/accounts.py` accepts the public fallback
    `dev_secret_change_me`; `install.sh` does not generate a unique JWT secret.
    A local client that can forge the desktop JWT may mint a terminal
    capability through `/api/ipc/session`.
  - `apps/synthesus/desktop/synthesus_native_shell.py` exposes the legacy
    `/api/terminal/run` route without the hardened controller capability and
    executes client text with `subprocess.check_output(..., shell=True)`.
  - The legacy Web Desktop contains canned OTA/Ring-0 success animation,
    unconditional privileged-daemon consent language, inaccurate universal
    no-egress privacy wording, and direct optional grid calls outside the
    authenticated controller boundary.
- Status: OPEN. Do not release until the findings above are removed, disabled,
  or replaced with authenticated fail-closed implementations and regression
  evidence.
- Next exact action: read the nested Synthesus agent contracts, trace route and
  installer callers, patch the smallest safe boundary, then run focused desktop
  security tests plus the monorepo regression matrix.

## Session entry template

```markdown
## YYYY-MM-DD — GATE-ID short title

- Base SHA:
- Branch:
- Objective:
- Files changed:
- Security decisions:
- Commands and exact results:
- Physical evidence and artifact digests:
- Review verdict:
- PR and final SHA:
- Remaining blockers / next exact command:
```
