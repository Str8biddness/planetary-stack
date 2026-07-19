# Planetary Stack production finish checklist

This document defines “finished.” `MIGRATION_CHECKLIST.md` controls repository
consolidation; this checklist controls product readiness. A box may be checked
only when its acceptance evidence is linked from `AGENT_LOG.md` and survives a
fresh supported-machine or physical-cluster run.

## Finish lines

### Release A — paid private-mesh v1

Planetary Stack is commercially finished for v1 when an ordinary subscriber
can install it on two to five machines they own, enroll those machines into one
account, use the Web Desktop to store files and run a useful supported model
job, survive a worker outage, understand resource/cost/privacy state, update or
uninstall safely, and receive support without developer intervention.

### Release B — community resource fabric

The public fabric is finished only after Release A is stable and untrusted
contributors can supply resources with enforceable isolation, verification,
metering, payments, abuse response, regional controls, and positive unit
economics. Release B is not required to call Release A a finished product.

## Evidence rules

- [ ] Every completed gate names an exact commit and clean GitHub check.
- [ ] Security-sensitive gates receive independent adversarial review.
- [ ] Network, hardware, installation, recovery, and update gates use physical
  machines; mocks are supplemental only.
- [ ] Failure tests prove explicit error/degraded states and no simulated
  success.
- [ ] Performance, cost, energy, and environmental claims include reproducible
  measurements and conditions.

## P0 — Release A blockers

### Immediate stop-ship findings

- [x] Remove the public desktop JWT fallback, generate a unique owner-only
  secret during installation, and refuse startup when the secret is absent or
  known-default. Evidence: `7866482`, `f07fece`, `967e651`, `3b34439`; PR #9
  review.
- [x] Remove or disable the unauthenticated legacy `/api/terminal/run`
  `shell=True` endpoint; all browser terminal operations must use the
  authenticated controller capability and Unix-socket PTY boundary. Evidence:
  `7866482`; live nonexecution proof and exact-head review in `AGENT_LOG.md`.
- [x] Remove/hide simulated OTA and Ring-0 success UI until a signed update
  transaction exists and reports verifiable state. Evidence: `24a5b17`.
- [x] Replace unconditional privileged-daemon consent and universal no-egress
  privacy language with accurate, feature-specific opt-in disclosure.
  Evidence: `24a5b17`, `4a382cc`.
- [x] Remove direct browser calls to legacy optional grid endpoints or route
  them through authenticated `synthesusd` APIs with no query-string secrets.
  Evidence: `24a5b17`, `4a382cc`; exact-head review confirmed one remaining
  WebSocket, the authenticated terminal capability.
- [x] Require the exact unique install key on every private runtime HTTP and
  WebSocket surface, enforce the actual loopback socket, and prevent an
  imported-ASGI wildcard-bind bypass. Evidence: `215a49b`, `d338056`.
- [x] Keep GitHub access tokens out of clone URLs/origin metadata and
  logs/errors; restrict ephemeral token delivery to exact HTTPS `github.com`
  and accurately disclose the network fetch. Evidence: `9259129`; two
  independent adversarial approvals.

Acceptance: focused adversarial tests prove JWT forgery, legacy shell execution,
unauthenticated grid access, and simulated update success are impossible in the
release surface.

### F-001 Canonical source, licensing, and release identity

- [ ] Declare the canonical writable implementation for CHAL, vSource,
  Unisync, AIVM, controller, desktop, frontend, and Knowledge Cloud.
- [ ] Quarantine or archive duplicate runtime trees with provenance and dated
  removal notices.
- [ ] Resolve `aivm-planetary-os` licensing and choose a license for new
  integration code.
- [ ] Run a history-aware secret scan, remediate findings, and rotate exposed
  credentials before any public repository or external beta.
- [ ] Generate an SBOM and third-party license/notice bundle.
- [ ] Define product/protocol/artifact semantic versions and a signed release
  manifest.

