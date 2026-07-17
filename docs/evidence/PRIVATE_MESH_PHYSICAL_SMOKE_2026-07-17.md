# Private-mesh physical smoke evidence — 2026-07-17

## Accepted run

- Tested commit: `2d01c5e931e24bf8bde0d8fe868d08aeebe1e472`
- Complete Git bundle SHA-256:
  `6c8b43eba08adc38806931f1577d363469da47558e29998440f36b0fff924cd0`
- Worker implementation SHA-256:
  `f3f9dfc60dc4e08b5dd9401916d772aa1b86400dc6c43195b787daac8e5dec30`
- Transcript SHA-256:
  `0594162c2edd4fba226cacd0131ad7df871f73c569a87c6cb833942fae6036e2`
- Checkpoint-stable SQLite SHA-256:
  `4fb28e1ecf022f100b44045e7486cd015a2cef11799b9d8d6b2c44202d7ac6b5`
- Physical hostnames: `AIVM`, `dakin-MS-7C95`
- Node contract-key fingerprints:
  - `c7d25fa6753dfdc879b7e662cfa3d4b420cbb06e6349a3f5f2c3b9618b3dff54`
  - `3e8c3aff1369d4d50f62d8590dd3ee92e3250664f8249503828755e0e94d5fc3`

Both machines cloned the complete bundle into fresh clean checkouts and
reported the exact tested commit. Their node state directories were owned by
the SSH user at mode `0700`; their Ed25519 private-key and identity files were
mode `0600`.

## Admitted state

The persistent SQLite record contains:

- 2 signed inventories;
- 2 scheduler-signed fenced leases;
- 8 signed lifecycle events;
- 2 signed responses;
- 2 leases in `released` state with terminal state `completed`.

The recorded SQLite hash was checked before opening the database, after a
read-only SQL audit, and against the transcript. All three values were
identical. The transcript and SQLite files were mode `0600`.

Each node received a separately audience-bound capability and lease. Each
admitted and hashed the exact 128-byte opaque bundle, returned an RFC
8785-canonical report, and produced the signed sequence
`admitted → staged → running → completed`. The controller ingested the signed
response before the terminal event released the lease. The shell-like bytes in
the bundle did not create their sentinel file on either worker.

## Validation

- Private-mesh/vSource/Unisync suite, `PYTHONHASHSEED=1`: 127 passed.
- Private-mesh/vSource/Unisync suite, `PYTHONHASHSEED=4`: 127 passed.
- Frozen contract suite: 42 passed under each of two hash seeds.
- Frozen schema manifest: 9 schemas validated.
- Focused worker/coordinator suite: 13 passed.
- Python compilation, Ruff, and `git diff --check`: passed.

An earlier candidate transcript was rejected because its raw SQLite hash was
taken before a WAL checkpoint and changed on later read. It is not acceptance
evidence. The accepted run above added and tested an explicit
`wal_checkpoint(TRUNCATE)` snapshot boundary.

## Explicit non-claims

This gate proves two pinned SSH endpoints and two distinct node-local contract
keys completed the bounded signed hash path. It does not prove:

- Unisync mTLS (`contract_transport=local_process`,
  `unisync_mtls_proven=false`);
- hardware-backed attestation;
- persistent issuer enrollment or revocation;
- durable node-side replay state across restart;
- arbitrary model execution or an AIVM sandbox;
- failure recovery, rescheduling, production SSI, or a public compute fabric.
