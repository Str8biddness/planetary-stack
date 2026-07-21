# F-020 end-to-end job → result on physical hardware — 2026-07-21

## What was proven

A single process on the desktop **submitted a real signed workload**, a physical
worker **executed it in rootless Podman**, and the desktop **pulled the genuine
result bytes back** over the lease-bound Unisync mTLS transport — with no
inbound firewall port opened on the desktop. This is the exact server-side path
the browser endpoints (`POST /api/jobs`, `GET /api/jobs/{id}/results/{sha}`)
call.

Reproduced by `tools/demo_browser_result.py` (committed alongside this doc).

- Implementation commit deployed to **both** machines via git bundle:
  `19b50a6fd58ee0a5f3ba93db1a520b3a89ccf0e1`.
- Desktop: `dakin-chronos` (192.168.68.55), repo `/home/dakin/planetary-stack-finish`.
- Worker: `dakin-MS-7C95` (192.168.68.54), pinned host key
  `SHA256:q0JCxuHCtW6gnRbnnAvcH0sqFz5RE8tfKQHoXSMGw4w`,
  checkout `/home/dakin/ps-demo-19b50a6fd58ee0a5f3ba93db1a520b3a89ccf0e1`.

## Observed run

```
bundle sha256: cc8667875c1ccee04b29fc5a44805dbcd0a727fe2f357a9bcf5828359a337e71 len: 1914
pipeline built + worker enrolled
job_id: job:cc8667875c1ccee0-d5a3e64b state: completed
outputs: [('5df96635e0a6a63e1026d42ced2e4dbbaa72a370035f0d7aa0df004476e557b1', 'application/json'),
          ('cdb217a732e24c8f005e527693371c9676c78580e82f74a4ba05787be90ece86',
           'application/vnd.planetary.aivm-evidence+json')]
PULLED RESULT bytes: 314 media: application/json
content: {"document_sha256":"07a1c31c…","feature_dims":256,"label":"positive",
          "model_sha256":"575d5666…",
          "schema":"planetary.aivm.result.text-classification.v1",
          "scores":{"negative":0.414381,"positive":0.585619}}
```

- Result object `5df96635e0a6a63e1026d42ced2e4dbbaa72a370035f0d7aa0df004476e557b1`
  (314 bytes) — **byte-identical to every prior physical execution path**
  (single-node, mesh-delivered, remote-backend, three-node cell, pull gate).
- Runtime image pinned by digest
  `sha256:4933984efd51622d198bab953d5011cdc6b94155a2467e85acbd8e1e581a3f5b`;
  entrypoint `aivm.model.text-classify.v1`; `--network none --read-only`.
- Manifest authenticity is established by `RequestBoundManifestVerifier`: the
  controller signature over the CHAL request pins the bundle digest
  (`cc866787…`). No separate owner manifest-signing key was deployed.
- Result return used the desktop-initiated pull (`carrier="hybrid"`,
  `pull=True`, `prepare_mode="existing"`): the **desktop dialed outbound** and
  acted as TLS server + receiver; the worker listened and acted as TLS client +
  sender. Roles are identical to the proven push; only the TCP initiator differs.

## What this does NOT prove

- **The browser UI itself was not driven in this run.** This exercises
  `build_remote_pipeline(...).submit()` and `.result()` — the functions the HTTP
  handlers call — not the HTTP layer or the rendered Mesh Jobs window.
- Input artifacts (model `575d5666…`, document `07a1c31c…`) were staged directly
  into the worker's content-addressed inbox for this run. **Input delivery over
  mTLS is proven separately** in `F020_MESH_WORKLOAD_PHYSICAL_2026-07-18.md`; it
  is not re-proven here.
- The harness carries machine-specific constants (host keys, absolute paths,
  interpreter paths). It is a reproduction script for these two machines, not a
  product installer.
- Unchanged from prior runs: certificate rotation/renewal, revocation
  distribution, NAT traversal/relay, hardware attestation, and production CA
  operations remain **unproven**.

## Reproduce

```
python tools/demo_browser_result.py
```

Requires the constants at the top of that file to match the local machines, the
worker checkout at the pinned HEAD, and the two input objects present in the
worker's `ps-demo-exec/inbox`.