Acceptance: one signed version identifies every source revision, dependency,
license, schema, binary, installer, and Knowledge Cloud artifact.

### F-010 Reproducible bootstrap, build, and CI

- [ ] Provide one documented bootstrap command for supported Linux.
- [ ] Pin Python, Node/Bun, compiler, Podman, Ollama, and optional CUDA versions.
- [ ] Add formatting, linting, typing, unit, integration, security, installer,
  upgrade, and rollback jobs with path-aware CI.
- [ ] Provide a reproducible devcontainer/Nix/container build environment.
- [ ] Build release artifacts from a clean runner without developer-home paths.
- [ ] Reproduce the same signed artifact twice from identical source inputs.

Acceptance: a fresh supported machine bootstraps and passes the complete release
matrix from one documented command.

### F-020 End-to-end useful workload

- [ ] Wire authenticated Web Desktop intent through `synthesusd`, CHAL,
  vSource placement, signed fenced lease, Unisync transfer, node agent, AIVM,
  verified result, and desktop presentation.
- [x] Replace the test authority verifier with persistent production issuer,
  scheduler, and node-agent verification/consumption wiring. Evidence:
  PR #10 (`PersistentExecutionAuthority`, node-agent executor wiring);
  physical use on `dakin-MS-7C95` with scheduler-signed leases in the
  2026-07-18 mesh-workload gate
  (`docs/evidence/F020_MESH_WORKLOAD_PHYSICAL_2026-07-18.md`).
- [x] Support at least one useful bounded model workload, not only SHA-256.
  Evidence: PR #10 execution spine; physical rootless-Podman ONNX
  classification on worker `dakin-MS-7C95` at exact head `f38a149`, image
  `sha256:4933984e…`, model `575d5666…` (AGENT_LOG 2026-07-18 physical gate).
- [x] Return a content-addressed, immutable result with provenance and resource
  evidence. Evidence: same physical gate — result JSON content-addressed
  (0400, owner-only store), byte-identical across two leases, with signed
  evidence including image/entrypoint/lease binding and `wall_time_ms`.
- [ ] Implement cancel/stop and prove terminal cleanup at every layer.
- [ ] Reject stale, duplicated, substituted, expired, cross-account, wrong-node,
  oversized, and unsupported requests before workload execution.

Acceptance: a fresh three-node cell completes a useful model job from the Web
Desktop and independently verifies its result without in-process shortcuts.

### F-030 Node enrollment and identity lifecycle

- [ ] Create node identity during installer-driven enrollment with explicit
  account/user confirmation.
- [ ] Keep private keys hardware-backed where available and mode-confined
  otherwise.
- [ ] Implement CA/intermediate custody, certificate issuance, renewal,
  rotation, expiry warnings, and online revocation distribution.
- [ ] Add lost-device removal, account recovery, key recovery/rotation, and
  ownership-transfer policy.
- [ ] Prevent rollback or resurrection of revoked enrollment state.
- [ ] Audit every enrollment, renewal, rejection, and revocation without
  logging credentials.

Acceptance: enroll, rotate, expire, revoke, recover, and replace nodes across
three physical machines without manual source edits or copying private keys.

### F-040 Node service and resource controls

- [ ] Package the node agent as an unprivileged supervised user service.
- [ ] Provide visible opt-in CPU, RAM, disk, bandwidth, GPU, thermal, power,
  schedule, pause, and stop controls.
- [ ] Enforce controls in the OS boundary and revalidate them per lease.
- [ ] Report signed inventory/health with TTLs and explicit degraded states.
- [ ] Prevent sleep/battery/thermal/storage-pressure policies from corrupting
  work or the host.
- [ ] Support and test the documented minimum Linux hardware/driver matrix.

Acceptance: limits cannot be exceeded by an adversarial workload and the owner
can instantly pause contribution without leaving active authority.

### F-050 Transport and private-cell networking

