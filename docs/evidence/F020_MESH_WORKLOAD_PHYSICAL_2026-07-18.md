# F-020 mesh-delivered useful workload physical evidence — 2026-07-18

## Accepted run

- Tested implementation commit:
  `7c92bb33df5859a1252d678ae05afb64f2442471`; identical fresh bundle
  clones verified on both machines.
- Physical machines: source `AIVM` (192.168.68.52), destination/executor
  `dakin-MS-7C95` (192.168.68.54), coordinator on the owner workstation.
- Pinned SSH host-key fingerprints:
  - `AIVM`: `SHA256:K93xXWV+UB7FCvv8yf1TpTaERu8h+ey2WOK/0x1PYAE`
  - `dakin-MS-7C95`: `SHA256:q0JCxuHCtW6gnRbnnAvcH0sqFz5RE8tfKQHoXSMGw4w`

## Unisync mTLS artifact delivery

Two complete mesh mTLS gate runs (fresh TLS enrollment, registry, signed
inventory/request/capability, scheduler-signed active `lan_mtls` lease,
TLS 1.3 mutual authentication, verified receipt, durable lease release)
moved both workload artifacts from the source to the executing node. Both
artifacts were reproduced locally on the source from repository-pinned
content (`prepare_mode` `workload_model` / `workload_document`); no
workload bytes crossed the administrative SSH channel.

- Model object: sha256
  `575d566648d21bcfae72241fb0d74e3d95ae22f3d44c28baab0cd579e38b817d`
  (2,354 bytes) — the deterministic demo ONNX classifier.
- Document object: sha256
  `07a1c31caa4e70ed6c41a318f9559bcb6780bf735fc6e6078a99565db1d12dd1`
  (41 bytes) — the repository-pinned demo document.
- Evidence transcripts (coordinator-side, mode 0600):
  - `evidence-model.json` sha256
    `e05ed7a77af85b2e0892368c82a19a5c6e93ab8dc0ea6ccfab8beffa61987890`
  - `evidence-document.json` sha256
    `fe5d0dacbde43e419a24900ffbd9bdff0ae9aebf0b53ecd6e0f6cc6515372fad`
  - Checkpoint-stable vSource SQLite states sha256
    `551bcee0535c0a3586008e111cbb45ae7400e5d0b42868041ed096d40c6375b0`
    (model run) and
    `c7b9d0125d7072e607bf3f53edbba7b81691f2e88d612aecaa27a576ad98c753`
    (document run).

Because TLS enrollment state is create-once by design, the two gate runs
used separate node state directories; the document object was then moved
between the two destination content-addressed stores on the same machine
with digest re-verification. Both objects reached the destination machine
exclusively over `lan_mtls`.

## Remote useful-workload execution

`run_remote_workload` drove the executing node over the pinned SSH
administrative carrier with an `ssh_job.v2` executor job
(`object_delivery="unisync_mtls"`): fresh worker enrollment, signed
inventory/request/capability and scheduler-signed fenced lease from a real
vSource control plane, node-agent admission, digest-verified staging of
both mesh-inbox objects into the executor CAS, request-bound manifest
verification, durable execution-authority consumption, and real rootless
Podman execution of the pinned immutable profile image
`localhost/aivm-text-classify@sha256:4933984efd51622d198bab953d5011cdc6b94155a2467e85acbd8e1e581a3f5b`
(base `docker.io/library/python@sha256:57cd7c3a…`, built 2026-07-18).

- Signed response outputs (coordinator-verified against the exact lease):
  - Result: `artifact://aivm/result/5df96635e0a6a63e1026d42ced2e4dbbaa72a370035f0d7aa0df004476e557b1`
    — the real ONNX classification (`label: positive`, probabilities
    summing to 1), stored content-addressed and immutable (0400) in the
    node result store; byte-identical to the 2026-07-18 single-node
    physical gate result, proving cross-machine determinism.
  - Execution evidence: sha256
    `b4e066397df3f2fb3f7aeb6e36cc7fa12304a34fb062209552f91513f255c6ae`,
    binding account, node, lease id/digest, fencing token, manifest
    digest, image digests, input set, and wall time.
- Coordinator evidence transcript `remote-workload-evidence.json` sha256
  `27b0accbafa4eae19f7714e0b4f04fc540523542954f5ea12f64d1a9bb0f76c2`.

## Non-claims

This gate proves a two-machine mesh-delivered useful workload with a
single executing node. It does not prove a three-node cell, worker-outage
recovery, desktop-initiated submission against these physical nodes,
result transfer back over mTLS, production CA lifecycle, or hardware
attestation. The remaining F-020 acceptance items stay open.
