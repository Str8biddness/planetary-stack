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
- Draft handoff PR: [#9](https://github.com/Str8biddness/planetary-stack/pull/9).
- Latest independently reviewed implementation head: `9259129fc99f0e291f7286bc36c187c78843721b`.
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

## 2026-07-17 — F-090/F-120 desktop and runtime trust closure

- Base SHA: `3f56b45d` (finish-readiness handoff commit).
- Branch: `agent/finish-readiness`.
- Candidate implementation head: `4c464eec441c7befea38c54b5ae5b93d01b0ca9e`.
- Objective: close the forgeable desktop identity, legacy shell-execution, and
  unauthenticated direct-runtime stop-ships without exposing secrets to the
  browser.
- Commits:
  - `7866482` — unique account JWT secret, owner-confined SQLite state,
    nonexecuting legacy terminal tombstone, no native-shell API-key fallback,
    and honest unmounted Planetary Drive state.
  - `a67cda4` — corrected the symlink regression fixture.
  - `f07fece` — secure fresh install/redeploy secret generation and migration,
    owner-only atomic env-file replacement, invalid/default secret rotation,
    unsafe secret-path rejection, and script-level upgrade regressions.
  - `215a49b` — exact install-key middleware for every runtime API/router,
    defense-in-depth dependency authentication, pre-accept WebSocket
    authentication, loopback-only runtime launch, fail-closed boot helper, and
    removal of the Windows-specific pattern database default.
  - `967e651` — closed installer/redeploy secret-path races found during
    independent review; unsafe final paths now fail before replacement.
  - `d338056` — closed imported-ASGI/wildcard-bind bypasses with actual socket
    scope enforcement and no default module-level `app` export.
  - `24a5b17` — removed the direct legacy grid/worker/KVM bridge, simulated
    OTA/Ring-0 flow, invisible privileged-daemon consent, and universal
    privacy/online/mounted claims from the release Web Desktop.
  - `4a382cc` — made voice availability evidence-based, strengthened the
    single authenticated-WebSocket regression, and removed dead modal helpers.
  - `4c464ee` — normalized X.509 validity timestamps across packaged
    `cryptography` 41 and newer timezone-aware certificate APIs.

### Security decisions and review trail

- `SYNTHESUS_JWT_SECRET` is separate from `SYNTHESUS_API_KEY`; the installer
  generates both. A public, empty, or short JWT secret refuses desktop startup.
- Existing secure secrets survive reinstall/redeploy. Missing, short, or known-
  default API/JWT values are rotated. Secret files are regular, same-user,
  mode `0600`, written through a same-directory `umask 077` temporary, and
  atomically replaced. Symlink and nonregular paths are refused.
- `~/.synthesus` is mode `0700` and its account database is a same-user regular
  mode-`0600` file opened with `O_NOFOLLOW` where supported. A permissive
  arbitrary custom parent is refused rather than chmodded.
- `/api/terminal/run` remains only as HTTP `410` migration feedback and cannot
  execute input. The per-launch synthesusd capability plus owner-only Unix-
  socket PTY is the only browser terminal transport.
- The runtime is not a public/demo API. Every `/api`, `/query`, `/control`, and
  `/parameter-cloud/v2` path requires the exact per-install key in constant
  time. Both runtime WebSockets reject before `accept()`. Browser traffic stays
  keyless and reaches the runtime only through authenticated `synthesusd`.
- Runtime HTTP remains loopback-only. CHAL/vSource/Unisync mTLS is the node
  network plane; exposing the legacy FastAPI server is not a cluster method.
- The first independent review returned `REQUEST CHANGES`: the documented
  redeploy path omitted the new JWT secret, install creation had a pre-`chmod`
  exposure window, and invalid preserved values could brick startup. Commit
  `f07fece` superseded that rejected state.
- A second review rejected the secret replacement sequence and imported-ASGI
  bind bypass. Commits `967e651` and `d338056` superseded those states.
- Independent desktop/runtime security review approved exact head `d338056`.
- Independent UI truthfulness review rejected `24a5b17` because the initial
  voice label claimed readiness without a provider check. `4a382cc` corrected
  it. Exact-head re-review approved `4c464ee`; it confirmed that only one
  browser WebSocket remains and it carries the authenticated terminal
  subprotocol/capability.

### Exact validation

- `python3 -m py_compile` on changed Python modules: passed.
- `bash -n` on `install.sh`, `run_runtime.sh`, `redeploy_install.sh`,
  `launch_smoke.sh`, and `launch.sh`: passed.
- `git diff --check`: passed.
- Exact-head desktop/controller suite: `28 passed`; `node --check script.js`
  passed. The same exact commit streamed to the ASUS worker also produced
  `28 passed` with one fixture-only PyJWT warning.
- Earlier focused desktop/controller/runtime and directly affected API slice:
  `42 passed` with 5 existing deprecation warnings.
- Live Flask-client adversarial proof: POSTing
  `{"command":"touch /tmp/synthesus-legacy-terminal-must-not-exist",
  "admin_override":true}` returned `410` with
  `legacy_terminal_transport_removed`; the marker did not exist.
- Full runtime attempt from monorepo root: `1742 passed, 40 skipped, 3 xfailed`,
  plus two failures and two errors caused by tests resolving runtime-relative
  paths against the root working directory. This failed invocation is retained
  as evidence, not treated as a product regression.
- Full runtime attempt from the runtime directory without the monorepo on
  `PYTHONPATH`: collection stopped on two `contracts` import errors. This is the
  known packaging gap recorded under F-010/F-100.
- Correct installed-development invocation from `apps/synthesus/runtime` with
  the canonical monorepo root on `PYTHONPATH`, after the imported-ASGI and UI
  changes: `1747 passed, 40 skipped, 3 xfailed` in 112.10 seconds. No test
  failed.
- `make test-contracts`: 9 frozen schemas validated; `42 passed` under seed 1
  and `42 passed` under seed 4.
- The first local `make test-private-mesh` exposed use of the
  `cryptography>=42`-only `Certificate.not_valid_*_utc` API in the installed
  `cryptography 41.0.7` environment. `4c464ee` added an aware-UTC compatibility
  adapter without weakening validity checks.
- A subsequent sandboxed focused run reached the real listener but its child
  process returned `PermissionError: [Errno 1] Operation not permitted`; the
  sandbox was blocking the temporary loopback socket. This was not counted as
  acceptance. With explicit loopback permission, the focused mTLS suite
  produced `14 passed`.
- Canonical post-fix `make test-private-mesh`: `143 passed` under seed 1 and
  `143 passed` under seed 4.
- Canonical exact-head `make test-aivm-execution`: `21 passed, 1 skipped` under
  each seed. The skip is the explicitly opt-in physical Podman profile; all
  required tests passed and the gate left no worktree artifacts.
- `git diff --check` passed. Independent desktop/runtime and UI reviews both
  returned APPROVE on the superseding exact implementation heads.

### Remaining blockers / next exact action

- This candidate's push/check action was completed and then superseded by the
  later final-review closure below.
- Start `F-020` with one production-shaped, useful CPU model profile wired
  end-to-end from authenticated desktop intent to verified result. Do not add
  writable host mounts or bypass the signed lease/execution-authority chain.
- The installed runtime still depends on a developer-style root `PYTHONPATH`
  for canonical `contracts`; this must be fixed by the release packaging gate.
- Stale `run_web_server.py`, Docker/Procfile commands, and historical docs still
  reference the intentionally disabled imported ASGI app. They fail loudly,
  but must be retired or updated under F-010/F-100.
- No end-to-end model job, SSI namespace, certificate lifecycle, recovery,
  signed updater, or paid-beta evidence is claimed by this local security gate.

## 2026-07-17 — PR #9 final adversarial closure

- Prior published handoff: `712aa175b4fd8ba347cc3b58b806a0d9c7c27a0d`.
- Accepted implementation head: `9259129fc99f0e291f7286bc36c187c78843721b`.
- PR: [#9](https://github.com/Str8biddness/planetary-stack/pull/9),
  `agent/finish-readiness` into `main`.

### Findings discovered and superseded

- Final whole-PR review reproduced a long-whitespace upgrade bug: install and
  redeploy preserved API/JWT values that passed raw shell length checks but
  were stripped and rejected at runtime. `3b34439` made both paths rotate
  known-default, short, or whitespace-containing values and added a real
  redeploy regression. Exact desktop/controller result: `29 passed`.
- Review also found that the GitHub Drive connector embedded its token in the
  clone URL, allowing Git to persist it as origin metadata and exceptions to
  echo it. The first attempted correction was rejected three times:
  - `13bc2ba` missed mixed-case URL schemes.
  - `69a9aec` missed password/query credentials on non-HTTP schemes.
  - `dcdeaf6` still accepted passwordless userinfo outside SSH.
- Accepted `9259129` passes only a credential-free URL to `git clone`, supplies
  the token through a one-process Git configuration header scoped to exact
  HTTPS `github.com`, rejects HTTP/misdirected-token/userinfo/password/query/
  fragment variants, discards clone stderr, returns bounded generic errors,
  redacts sync/async API and job errors, removes failed temporary trees, and
  tells the user that the token is sent to GitHub for the fetch but is not
  saved in the clone URL.

### Exact accepted-head validation

- Independent connector/runtime-auth review: `21 passed` plus a manual hostile
  URL/token matrix; APPROVE `9259129`.
- Second independent connector/UI review: `33 passed`; APPROVE `9259129`.
- Local connector adversarial suite after all parser fixes: `14 passed`.
- Local desktop/controller suite: `29 passed`.
- Full runtime suite from `apps/synthesus/runtime` with monorepo `PYTHONPATH`:
  `1811 passed, 49 skipped, 3 xfailed, 39 warnings` in 119.61 seconds.
- `py_compile`, `bash -n`, `node --check`, `git diff --check`, `make doctor`,
  contracts (42 + 42), private mesh (143 + 143), and AIVM execution
  (21 passed / 1 opt-in skip under each seed) passed during this branch.
- GitHub `integration-smoke` passed on intermediate exact pushed head
  `3b34439` in run `29626442550`; the final documentation head must receive its
  own green check before ready/merge.

### Deferred advisories and exact next action

- Reconcile the memory-feature-specific `C-NNN`/disjoint-ownership language in
  `apps/synthesus/AGENTS.md` with root `F-*` integration gates before another
  cross-cutting Synthesus change. This PR does not modify the frozen memory
  contract; the full runtime suite preserves its tests.
- Explicit control-character rejection and clearing the password DOM field
  immediately after request submission are defense-in-depth follow-ups. Git
  rejected tested malformed control-character remotes before transmission.
- Same-UID observation of the transient Git child environment remains outside
  the documented threat boundary and must be revisited if the connector moves
  into a shared service identity.
- Push this doc-only closure, require exact-head GitHub CI, then mark PR #9
  ready for human/authorized merge. After merge, branch from the new `main` and
  begin `F-020`; do not represent Release A as finished.

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
