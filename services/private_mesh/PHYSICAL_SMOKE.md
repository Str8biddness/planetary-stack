# Private-mesh two-node physical smoke gate

This gate proves that two distinct, pinned SSH endpoints each used a distinct
node-local Ed25519 key to admit a scheduler-signed fenced lease and execute the
bounded `NodeAgent` SHA-256 operation. It then verifies and ingests the signed
response and lifecycle sequence into a persistent SQLite evidence database.

It does **not** prove production SSI, hardware attestation, arbitrary model
execution, restart-safe node state, or Unisync mTLS. SSH is the administrative
carrier for this gate. The frozen contract truthfully records
`transport=local_process` because execution occurs inside the remote worker
process.

## Node preparation

Use a fresh checkout at the same commit on each worker. The Python executable
must have the repository's runtime/test dependencies. Do not reuse an existing
dirty checkout for the gate.

The first `enroll` invocation creates a node-local state directory at mode
`0700` and raw Ed25519 identity files at mode `0600`. The private key is never
returned. Account, node, and authenticated-subject bindings cannot be changed
after enrollment.

## Coordinator command

Pass exactly two `--node` values in this form:

```text
NODE_ID|SSH_ALIAS|HOST_FINGERPRINT|PYTHON|REPO|STATE_DIR
```

Example shape (replace every value with the actual machine-local paths and
verified host fingerprints):

```bash
python -m services.private_mesh.ssh_smoke \
  --known-hosts ~/.ssh/known_hosts \
  --node 'node:owner:a|worker-a|SHA256:...|/absolute/venv/bin/python|/absolute/repo|/absolute/state/a' \
  --node 'node:owner:b|worker-b|SHA256:...|/absolute/venv/bin/python|/absolute/repo|/absolute/state/b' \
  --state-db /absolute/path/private-mesh-physical-smoke.sqlite3 \
  --output /absolute/path/private-mesh-physical-smoke.json
```

The coordinator requires `BatchMode=yes`, strict known-host checking, disabled
forwarding, two distinct host fingerprints, two distinct hostnames, two
distinct node IDs, and two distinct node contract keys. It sends no command,
entrypoint, pickle, marshal, or bytecode field. The deliberately shell-like
128-byte test bundle is only hashed by the fixed worker program.

The evidence and SQLite files are created exclusively at mode `0600`. The JSON
records the public scheduler-side and per-node worker trust views, signed
documents, and digests needed to audit the run. Controller and scheduler keys
are ephemeral. The per-job issuer records arrive through the pinned
administrative SSH channel; this gate does not prove persistent registry
enrollment. Hostname and implementation digests are SSH-observed metadata, not
hardware-backed signed attestation. The evidence explicitly records
`unisync_mtls_proven=false` and the other deferred production claims.
