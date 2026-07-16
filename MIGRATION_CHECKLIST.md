# Planetary Stack: start-to-finish checklist

This is the controlling checklist for consolidating the repositories and
shipping the first paid Planetary product. A checkbox is complete only when
its acceptance gate has real evidence.

## Phase 0 — repository safety and decisions

- [x] Select the monorepo name: `planetary-stack`.
- [x] Inventory local repositories, branches, remotes, sizes, licenses, and
  dirty state.
- [x] Confirm `synthesus-ultra-` and `synthesus-os` have identical tracked
  trees at `db72d05`; import only one copy.
- [ ] Clarify or add the license for `aivm-planetary-os`.
- [ ] Rotate and remove any committed credentials before a public-node alpha.
- [ ] Decide the license for new cross-component integration code.

Acceptance gate: every imported source has an origin, exact commit, license,
and secret-scan result recorded in `docs/REPOSITORY_MAP.md`.

## Phase 1 — history-preserving monorepo bootstrap

- [x] Initialize the root repository and integration documentation.
- [x] Import Synthesus from `fix/launch-async-guard` into `apps/synthesus/`.
- [x] Import Knowledge Cloud from `agent/repair-knowledge-cloud-bundle` into
  `knowledge/knowledge-cloud/`, retaining Git LFS pointers.
- [x] Import AIVM Planetary OS into `platform/planetary-os/`.
- [x] Import Synthesus OS/CHAL seed into `platform/synthesus-os/`.
- [x] Import Synthetic Intelligence Network into
  `research/synthetic-intelligence-network/`.
- [x] Record source remote and commit metadata.
- [x] Add root diagnostics and run them from the integrated checkout.
- [ ] Verify root diagnostics from a fresh clone after the GitHub repository
  exists.

Acceptance gate: one clone contains every canonical source boundary and
`make doctor` identifies every required or optional dependency accurately.

## Phase 2 — establish canonical ownership

- [x] Diff `apps/synthesus/runtime/` against `platform/synthesus-os/`.
- [x] Declare `apps/synthesus/runtime/` as the provisional canonical product
  runtime and `platform/synthesus-os/` as a read-only extraction seed.
- [x] Stop tracking imported Planetary kernel build products and validate the
  kernel from an isolated temporary build directory.
- [ ] Declare one canonical implementation for CHAL, Cognitive Hypervisor,
  AIVM, knowledge integration, API, frontend, and desktop.
- [ ] Quarantine duplicate or historical trees under `archive/` with a
  retirement note; do not silently delete unique work.
- [ ] Move architecture-only vSource and Unisync material into versioned
  cross-component specifications.
- [ ] Fix the mounted Knowledge Cloud evolution regression exposed by
  `tests/test_knowledge_evolution.py::test_knowledge_evolution_propagation`.
- [ ] Replace internal imports that depend on former repository roots.
- [ ] Add compatibility shims only where a dated removal issue exists.

Acceptance gate: each subsystem has one writable source of truth and duplicate
trees fail a repository audit.

## Phase 3 — unified development and release tooling

- [ ] Create one bootstrap command for Python, Node/Bun, C++, and optional GPU
  dependencies.
- [ ] Pin supported Python, Node/Bun, compiler, Ollama, and CUDA versions.
- [x] Add an initial root CI smoke workflow.
- [ ] Expand CI into path-filtered desktop, runtime, kernel, and knowledge
  planes.
- [ ] Add formatting, linting, type checking, unit, integration, and security
  commands.
- [ ] Add a reproducible development container or Nix/devcontainer equivalent.
- [ ] Define semantic versions for the product and independently versioned
  protocols/artifacts.

Acceptance gate: a fresh supported Linux machine can bootstrap and execute the
changed-component test matrix from documented commands.

## Phase 4 — service boundaries and contracts

- [ ] Extract `synthesusd`, the local cognitive controller daemon.
- [ ] Bind the desktop to authenticated loopback IPC; never expose the
  terminal server directly to the LAN.
- [ ] Freeze the CHAL request, response, capability, telemetry, and error
  schemas.
- [ ] Implement vSource resource inventory, leases, placement, and lifecycle.
- [ ] Define Unisync backends for local memory/PCIe, trusted LAN, and Internet
  task/object transport.
