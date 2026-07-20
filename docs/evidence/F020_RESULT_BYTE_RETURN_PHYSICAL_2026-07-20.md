# F-020 result-byte return over physical mTLS — 2026-07-20

## What was proven

A **genuine model result**, produced by real rootless-Podman execution on one
mesh node, was **staged** into the mesh outbox by the `stage-result` command
and **returned** to a second mesh node over the lease-bound Unisync mTLS
transport, where its exact bytes were independently verified. This closes — at
the node-to-node transport level — the gap the prior physical runs documented:
*"Returning the result bytes over lease-bound mTLS … `LocalJobPipeline.result`
returns None without a loader."*

- Tested implementation commit: `31a189e73a5cb7b0d94b99c12adabf41f73ae2d7`
  (deployed identically to both nodes via git bundle; both at that HEAD).
- Node-side `implementation_sha256`: `0a14c420365afbf2f358f1927125c7d4fe82e85030226ef1f2191ffe2636c9dc`.
- Physical machines / pinned SSH host keys:
  - source `AIVM` (192.168.68.52): `SHA256:K93xXWV+UB7FCvv8yf1TpTaERu8h+ey2WOK/0x1PYAE`
  - destination `dakin-MS-7C95` (192.168.68.54): `SHA256:q0JCxuHCtW6gnRbnnAvcH0sqFz5RE8tfKQHoXSMGw4w`

## The genuine result

Produced on `dakin-MS-7C95` by running the real `localhost/aivm-text-classify`
ONNX profile in **rootless Podman** (`--network none --read-only`) over the
repo-pinned model (`575d5666…`, 2354 B) and document (`07a1c31c…`, 41 B):

```
{"document_sha256":"07a1c31c…","feature_dims":256,"label":"positive",
 "model_sha256":"575d5666…","schema":"planetary.aivm.result.text-classification.v1",
 "scores":{"negative":0.414381,"positive":0.585619}}
```

- Result object (payload + newline): sha256
  `5df96635e0a6a63e1026d42ced2e4dbbaa72a370035f0d7aa0df004476e557b1`
  (314 bytes) — **byte-identical to every prior physical execution path**
  (single-node, mesh-delivered, remote-backend, three-node cell).

## Staging + transfer

1. `stage-result` (`planetary.private_mesh.stage_result.v1`) re-hashed the
   result and placed it into the source node's Unisync outbox as a
   content-addressed bounded object (`byte_length` 314, digest re-verified).
2. The mesh mTLS gate ran in `prepare_mode="existing"`: fresh TLS enrollment on
   both nodes, mesh CA issuance/install, signed inventory, a scheduler-signed
   active `lan_mtls` lease bound to the destination, and a lease-bound
   `send`/`serve` that moved the **pre-staged result** over the socket. No
   result bytes crossed the administrative SSH channel.

- Bootstrap carrier: `ssh_stdio`; contract transport: `lan_mtls`; run token
  `c107777f51855f9a`.
- Negotiated `TLSv1.3`, mutual client certificate required; source cert
  `e711d8dc…`; serve audit event `client_identity_bound`.
- Scheduler-signed active lease `lease:2d4344d1383ceb70ad9a3d8e299760b8`
  (fencing token 1); durably released after the transfer.
- Verified receipt sha256 `78e0c486e638f214f1f61974c662cab275b650fab659d90fe23ec6f93c7031c0`.
- Coordinator evidence transcript (mode 0600) sha256
  `f38e52ed1a8cde46ffc9d64e29280729664d19fe88d1a318a5e7afb0b90e8aab`;
  checkpoint-stable vSource SQLite sha256
  `2834c5c1e30484beff9a7027484757e0fe4e8090168e0b8221f324bec845578f`.

## Independent destination verification

On `dakin-MS-7C95`, the received inbox object
`inbox/objects/5d/5df96635…` re-hashes to
`5df96635e0a6a63e1026d42ced2e4dbbaa72a370035f0d7aa0df004476e557b1` at 314
bytes, with content byte-identical to the genuine result above.

## Honest scope — no FINISH_CHECKLIST box is checked

This proves the result-byte return **between two real mesh nodes over physical
mTLS**, exercising the session's `stage-result` and `prepare_mode="existing"`
code on hardware. It does **not** yet prove:

- **Desktop-as-destination on hardware.** The receiving party here is a peer
  mesh node, not the coordinating Web Desktop itself. `build_result_loader`
  (services/result_transfer.py) performs the desktop-as-destination path
  in-process (LocalMeshCarrier); the physical version needs a hybrid carrier
  (local desktop `serve` + SSH worker `send`), which is not built.
- **`synthesusd` wiring.** The desktop server does not yet construct/pass the
  loader, so a live browser does not yet see the returned bytes.
- **Production enrollment shape.** This run performs fresh per-transfer TLS
  enrollment + CA + lease, not persistent enrollment reused across fetches.
- **Note on inputs.** The receiving node's firewall required the destination to
  be `dakin-MS-7C95`; the genuine result bytes were produced on that node and
  copied to the source node `AIVM` for staging (the result is deterministic and
  its digest was verified at every hop). The Podman execution that produced the
  result is the real one; the source node here is a stand-in for "the node that
  holds the result," which on hardware is the executing worker.
