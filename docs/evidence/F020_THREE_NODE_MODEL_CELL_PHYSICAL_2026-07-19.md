# Three-node cell — useful model job, physical — 2026-07-19

## What was proven

A **useful ONNX model job** was placed and executed inside a **real
three-node-enrolled cell**, over the pinned SSH carrier, and its result was
independently verified coordinator-side.

- Cell members (three distinct physical machines, distinct node keys, all
  enrolled in one account `account:private-mesh:home`):
  `AIVM`, `dakin-MS-7C95` (execution), `dako-MS-7C89`.
- The scheduler issued one fenced lease bound to the execution node; a
  `ssh_job.v2` executor job ran the real text-classification profile in
  rootless Podman (`localhost/aivm-text-classify@sha256:4933984e…`) from
  artifacts resident in the execution node's Unisync mesh inbox
  (model `575d5666…`, document `07a1c31c…`, delivered over mTLS earlier).
- The coordinator validated the signed response + execution evidence
  against the exact lease (`_ingest_result` executor-evidence mode):
  - Content-addressed model result
    `5df96635e0a6a63e1026d42ced2e4dbbaa72a370035f0d7aa0df004476e557b1`
    — **byte-identical to every prior physical execution path** (single
    node, mesh-delivered, remote-backend), confirming determinism holds
    across the three-node cell too.
  - Execution evidence `117c92b1…`.
- Coordinator evidence transcript: `cell-model-evidence.json`
  (sha256 `67ada8a8…`).

## Honest scope — no FINISH_CHECKLIST box is checked

F-020's cell acceptance is "a fresh three-node cell completes a useful model
job **from the Web Desktop** and independently verifies its result without
in-process shortcuts." This run demonstrates:
- ✅ a fresh three-node cell,
- ✅ a useful (non-hash) model job,
- ✅ independent signed-result verification,
- ✅ no in-process shortcuts (real Podman, real SSH carrier, real signed
  CHAL/vSource documents).

It does NOT yet demonstrate the literal **Web-Desktop origin**: the desktop
job API dispatches through `synthesusd`, whose productionized remote
construction (mesh enrollment + persistent signed control plane + mTLS
result return) is intentionally fail-closed pending secure implementation.
The desktop-facing `RemoteExecutionBackend` is proven separately
(`F020_DESKTOP_REMOTE_JOB_PHYSICAL_2026-07-18.md`), but the end-to-end
browser-click → cell-execution → desktop-presentation path is not wired.

Also NOT proven: worker-outage survival / rescheduling for the model
workload (single-node model execution has no redundancy yet — F-080
rescheduling remains open), and physically triggered controller restart.