- [x] Prove one private-LAN TLS 1.3 mTLS object transfer between two enrolled
  physical nodes with exact peer and lease binding. Evidence: PR #8 / `b39a8fc`.
- [ ] Route every supported node-to-node operation through an authenticated,
  authorized, bounded, replay-protected transport.
- [ ] Implement local memory/PCIe transport without weakening authority.
- [ ] Add safe discovery that reveals no usable authority.
- [ ] Add NAT traversal and a mutually authenticated relay fallback without
  automatic unsafe router configuration.
- [ ] Add transfer retry/resume, bandwidth control, cancellation, and cleanup.
- [ ] Test hostile framing, corruption, truncation, replay, slow peers, and
  connection loss on physical nodes.

Acceptance: two-to-five machines communicate across supported home-network
topologies while public/wildcard listeners and unenrolled peers fail closed.

### F-060 Planetary Drive / SSI storage

- [ ] Enroll only an owner-selected bounded directory or expansion-drive volume
  per node; never expose or consume a whole disk implicitly.
- [ ] Store encrypted immutable objects in node-local Unisync CAS roots.
- [ ] Define signed file manifests and a versioned per-account namespace.
- [ ] Add vSource storage inventory, reservations, replica placement, and
  node-signed durability receipts.
- [ ] Implement read-only `SSI-RO-001`: the same namespace is visible in the
  Web Desktop and terminal on all enrolled machines and survives one replica
  going offline.
- [ ] Implement atomic file replacement, rename, tombstone deletion, version
  history, snapshot, restore, and explicit conflict siblings.
- [ ] Add local drafts and honest offline/syncing/durable/under-replicated/
  unavailable/conflict states.
- [ ] Add account/device key wrapping, recovery keys, rotation, and revocation.
- [ ] Enforce logical/physical/version/cache/object-count quotas and host free-
  space reserves before accepting writes.
- [ ] Add verified repair, scrub, drain, retention, and fenced garbage
  collection that never deletes the sole good replica.
- [ ] Project the namespace through authenticated loopback APIs and optional
  owner-only FUSE; use `nosuid,nodev,noexec` and no `allow_other`.

Acceptance: a file written once is versioned, encrypted, replicated to separate
physical nodes, readable from the common projection after one node disconnects,
repairable after corruption, quota bounded, and restorable after deletion.

### F-070 AIVM workload isolation and result safety

- [x] Prove the fixed CPU SHA-256 profile in rootless Podman with immutable
  input, canonical stdout result, resource limits, cleanup, replay rejection,
  exact authority, and sealed-manifest TOCTOU defense. Evidence: PR #8 /
  `b39a8fc`.
- [ ] Define a small allowlisted set of useful model entrypoints and immutable
  images.
- [ ] Add quota-backed or CAS-imported writable results without exposing a
  writable host mount.
- [ ] Add secrets/data mounts with least privilege and deterministic cleanup.
- [ ] Add GPU isolation with device/IOMMU/driver policy and physical escape
  testing before enabling GPU workloads.
- [ ] Add checkpoint import/export and bounded preemption.
- [ ] Remove or isolate every remaining raw `marshal`, pickle, `eval`, arbitrary
  shell, bytecode, and unauthenticated execution path.
- [ ] Define the threat boundary for same-UID hostile processes or place the
  executor under a separate confined service identity.

Acceptance: supported useful workloads cannot escape, access undeclared data,
exceed resources, retain authority, mutate evidence, or simulate success.

### F-080 Scheduling, health, and recovery

- [ ] Run vSource as a persistent service/API rather than an in-process test
  object.
- [ ] Schedule only same-account nodes for Release A.
- [ ] Implement heartbeats, TTL expiry, disappearance detection, retry budgets,
  lease terminalization, checkpoint/resume, and rescheduling.
- [ ] Prevent duplicate non-idempotent results during timeout/race recovery.
- [ ] Add topology, capability, thermal, power, bandwidth, and owner-policy
  placement constraints.