- [ ] Define AIVM workload and artifact manifests.
- [ ] Mount the Knowledge Cloud through a versioned manifest-verified client.

Acceptance gate: the desktop can launch one real local workload through
desktop → controller → CHAL → vSource → AIVM and retrieve a verified Knowledge
Cloud artifact without private in-process shortcuts.

## Phase 5 — secure personal mesh MVP

- [ ] Build a cross-platform node agent with explicit opt-in resource limits.
- [ ] Implement device enrollment using per-node keys and revocation.
- [ ] Use mutually authenticated encrypted transport for every node.
- [ ] Add NAT traversal with a relay fallback; never require unsafe router
  configuration.
- [ ] Schedule only among machines owned by the same account.
- [ ] Implement heartbeat, disappearance, retry, checkpoint, and rescheduling.
- [ ] Ship CPU/RAM/GPU/disk/bandwidth and thermal/power controls.
- [ ] Provide a visible pause/stop control and an audit log.

Acceptance gate: a two-to-five-machine household mesh completes real embedding,
indexing, and inference jobs while tolerating a worker disappearing.

## Phase 6 — isolation, verification, and accounting

- [ ] Replace raw marshal, pickle, eval, and arbitrary-shell execution at every
  network boundary.
- [ ] Run untrusted work in a hardened container, microVM, or WASM sandbox.
- [ ] Enforce signed workload manifests and allowlisted runtime images.
- [ ] Add node health, capability, benchmark, and reputation records.
- [ ] Add deterministic result hashes where possible.
- [ ] Add redundant execution or challenge jobs for untrusted results.
- [ ] Meter useful work, transfer, storage, failures, and verification cost.
- [ ] Add abuse controls, rate limits, quotas, and incident response.

Acceptance gate: an adversarial host cannot read protected workload data,
escape its workload boundary, falsify metering without detection, or submit
unchecked results.

## Phase 7 — paid private beta

- [ ] Package a signed installer and updater for the supported Linux target.
- [ ] Add account, subscription entitlement, and local-license caching.
- [ ] Keep base local operation available during control-plane interruption.
- [ ] Add crash reporting and telemetry as explicit, privacy-respecting opt-in.
- [ ] Publish pricing for Personal and Pro private meshes.
- [ ] Recruit 10–25 design partners and record activation/retention metrics.
- [ ] Establish support, privacy, terms, acceptable use, and security contacts.

Acceptance gate: at least ten users install without developer intervention,
five pay, and retained users complete useful weekly workloads.

## Phase 8 — trusted community compute beta

- [ ] Add contributor enrollment, consent, schedules, and resource budgets.
- [ ] Start with subscription credits, not a speculative token.
- [ ] Restrict initial workload classes to interruptible high-throughput jobs.
- [ ] Add carbon/price-aware placement and opt-out peak-hour scheduling.
- [ ] Publish contributor electricity and wear estimates.
- [ ] Measure cost per successful job against at least two cloud alternatives.
- [ ] Add regional/data-residency placement and deletion guarantees.

Acceptance gate: 25–100 real nodes deliver verified workloads with positive
unit economics after contributor credit, verification, storage, bandwidth,
payments, and support.

## Phase 9 — public launch and scale

- [ ] Complete independent application, infrastructure, and protocol security
  reviews.
- [ ] Add redundant control-plane, relay, artifact, billing, and observability
  services.
- [ ] Publish status, incident, vulnerability-disclosure, and SLA policies.
- [ ] Build supply and demand acquisition separately; avoid idle subsidized
  capacity without customer work.
- [ ] Add qualified low-latency cells for multi-GPU workloads.
- [ ] Retire or archive former standalone repositories with migration notices.
- [ ] Publish measured cost, energy, reliability, and environmental claims.

Acceptance gate: the service survives regional failure, pays contributors from
customer revenue, maintains target gross margin, and meets its published SLOs.

## Product metrics that decide profitability

- Activation: installation-to-first-useful-job conversion.
- Retention: weekly active paid private meshes.
- Supply: verified available GPU-hours by hardware and region.
- Demand: paid useful GPU-hours and queue depth.
- Reliability: successful jobs after retries and verification.
- Unit economics: revenue minus contributor credits, power subsidies, artifact
  storage, bandwidth, verification, payments, and support.
- Safety: confirmed isolation, privacy, abuse, and metering incidents.
