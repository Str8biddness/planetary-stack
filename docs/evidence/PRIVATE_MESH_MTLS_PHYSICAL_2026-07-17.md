# Private-mesh Unisync mTLS physical evidence — 2026-07-17

## Accepted run

- Tested implementation commit:
  `be1e6495e147e2e40a26126ba20a3260d3799a50`
- Complete Git bundle SHA-256:
  `ab199a9b99cbd1f42fe84160a00ed854437477772296f78ad5aa1e0e88c280ad`
- Worker implementation SHA-256:
  `6d832dba6a36b27a27afb48e476aaaab8e2fbd8d2b047c738025b68f294210f8`
- Evidence transcript SHA-256:
  `f078c039a0291238ff6c457c0e64268db521c109e3155e7c4399a8806cdae37c`
- Checkpoint-stable SQLite SHA-256:
  `3cdc2c7819672afe49e86ea658a6297c88821a8faa42f4729e244e1893d50f00`
- Enrollment registry SHA-256:
  `f59253ce6ae17a55ce056c2f5a7a4a4973259dd64229225b85aea2c42e91a2b6`
- Completed at: `2026-07-17T21:02:10Z`
- Physical hostnames: `AIVM`, `dakin-MS-7C95`
- Pinned SSH host-key fingerprints:
  - `SHA256:K93xXWV+UB7FCvv8yf1TpTaERu8h+ey2WOK/0x1PYAE`
  - `SHA256:q0JCxuHCtW6gnRbnnAvcH0sqFz5RE8tfKQHoXSMGw4w`

Both machines cloned the complete bundle into fresh clean checkouts and
reported the exact tested commit. The SSH carrier used exact Ed25519 host-key
pins and fixed node CLI subcommands for enrollment and coordination. It did not
carry the opaque workload bytes.

## Enrollment and authorization

Each node generated separate TLS and CHAL/vSource signing keys locally. State
directories were mode `0700`; TLS private keys, public certificate state,
trust anchors, and persistent lease-use records were mode `0600`. No private
key appeared in the retained transcript.

The short-lived certificates bind the shared account and exact node identity
in their signed X.509 subjects:

- `O=account:private-mesh:home, CN=node:private-mesh:aivm`
- `O=account:private-mesh:home, CN=node:private-mesh:ms7c95`

Their certificate SHA-256 fingerprints were respectively
`4883e36da115d2d7ff722a9a8626a72bc25776c7066667bd6ef1106ae4b7d430`
and
`ecd6f0c485c7a64a5aa491cb6326e0fb0c06d83714d55b187264cdcd517a73ab`.
The persistent enrollment directory was mode `0700`; its registry and stable
cross-process lock were mode `0600`.

Both nodes admitted the same controller-signed request and scheduler-signed
active `lan_mtls` lease. Validation bound the exact account, request digest,
lease ID and digest, fencing token `1`, source, destination, transport, object
reference, byte length, and expiry. After the verified receipt, the central
SQLite record was integrity-clean with state and terminal state both
`released`. Both node-local lease-use records were `completed`.

A second invocation of the source send path with the same signed lease and
fencing token failed before network use with:

```text
AuthorizationError: lease revision was already admitted or superseded
```

The regression suite also injects a coordinator failure during the first
post-allocation validation phase and verifies that the central lease is
durably `revoked`, rather than left active.

## Data-plane proof

The source generated a 65,536-byte opaque object inside its local CAS. The
object was not provisioned over SSH. Source and destination CAS files both
hashed to:

`ad67f47582d79f8324bb7aa47f9f3ec6ca7711b71b4d484edc5ba44cb95349ef`

The destination accepted it over a real private-address TCP connection with:

- TLS version: `TLSv1.3`
- Cipher: `TLS_AES_256_GCM_SHA384`
- Contract transport: `lan_mtls`
- Destination audit event: `client_identity_bound`
- Verified receipt SHA-256:
  `212b2b9ecd5d8817072d93ae03ac7d734a61ab293a5f4cd56e21f857fce15489`

The source's certificate fingerprint in the send result and the destination's
certificate fingerprint in the serve result exactly matched the persistent
enrollment records.

## Validation

- Focused mTLS gate suite: 14 passed.
- Private-mesh/vSource/Unisync suite, `PYTHONHASHSEED=1`: 141 passed.
- Private-mesh/vSource/Unisync suite, `PYTHONHASHSEED=4`: 141 passed.
- Frozen contract suite: 42 passed under each of two hash seeds.
- Frozen schema manifest: 9 schemas validated.
- Python compilation and `git diff --check`: passed.
- `make doctor`: `required_missing=0`; two optional tools were unavailable.
- `make status`: all component paths present at tested head `be1e649`.

The focused suite includes real TCP TLS 1.3 transfer,
signed-request-to-object digest/size binding, signed lease/fence binding,
account-bound certificate substitution rejection,
cross-process enrollment-registry serialization, persistent replay rejection,
cross-process lease-admission serialization, failure-path lease revocation,
private-address listener policy, strict I-JSON, credential
permissions/symlink rejection, and separate contract/TLS keys.

The raw transcript, SQLite database, registry, and complete Git bundle remain
retained in owner-only storage on `AIVM`; they are hash-referenced here rather
than committed because the raw transcript contains local topology and public
certificate metadata.

## Explicit non-claims

This gate does not prove:

- production CA or HSM custody;
- certificate renewal, rotation, CRL/OCSP, or online revocation distribution;
- automatic recovery, retry, checkpointing, or rescheduling;
- NAT traversal or relay transport;
- hardware-backed attestation;
- local memory/PCIe or public-Internet Unisync backends;
- AIVM isolation or arbitrary model execution;
- multi-tenant public-fabric scheduling or a completed planetary SSI.
