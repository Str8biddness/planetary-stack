# Node-signed execution evidence, verified across two machines — 2026-07-21

## What was proven

A physical worker executed a real job in rootless Podman, **signed its execution
evidence with its own mesh contract key**, and the desktop **verified that
signature against the public key it learned at enrollment** — on separate
machines, over the pinned carrier, with the result returned by the
firewall-free desktop-initiated mTLS pull.

- Implementation commit deployed to the worker via git bundle:
  `670d995542a4f3d7c71c5b1236384d7c69daaccf`.
- Desktop: `dakin-chronos` (192.168.68.55). Worker: `dakin-MS-7C95`
  (192.168.68.54), pinned host key
  `SHA256:q0JCxuHCtW6gnRbnnAvcH0sqFz5RE8tfKQHoXSMGw4w`, checkout
  `/home/dakin/ps-ev-670d995542a4f3d7c71c5b1236384d7c69daaccf`.

## Observed run

```
bundle sha256: d53af58e20741e013cece8a5b84699687ab7f2b0de52629f02d616dcad66b7fb len: 1914
pipeline built + worker enrolled
job_id: job:d53af58e20741e01-5551c606 state: completed
outputs: [('5df96635e0a6a63e1026d42ced2e4dbbaa72a370035f0d7aa0df004476e557b1', 'application/json'),
          ('4bfe2f4cb7d71e351e3327ba09023e4c322c9b86869313b4a577b388e94e6d20',
           'application/vnd.planetary.aivm-evidence+json')]
PULLED RESULT bytes: 314 media: application/json
EVIDENCE STATUS: verified
evidence key id: key:private-mesh-node:d06e6a0c3f4e02fff57d
```

- `EVIDENCE STATUS: verified` is the desktop's own verification of the worker's
  detached ed25519 signature, checked against the contract public key recorded
  at enrollment (not a key supplied with the response).
- Result object `5df96635…` (314 bytes) is **byte-identical to every prior
  physical execution path**.
- The evidence digest differs from previous runs (`4bfe2f4c…` here vs
  `cdb217a7…` on 2026-07-20) because evidence binds run-specific values — lease
  id, fencing token, wall time. That is expected and is the point: evidence is
  per-run, the result is deterministic.

## What this does NOT prove

- **Self-attestation, not hardware attestation.** The worker signed a statement
  about its own execution with its own key. A compromised worker could sign a
  false statement. Every node still reports `attestation: unverified`.
- The negative cases (wrong key, tampered bytes, rewritten digest) were proven
  by unit test, **not** on hardware in this run.
- Enforcement policy does not exist yet; nothing consumes
  `last_evidence_status` beyond this harness. No UI surfaces it.
- The browser HTTP layer was not driven in this run.

## Reproduce

Deploy the commit above to the worker, then run the demo harness with the
worker repo path pointed at that checkout and print
`pipeline._backend.last_evidence_status`.

No FINISH_CHECKLIST box is checked by this document.
