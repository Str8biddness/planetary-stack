# Private-mesh node agent: deferred shared integration requests

This wave intentionally edits only `services/private_mesh/**` and
`tests/private_mesh/**`. The following shared changes are requested for the
coordinator/integrator and are **not** applied here:

1. **Makefile** — extend `test-private-mesh` to include `tests/private_mesh`
   under both `PYTHONHASHSEED=1` and `PYTHONHASHSEED=4`:

   ```make
   test-private-mesh:
   	PYTHONHASHSEED=1 $(PYTHON) -m pytest -q tests/vsource tests/unisync tests/private_mesh
   	PYTHONHASHSEED=4 $(PYTHON) -m pytest -q tests/vsource tests/unisync tests/private_mesh
   ```

2. **CI** — `.github/workflows/monorepo-smoke.yml` already runs
   `make test-private-mesh`; no workflow edit is needed once the Makefile
   change lands.

3. **Packaging** — `pyproject.toml` already includes `services*` via
   `tool.setuptools.packages.find`, so `services.private_mesh` ships without a
   packaging edit. `cryptography` remains a test/runtime extra exactly as for
   `services.vsource`.

4. **Two-node execution interface for the coordinator.** The later physical
   check drives one `NodeAgent` per enrolled machine over pinned SSH/mTLS.
   Per node, the coordinator must supply:

   - `NodeAgent(account_id=..., node_id=..., inventory=<signed v1 inventory>,
     verifier=Ed25519DocumentVerifier(key_resolver, clock, audience=node_id),
     signer=<node Ed25519 signer>, clock=<real UTC clock>)`;
   - `admit_lease(lease, request, capability,
     authenticated_subject_id=...)` with the exact signed v1 documents issued
     by `LocalVSourceControlPlane.allocate()`;
   - `execute(lease_id=..., lease_sha256=..., fencing_token=...,
     bundle=<opaque bytes>)`, where the bundle bytes must hash to the signed
     `workload_manifest.sha256`/`size_bytes` of the request;
   - feeding each returned signed `LifecycleEvent`/`ChalResponse` back into
     `LocalVSourceControlPlane.record_lifecycle_event()` /
     `record_response()` for durable, fenced verification.

   Suggested later gate command (from the coordinator host, once the SSH/mTLS
   driver exists):
   `make test-private-mesh PYTHON=.venv/bin/python` for in-process evidence,
   plus a dedicated two-machine driver invoking the interface above; the
   in-process suite must never be reported as physical-cluster evidence.

5. **Durable node-side replay state.** This wave keeps admitted-lease state
   in process memory. Before a node agent survives restarts in a real mesh,
   its lease/fence/sequence bookkeeping needs the same durable CAS treatment
   as `services/vsource/control_plane.py` (shared decision; not taken here).
