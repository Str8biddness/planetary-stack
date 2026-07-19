# F-020 desktop remote-backend physical evidence — 2026-07-18

## What was proven

`RemoteExecutionBackend` — the desktop job pipeline's remote execution
backend — was driven against the enrolled worker `dakin-MS-7C95` over the
pinned OpenSSH administrative carrier. The backend built an `ssh_job.v2`
executor job whose spec it derived from the signed workload manifest,
dispatched it, and the worker ran the **real ONNX model profile** in
rootless Podman against artifacts already resident in its Unisync mesh
inbox (delivered over mTLS in the 2026-07-18 mesh-workload gate). The
backend parsed the worker's signed response envelope back into the
node-agent result types the pipeline consumes.

This closes the remaining wiring gap: the same `LocalJobPipeline` behind
the authenticated `synthesusd` job API can now target a physical worker,
not only the in-process node, and the model runs on the worker.

## Result

- Backend result: `status=executed`, `accepted=true`,
  `response_status=succeeded`.
- Signed response outputs:
  - Content-addressed model result
    `5df96635e0a6a63e1026d42ced2e4dbbaa72a370035f0d7aa0df004476e557b1`
    (`application/json`) — **byte-identical to the single-node physical
    gate and the mesh-delivered workload gate**, confirming determinism
    across every execution path.
  - Execution evidence
    `ba7e385a5dc5aa9351bf261609e04be3bae456ff19465314a38bc10bcaf204b7`.
- Immutable profile image
  `localhost/aivm-text-classify@sha256:4933984efd51622d198bab953d5011cdc6b94155a2467e85acbd8e1e581a3f5b`.
- Coordinator evidence: `backend-remote-evidence.json`.

## Distinction from run_remote_workload (PR #14)

PR #14 proved the coordinator function `run_remote_workload`. This run
proves the `RemoteExecutionBackend` class that the desktop pipeline
actually uses — it builds the v2 job from a manifest, dispatches, and maps
the response without fabricating any state. Unit tests
(`tests/private_mesh/test_remote_backend.py`) pin its spec derivation,
fail-closed image/manifest checks, and rejection/unavailable mapping.

## Non-claims

This proves single-worker desktop-backed remote execution. It does not
prove desktop UI end-to-end against physical hardware, result return to
the desktop over mTLS as a productized flow, a three-node cell, or
worker-outage recovery. Those F-020 items remain open.
