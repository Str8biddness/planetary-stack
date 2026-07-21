# Proposal: bounded response slots for the exchange return leg

**Status: PROPOSAL — not built. Revision 2.**
Written 2026-07-21 in response to the blocker recorded in
`EXCHANGE_RESPONSE_AUTHORITY.md`. Nothing in this document has been implemented.

**Review decision (owner, 2026-07-21): open question 2 answered YES — filling a
slot MUST carry an execution evidence document.** Revision 2 folds that in; it
is now a requirement of the mechanism, not an option. See "Required evidence"
and "Self-attestation: what this does and does not buy" below.

## The problem, precisely

`services/unisync/exchange.py` moves a request to a worker and a response back
on one lease-bound mTLS socket. The transport works. The *authority* does not:
the production `SignedLeaseValidator` rejects the return leg for two independent
reasons, verified against the genuine signed documents from the 2026-07-20
physical pull.

1. **A lease pins one destination node** (`mesh_lease.py:179`). The return leg
   delivers to the requester, a different node.
2. **The object must be an exact content reference in the signed request**
   (`mesh_lease.py:189-196`). A response digest cannot exist before the handler
   has run.

Blocker 2 is the hard one. It cannot be solved by issuing more leases, because
no party can name the digest of a computation that has not happened yet.

## The honest framing

Today's model is: *the owner pre-approves exact bytes.* Every object that moves
was named, by digest, in something the owner's controller signed. That is a
strong property and it is why the transfer story holds up.

**That property cannot survive contact with computation.** The entire point of
sending a prompt to a worker is to receive bytes nobody has seen yet. Any design
that returns a computed result necessarily weakens "pre-approved exact bytes" to
something else.

So the question is not *how do we keep the guarantee* — we cannot. The question
is *what is the strongest guarantee that survives*, and whether it is strong
enough to sell. This proposal argues the answer is:

> The owner pre-approves a **bounded, single-use, attributable channel** from one
> named node, for one named request.

If a reviewer thinks that is not strong enough, the correct conclusion is that
the private mesh should not carry inference at all — not that the bounds should
be loosened until it fits.

## Proposed mechanism

### 1. A `ResponseSlot` declared in the signed request

The controller signs it as part of the `ChalRequest`, so it is already covered
by `request_sha256`, which the lease already binds. No new signing key, no new
trust root.

```
ResponseSlot:
  slot_id            stable id, unique within the request
  responder_node_id  the ONLY node permitted to fill it
  destination_node_id the ONLY node permitted to receive it
  max_byte_length    hard ceiling, <= the transport's max_total_bytes
  media_type         exact string; no wildcards, no lists
```

This mirrors how a CHAL request already declares `outputs` as a slot
(`output:classification:001`) rather than a digest — the shape is not novel to
this codebase.

### 2. A lease pair, minted atomically

The scheduler issues two leases for one placement:

- **forward lease** — `node_id` = responder (unchanged semantics)
- **return lease** — `node_id` = requester

Both carry the same `placement_id` and `request_sha256`. This preserves the
invariant that made blocker 1 fire — *a lease is authority to deliver to exactly
one node* — instead of eroding it. `mesh_lease.py:179` stays exactly as it is.

Minting them atomically matters: a return lease that can be obtained
independently of a forward lease is a standalone "send me bytes" capability.

### 3. Required evidence: a slot is filled with a signed envelope, not raw bytes

A slot fill is **one** object: a canonical envelope carrying both the result and
the execution evidence for it. One object keeps the single-transfer shape and
keeps `max_byte_length` meaningful as a total ceiling.

```
ResponseEnvelope:
  schema           "planetary.mesh.response_envelope.v1"
  slot_id          the slot being filled
  request_sha256   the signed request this answers
  result_sha256    digest of the result bytes
  result           the result bytes (bounded, inline)
  evidence         the AIVM ExecutionEvidence record
  signature        ed25519 over the canonical envelope, by the responder's
                   node contract key
```

`ExecutionEvidence` already exists and is already produced on every run
(`aivm/execution/podman.py:806`). It carries exactly the fields this needs:
`manifest_sha256`, `lease_id`, `lease_sha256`, `fencing_token`, `node_id`,
`immutable_image_ref`, `entrypoint_id`, `input_set_sha256`, `output_set_sha256`,
`outputs`, plus host capability evidence (`rootless`, `seccomp_enabled`,
`image_digest`). Today's end-to-end physical run returned it alongside the
result as output `cdb217a7…`.