- [ ] Test controller restart, scheduler restart, network partition, clock
  skew, disk full, corrupt state, and worker power loss.

Acceptance: useful jobs finish or fail explicitly while any one worker and the
local controller are restarted or disconnected at defined failure points.

### F-090 Desktop and product experience

- [ ] Provide one signed Standard launcher and one clearly distinct optional
  Agentic launcher with correct icon/menu integration.
- [ ] Implement guided account setup, node enrollment, resource contribution,
  Planetary Drive, job submission, progress, result, cancellation, and support
  flows.
- [ ] Show real node, storage, sync, lease, workload, failure, and privacy state.
- [ ] Meet keyboard, screen-reader, contrast, scaling, and reduced-motion
  accessibility requirements.
- [ ] Remove dead controls, mock success, placeholder commerce, and legacy
  network bridges from production paths.
- [ ] Test first-run and daily-use flows with non-developer users.

Acceptance: ten users complete installation, enrollment, first file, and first
useful job without shell commands or developer intervention.

### F-100 Installer, updater, rollback, and removal

- [ ] Produce a signed installer for the supported Linux target.
- [ ] Preflight dependencies, ports, filesystem permissions, disk, GPU/driver,
  Podman rootless/cgroup/seccomp, and optional services.
- [ ] Install least-privilege services, desktop entries, configuration, and
  owner-only state predictably.
- [ ] Implement signed atomic updates, schema/data migrations, rollback, and
  channel selection.
- [ ] Preserve user files and keys across update; never preserve revoked
  authority accidentally.
- [ ] Provide complete uninstall, optional secure data removal, and node drain.
- [ ] Test clean install, upgrade from every supported version, failed update,
  rollback, reinstall, and uninstall on physical supported machines.

Acceptance: a non-developer can safely install, update, roll back, and remove
the product without losing opted-in user data or leaving privileged residue.

### F-110 Observability, privacy, and operations

- [ ] Add structured owner-visible local logs and audit records with stable
  error codes and no secrets/prompts/private content.
- [ ] Add bounded metrics for health, jobs, storage, transfer, retries,
  isolation, and resource use.
- [ ] Make crash reporting and remote telemetry explicit opt-in with preview,
  retention, deletion, and disable controls.
- [ ] Publish health diagnostics and evidence export suitable for support.
- [ ] Add backup/restore for control metadata and tested disaster recovery.
- [ ] Define SLOs, alerts, incident roles, status communication, and on-call
  ownership for paid beta.

Acceptance: operators detect and diagnose supported failures without collecting
raw user content, and recover control metadata from a tested backup.

### F-120 Security and supply-chain release gate

- [ ] Complete threat models for desktop/controller, identity, scheduler,
  transport, storage, sandbox, update, billing, and public APIs.
- [ ] Add dependency, container, SBOM, secret, SAST, fuzz, and configuration
  scanning with blocking severity policy.
- [ ] Pin and verify dependencies, images, actions, release builders, and
  artifact signatures/provenance.
- [ ] Complete independent application, infrastructure, and protocol reviews;
  resolve all critical/high findings.
- [ ] Run physical red-team tests for escape, cross-account access, replay,
  rollback, path traversal, disk exhaustion, credential theft, and malicious
  update.
- [ ] Publish vulnerability disclosure, security contact, response timeline,
  and supported-version policy.

Acceptance: no open critical/high finding, reproducible signed supply-chain
evidence, and documented incident/vulnerability handling.

### F-130 Entitlements, billing, and unit economics

- [ ] Define Personal and Pro features, limits, prices, cancellation, refunds,
  trial, and grace behavior.
- [ ] Implement account subscription entitlement with signed local cache and
  explicit offline/degraded behavior.
- [ ] Meter only billable useful work with idempotent events and reconciliation.
- [ ] Enforce quotas/rate limits consistently across controller, scheduler,
  storage, transfer, and execution.
