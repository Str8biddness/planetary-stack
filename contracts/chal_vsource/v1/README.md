# CHAL/vSource contract v1

This package freezes the first cross-component control-plane contract for the
Planetary private-cell MVP. The strict Python models are the executable
reference validator. The committed Draft 2020-12 schemas provide the same
structural and expressible conditional rules for node agents and other
non-Python consumers. Every schema also carries mandatory
`x-planetary-semantic-invariants` for cryptographic, cross-document, clock,
replay, and monotonic-state checks that JSON Schema cannot express.
`schemas/schema-manifest.json` pins the generator version, URI, and SHA-256
digest of every export.

Version 1 covers:

- CHAL requests, responses, structured errors, capabilities, and telemetry;
- vSource resource inventory, placement decisions, fenced leases, and
  workload lifecycle events;
- a same-account private cell only. Public providers and multi-tenant
  scheduling are intentionally outside this version.

## Security boundary

Control messages are signed descriptors containing content-addressed artifact
references. They never contain executable bytecode, shell commands, pickle,
marshal payloads, raw prompts, raw outputs, reusable credentials, or trust
bypass instructions. A signature field defines the wire contract but does not
itself verify cryptography; the future node agent and scheduler must verify
Ed25519, key ownership, revocation epoch, audience, TTL, account, resource
scope, request/inventory digests, and artifact hashes before acting.

For every v1 document that carries a `signature`, the signature covers the RFC
8785 JSON Canonicalization Scheme representation of the complete document with
that top-level field omitted. Verification must reject unknown key IDs,
non-canonical encodings, duplicate JSON keys, revoked keys/capabilities, and
signatures outside their validity window before any state change.

Every modeled wire property is required, including explicit `null`, `false`,
zero, and empty-array defaults. A signer first performs strict schema and
semantic validation, serializes by wire alias with all properties present,
removes only the top-level `signature`, and then applies RFC 8785. This prevents
different languages from signing different default-materialized documents.

All signed integers stay within the interoperable I-JSON safe-integer domain.
Mathematically integral JSON numbers such as `1.0` follow Draft 2020-12
integer semantics and normalize to the same RFC 8785 number as `1`; strings and
booleans are never integer inputs.
Set-like signed values are lexicographically sorted arrays, never unordered
sets; semantically ordered inputs, outputs, and placement candidates preserve
their declared order. Timestamps have one lexical form: UTC, second precision,
`YYYY-MM-DDTHH:MM:SSZ`. Ed25519 values are canonical unpadded base64url
encodings of exactly 64 bytes. The executable reference helper in
`canonical.py` produces RFC 8785 signing bytes and request digests.

Requests and capabilities use bounded `ttl_seconds` values capped at one hour,
inventory at five minutes, and leases at fifteen minutes. Effective expiry is
the document timestamp plus that TTL. Production policy may issue shorter
windows; widening a schema cap requires a new contract review.

The request signature binds its workload manifest, inputs, parameters,
constraints, account, capability, and device. Placement, lease, response,
lifecycle, error, and telemetry documents carry the SHA-256 digest of the
RFC-8785 request signing bytes. A controller must persist
`(account_id, idempotency_key) -> request_sha256` and reject reuse with a
different digest.

Capability `resource_prefixes` are normalized lowercase CHAL URI prefixes
ending in `/`. Matching is a literal, segment-bounded string prefix; regular
expressions, globs, URL decoding, and substring matching are prohibited.

The `personal_cell` trust-zone value describes machines enrolled to the same
account. It does not imply a shared kernel, global memory-consistency domain,
or implicit trust between processes. Every allocation uses a short-lived lease
with a monotonically fenced token. For each `lease_id`, renewal sequence and
fencing token strictly increase. Results and lifecycle events carry the exact
active lease digest and fencing token; a node accepts them only when that tuple
matches durable scheduler state. Unisync is a future transport behind these
contracts, not an authorization layer.

Inventory publishes currently allocatable host resources, not unverifiable
capacity claims. GPU inventory is an object keyed by the unique GPU ID.
Placement candidates bind an account plus the ID and digest of a signed
inventory document; placement and lease select one signed transport. A lease
binds the selected request and inventory digests plus canonical GPU IDs.

Allocation authorization is componentwise and fail-closed. The request must be
within the capability resource vector; the lease must be within both the
request and signed allocatable inventory. GPU count and memory are either both
zero or both positive, `gpu_ids` count equals the leased GPU count, every ID
exists in the bound inventory, and their aggregate allocatable memory covers
the lease. The runtime must also require account equality, authenticated
capability subject, `reserve` and `execute` actions, selected-node audience,
minimum attestation, workload membership, literal device-prefix scope, and
selected transport in both capability and inventory.
`validate_private_cell_allocation()` is the executable reference for these
joins.

Telemetry is metadata-only. It identifies work using IDs and SHA-256 digests;
`contains_user_content` is fixed to `false`, and every label name and value is
an enum. Structured errors expose an error code and optional diagnostic ID,
not free-form text.

## Validation contract

Admission requires all of the following; passing only a generic JSON Schema
validator is never sufficient:

1. reject duplicate JSON keys and non-I-JSON values;
2. validate the committed Draft 2020-12 schema, including its `if`/`then`
   lifecycle and evidence rules;
3. enforce every `x-planetary-semantic-invariants` entry;
4. canonicalize using RFC 8785 and verify the Ed25519 signature;
5. verify enrollment, account, audience, revocation, TTL, digest joins,
   idempotency, fencing, and durable sequence state.

The CLI performs steps 1–2, the locally expressible subset of step 3 through
the Python semantic reference, and an RFC 8785 canonicalization safety check.
Cryptographic keys, clock policy, enrollment state, cross-document joins, and
durable scheduler state are deliberately runtime gates.

## Lifecycle

```text
admitted -> staged -> running -> completed/failed/cancelled/lost
                         v
                    checkpointed -> running
                         |
                         v
                       evicted -> staged
```

Completed, failed, cancelled, and lost are terminal. Completed events require content-addressed
outputs; checkpointed events require a checkpoint; failed and lost events
require a structured error.

## Versioning

The discriminator is the document's `schema` field, for example
`planetary.chal.request.v1`. The v1 wire shape is frozen: adding or removing a
field, altering its meaning, widening authority, or changing validation rules
requires a new schema namespace. Documentation and test corrections may remain
within v1 only when they do not change accepted wire documents or signing
bytes.

Regenerate and verify the checked-in schemas with the installed Synthesus
environment:

```bash
python -m pip install -e '.[test]'
python -m contracts.chal_vsource.v1.schema_tool --write
python -m contracts.chal_vsource.v1.schema_tool --check
python -m pytest -q tests/test_chal_vsource_contracts.py
```

Validate an individual JSON document with:

```bash
python -m contracts.chal_vsource.v1.schema_tool --validate document.json
```

This package freezes message shapes only. It does not claim that the vSource
registry, allocator, signature verifier, node agent, transport, or AIVM
sandbox has been implemented.