**It is currently UNSIGNED.** `chal_adapter.py` serialises the record and hashes
it; nothing signs it. Signing it with the responder's node contract key is new
work — but it needs no new trust material: those keys are already in the mesh
trust bundle (`node_contracts[].public_key_base64`), already distributed, and
already verified for inventories.

On receipt, before the result is handed to any caller, the requester checks:

- the envelope signature verifies against the enrolled responder's contract key,
  and that node is the slot's `responder_node_id`;
- `evidence.lease_id` / `lease_sha256` / `fencing_token` match the forward lease;
- `evidence.manifest_sha256` matches the manifest the owner signed;
- `evidence.immutable_image_ref` and `host.image_digest` match the image digest
  pre-approved in the request;
- `evidence.entrypoint_id` matches the approved entrypoint;
- `evidence.input_set_sha256` derives from content references the owner already
  approved by digest;
- `evidence.output_set_sha256` covers `result_sha256`, and
  `sha256(result) == result_sha256`;
- `host.rootless` is true and `seccomp_enabled` is true.

Any failure fails the slot closed and the result is never returned to the
caller.

### 4. A narrowly scoped relaxation of the content-reference rule

`SignedLeaseValidator` gains one alternative branch. An object is authorized if
it is an exact content reference **(unchanged, and still the only path for
artifacts)** *or* if all of the following hold:

- the transfer context names a `slot_id` present in the signed request;
- `context.source_node_id == slot.responder_node_id`;
- `context.destination_node_id == slot.destination_node_id`;
- `context.byte_length <= slot.max_byte_length`;
- the slot has not been filled before under this lease revision
  (durable replay fence, reusing `LeaseUseStore`, keyed by `slot_id`);
- the existing "response must not repeat the request object" check still passes;
- the envelope and evidence checks in §3 all pass.

The transferred object's digest is deliberately **unconstrained by the signed
request** on this path. That is the whole concession, stated in one place so it
can be reviewed as one decision.

## What is actually lost, stated plainly

A compromised-but-enrolled responder can return **any bytes it likes**, up to
`max_byte_length`, once per slot. Digest verification on the return leg proves
the bytes arrived intact; it does not prove they are the bytes the owner
approved, because the owner never saw them.

This is not a weakness introduced by slots. It is the irreducible cost of
computing on a machine you do not fully control, and it is present in every
system of this kind. What slots do is *bound the blast radius*; what required
evidence does is make the result **attributable and internally constrained**.

## Self-attestation: what required evidence does and does not buy

Requiring signed evidence does **not** make a compromised node honest. The node
holds its own contract key, so it can sign a false evidence record. This is
*self-attestation*, not third-party attestation, and the document must not be
marketed as more than that.

What it does buy is real, and it is more than attribution:

1. **Everything around the output is pinned to owner-signed values.** The image
   digest, entrypoint, manifest digest, input digests, lease and fencing token
   were all approved by the owner *by digest, in advance*. The output bytes are
   the only unconstrained value in the envelope. A lie has to be told in a very
   narrow place, surrounded by values the liar cannot alter.
2. **A lie becomes durable and attributable.** To return false bytes, a node
   must produce a signed statement, under its own enrolled key, naming the
   owner's own approved image and lease. That artifact persists and is
   non-repudiable. Silent tampering becomes signed forgery.
3. **Determinism converts attestation into verification.** For a deterministic
   profile the owner can re-execute and compare. The text-classification result
   used throughout this project is byte-identical across every execution path
   physically proven so far (`5df96635…`, 314 bytes, single-node,
   mesh-delivered, remote-backend, three-node cell, pull gate). Where a profile
   is deterministic, evidence + re-execution is a *complete* check, not a
   partial one.
4. **Isolation claims travel with the result.** `host.rootless` and
   `host.seccomp_enabled` arrive attached to the bytes rather than being assumed
   of the node in general.
5. **It is the hook hardware attestation plugs into later.** The attestation
   ladder already exists (`unverified` → `software_verified` →
   `hardware_verified`) and every physical run to date is `unverified`. When a
   node can attest in hardware, this envelope is where that evidence lands, and
   the self-attestation caveat above weakens accordingly.