- [ ] Keep local base operation available during billing/control interruption
  according to published policy.
- [ ] Measure cost per successful workload, support burden, payment fees,
  storage, bandwidth, and target gross margin.
- [ ] Test webhook replay, duplicate charge, stale entitlement, cancellation,
  refund, clock skew, and provider outage.

Acceptance: five real subscribers are billed correctly, can cancel/refund, and
retain the promised offline/local behavior with positive measured contribution
margin.

### F-140 Legal, support, and beta proof

- [ ] Publish privacy policy, terms, acceptable-use policy, license notices,
  data-processing/deletion terms, refund policy, and security contact.
- [ ] Define model/data licensing responsibilities and prohibited workloads.
- [ ] Establish support intake, diagnostics consent, severity targets, and
  escalation.
- [ ] Recruit 10–25 design partners across the supported hardware matrix.
- [ ] Record activation, first-use success, weekly retention, successful jobs,
  sync durability, incidents, support time, and willingness to pay.
- [ ] Obtain explicit go/no-go signoff from engineering, security, operations,
  product, legal, and support owners.

Acceptance: at least ten users install without developer intervention, five
pay, retained users complete useful weekly work, and all release owners sign
off with no unresolved launch blocker.

## P1 — Release B community resource fabric

### F-200 Public identity and isolation

- [ ] Separate provider, tenant, operator, billing, and recovery trust domains.
- [ ] Add hardware/software attestation where required and reputation only as
  supplemental evidence.
- [ ] Encrypt tenant data so storage-only providers lack plaintext keys.
- [ ] Add redundant execution/challenge verification and malicious-provider
  response.
- [ ] Prove cross-tenant confidentiality and cleanup on adversarial public
  nodes.

### F-210 Public scheduling and networking

- [ ] Add Internet/relay transport, regional/data-residency controls, deletion
  guarantees, and denial-of-service protection.
- [ ] Add provider schedules, consent, budgets, drain, maintenance, and wear/
  power estimates.
- [ ] Restrict the initial catalog to bounded interruptible workloads.
- [ ] Add carbon/price-aware placement with honest measurement methodology.
- [ ] Qualify low-latency cells separately from high-throughput nodes.

### F-220 Marketplace accounting and abuse

- [ ] Implement tamper-evident metering, reconciliation, contributor credits,
  tax/payment compliance, fraud controls, disputes, and reserve policy.
- [ ] Add workload moderation, customer/provider sanctions, investigation,
  evidence retention, and appeals.
- [ ] Measure supply utilization and paid demand before subsidizing capacity.
- [ ] Demonstrate positive unit economics after credits, verification, storage,
  bandwidth, payments, fraud, and support.

### F-230 Public reliability and launch

- [ ] Add redundant control-plane, relay, artifact, metadata, billing, and
  observability services.
- [ ] Test region failure, control-plane failover, key compromise, provider
  collusion, billing outage, and mass revocation.
- [ ] Publish status, incident history, SLO/SLA, capacity, cost, energy, and
  environmental measurement methodology.
- [ ] Run a 25–100-node trusted beta before opening general contribution.

Acceptance: verified customer work pays contributors from revenue, survives a
regional failure, meets published SLOs, and maintains target gross margin with
no unresolved critical/high security finding.

## Recommended execution order

1. `F-020` end-to-end useful workload.
2. `F-030` production identity lifecycle.
3. `F-060` `SSI-RO-001`, followed by safe writable/versioned storage.
4. `F-080` disappearance, retry, and rescheduling.
5. `F-040` complete resource controls and supervised node service.
6. `F-070` useful model profile and result import.
7. `F-090` and `F-100` non-developer UX/install/update.
8. `F-110`, `F-120`, `F-130`, and `F-140` operations and paid-beta gate.
9. Release B only after Release A evidence is stable.
