# CHAL/vSource contract v1

This package freezes the first cross-component control-plane contract for the
Planetary private-cell MVP. The Python models are the canonical validator. The
committed JSON Schema documents are deterministic exports for node agents and
other non-Python consumers. `schemas/schema-manifest.json` pins the URI and
SHA-256 digest of every exported schema.

Version 1 covers:

- CHAL requests, responses, structured errors, capabilities, and telemetry;
- vSource resource inventory, placement decisions, fenced leases, and
  workload lifecycle events;
- a same-account private cell only. Public providers and multi-tenant
  scheduling are intentionally outside this version.

## Security boundary

Control messages contain signed descriptors and content-addressed artifact
references. They never contain executable bytecode, shell commands, pickle,
marshal payloads, raw prompts, raw outputs, reusable credentials, or trust
bypass instructions. A signature field defines the wire contract but does not
itself verify cryptography; the future node agent and scheduler must verify the
Ed25519 signature, key ownership, revocation epoch, audience, expiry, account,
resource scope, and artifact hash before acting.

For every v1 document that carries a `signature`, the signature covers the RFC
8785 JSON Canonicalization Scheme representation of the complete document with
that top-level field omitted. Verification must reject unknown key IDs,
non-canonical encodings, duplicate JSON keys, revoked keys/capabilities, and
signatures outside their validity window before any state change.

Request and capability validity windows are capped at one hour, inventory at
five minutes, and leases at fifteen minutes. Production policy may issue
shorter windows; widening these caps requires a new contract review.

The `personal_cell` trust-zone value describes machines enrolled to the same
account. It does not imply a shared kernel, global memory-consistency domain,
or implicit trust between processes. Every allocation uses a short-lived lease
with a monotonically fenced token. Unisync is a future transport behind these
contracts, not an authorization layer.

Telemetry is metadata-only. It identifies work using IDs and SHA-256 digests;
`contains_user_content` is fixed to `false`, and secret/content-bearing label
names are rejected.

## Lifecycle

```text
admitted -> staged -> running -> completed
                         |       failed/cancelled/lost
                         v
                    checkpointed -> running
                         |
                         v
                       evicted -> staged
```

Terminal states cannot transition. Completed events require content-addressed
outputs; checkpointed events require a checkpoint; failed and lost events
require a structured error.

## Versioning

The discriminator is the document's `schema` field, for example
`planetary.chal.request.v1`. Changes that remove fields, alter meanings, widen
authority, or change validation rules incompatibly require a new major schema
namespace. Backward-compatible documentation or optional-field additions may
remain within v1 only after the generated schemas and tests are updated in the
same change.

Regenerate and verify the checked-in schemas with the installed Synthesus
environment:

```bash
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