The honest one-line claim, for the product and for a customer: *the result is
bound to an approved image, approved inputs, and one named machine, signed by
that machine — and for deterministic workloads you can re-run it and check.*

## What is retained

- **Attribution.** The receipt binds the responder's certificate, the slot, and
  the request digest. Bytes are non-repudiably traceable to one enrolled node.
- **Confidentiality and integrity in transit.** Unchanged: TLS 1.3, mutual auth,
  SAN pinning, enrollment binding, chunk digests, receipt.
- **A hard size ceiling.** A compromised node cannot use the return leg as a
  bulk exfiltration or flooding channel.
- **Single use.** One slot, one fill, fenced by the lease revision.
- **No lateral reach.** A node can fill only slots naming it, for requests it
  was actually leased, to the single destination named.

## Threat cases this must survive

| Attack | Defence |
|---|---|
| Oversized response | `max_byte_length`, enforced before assembly |
| Slot filled twice | durable replay fence keyed by `slot_id` + lease revision |
| Response to a different request | slot is inside the signed request; `request_sha256` bound |
| Another node fills the slot | `responder_node_id` + mutual-TLS peer identity must agree |
| Response redirected to another node | return lease pins `node_id`; slot pins destination |
| Stale lease revision replayed | existing fencing-token check, unchanged |
| Request object echoed back as a "result" | existing echo check in `exchange.py` |
| Slot used to smuggle an artifact on the forward leg | slot path requires `source == responder_node_id` |
| Return lease obtained without a forward lease | leases minted atomically per placement |
| Result returned with no evidence, or evidence stripped | envelope schema requires it; unsigned or absent fails closed |
| Evidence copied from a different run | evidence binds lease id, lease digest, fencing token, manifest digest |
| Evidence signed by another node | signature must verify against the slot's `responder_node_id` contract key |
| Result swapped after evidence was produced | `output_set_sha256` must cover `result_sha256`, which must hash the bytes |
| Approved image claimed, different image run | `immutable_image_ref` and `host.image_digest` must match the pre-approved digest |

## Explicitly NOT proposed

- Wildcard or list-valued media types
- Unbounded or caller-supplied response size
- Slots that outlive the lease window
- Reusable / multi-fill slots
- Any relaxation of the content-reference rule for artifact transfers
- Unsigned evidence, or a slot fill that omits evidence
- Treating self-attested evidence as hardware attestation in any user-facing text

## Cost and ripple

- `contracts/chal_vsource/v1/models.py` — new `ResponseSlot`; request gains an
  optional slot list. **Wire-format change**, needs a version decision.
- `TransferContext` — needs an optional `slot_id`. `from_wire` enforces an exact
  field set, so this is also a wire-format change affecting every node.
- `SignedLeaseValidator` — one alternative branch, as above.
- Scheduler — atomic lease-pair minting.
- `exchange.py` — `derive_response_context` carries the slot id; the do-not-wire
  banner comes off only when all of the above is real.
- **`ExecutionEvidence` must be signed.** It is produced unsigned today
  (`chal_adapter.py` serialises and hashes it; nothing signs it). Signing uses
  the node contract key already in the trust bundle, so no new trust material —
  but the signing path, the envelope type, and its verifier are new code.

Two of these are wire-format changes across every node. This is not a small
change, and staging it (contracts → validator → scheduler → transport) matters.

## Open questions for review

1. **Is a bounded attributable channel sufficient for the product's privacy
   claim?** If not, stop here — this is the strongest honest version.
2. ~~Should filling a slot require an execution evidence document?~~
   **ANSWERED YES by the owner, 2026-07-21.** Folded into §3 as a requirement.
   Follow-on now open: should a slot fill be rejected when
   `host.rootless` is false or `seccomp_enabled` is false, or should that be a
   recorded warning? This proposal assumes **rejected**.
3. Should `max_byte_length` have a low protocol-level ceiling independent of
   what a request may ask for?
4. One slot per request, or several? Several enables streaming later; several
   also multiplies the fence's state and the review surface.
5. Is the lease *pair* right, or should the return authority be a distinct
   document type that is not a lease at all?

## Status

- Not implemented. `exchange.py` remains do-not-wire.
- Physical two-machine exchange run: still **NOT DONE**, still blocked.
- No FINISH_CHECKLIST box is checked by this document.
