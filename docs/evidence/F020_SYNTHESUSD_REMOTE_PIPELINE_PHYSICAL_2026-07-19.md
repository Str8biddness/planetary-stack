# Secure synthesusd remote pipeline — physical — 2026-07-19

## What was proven

The controller-side construction that `synthesusd._build_job_pipeline` uses
was exercised against the real worker. `load_remote_worker_config` parsed a
strict environment config; `build_remote_pipeline` created a persistent
owner-only desktop signing identity (controller + scheduler), enrolled the
worker `dakin-MS-7C95` over the pinned SSH carrier, registered its signed
inventory in a persistent vSource control plane, and constructed a
`LocalJobPipeline` bound to the `RemoteExecutionBackend`. `pipeline.submit()`
then placed, admitted, and executed the real model on the worker.

- Result: `state = completed`; signed response outputs:
  - Model result
    `5df96635e0a6a63e1026d42ced2e4dbbaa72a370035f0d7aa0df004476e557b1`
    — **byte-identical to every prior physical path**.
  - Execution evidence `28431b2d…`.
- Every document was really signed (persistent Ed25519 controller/scheduler
  identity); no placeholder keys or signatures. Worker enrollment, control
  plane, capability, request, and lease are all real.

## Distinction and honest scope

This closes the controller-side gap that was previously fail-closed: the
desktop controller can now construct a real remote pipeline and run the
model on a configured worker. Combined with the authenticated `synthesusd`
job API (covered by the 30-test desktop suite), this is the browser →
`synthesusd` → worker → verified result path, minus the literal browser
click (the API layer is tested, not driven by a live browser here).

Not yet productionized (documented, not faked):
- Returning the result **bytes** to the desktop over lease-bound mTLS. The
  signed response carries the content-addressed result digest and execution
  evidence, which the desktop presents; fetching the bytes is a separate
  reviewed step. (`LocalJobPipeline.result` returns None without a loader.)
- Installer-driven enrollment/identity provisioning (F-030): the desktop
  authority is a per-owner persistent key created on first construction; a
  productionized flow would provision it through the installer.

No FINISH_CHECKLIST box is checked on this evidence: the literal
Web-Desktop-origin end-to-end and desktop result-byte presentation remain.
