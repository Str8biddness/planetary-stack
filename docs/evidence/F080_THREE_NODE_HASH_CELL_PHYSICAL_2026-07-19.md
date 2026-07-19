# Three-node physical cell (bounded hash workload) — 2026-07-19

## What was proven

`run_three_node_cell` was driven over the pinned OpenSSH carrier against
**three distinct physical machines**. All three enrolled with distinct
node identities and distinct node-local Ed25519 signing keys; the scheduler
issued one fenced lease on a single execution node; that node ran the
bounded `ssh_job.v1` hash operation; and the coordinator verified the
signed response and admitted/staged/running/completed lifecycle and
released the lease durably — the same verification the two-node smoke
performs.

- Nodes (distinct hostnames + distinct node key fingerprints):
  - `node:private-mesh:aivm` — host `AIVM`, key `57e1f19d…`
  - `node:private-mesh:ms7c95` — host `dakin-MS-7C95`, key `f5c6aed3…`
    (execution node)
  - `node:private-mesh:ms7c89` — host `dako-MS-7C89`, key `75bc6e8e…`
- `passed: true`, `degraded: false`, `node_count: 3`,
  `contract_transport: local_process`.
- Coordinator evidence: `cell-evidence.json` (sha256 `685caaf8…`);
  checkpoint-stable SQLite `0d69cd43…`.

## Honest scope — this does NOT close F-080 or the F-020 cell item

The harness intentionally runs the model-free hash job so it executes on
any node. This run therefore proves three-machine enrollment, single-lease
fenced scheduling, and signed-result verification across a real cell — but
it does NOT prove:
- a **useful model** workload across the cell (that needs the `ssh_job.v2`
  Podman/model path on the execution node plus Unisync mTLS object
  delivery — proven separately on two nodes, not yet combined here),
- a **physically triggered** worker-disappearance / controller-restart at
  defined failure points (covered by the harness unit tests with an
  in-process carrier, not exercised on hardware in this run),
- production SSI, hardware attestation, or persistent registry enrollment.

No FINISH_CHECKLIST box is checked on this evidence. The next step to close
the F-020 cell acceptance is to combine this three-node orchestration with
the already-proven v2 model execution + mTLS delivery, and to trigger a
real node outage mid-run.
