# Private-mesh Unisync mTLS gate

This gate moves one bounded content-addressed object between two enrolled
private-cell nodes over a real TCP TLS 1.3 connection. It builds on the frozen
CHAL/vSource v1 request, inventory, capability, and fenced-lease contracts; it
does not change their schema hashes.

## Trust and data path

1. Each node creates a distinct EC P-256 TLS key and CSR locally in a
   mode-0700 state directory. TLS, CHAL document-signing, and SSH identities
   remain separate. Private keys are regular mode-0600 files and never leave
   the node.
2. The coordinator verifies each CSR's account, node, SANs, signature, and
   public key, issues short-lived client/server certificates with the account
   and node embedded in the signed X.509 subject, and persists exact
   enrollment records and revocations in a mode-0600 registry. A stable
   owner-only lock serializes cross-process registry mutations so a stale
   writer cannot resurrect a revoked certificate.
3. During pinned administrative enrollment, each node persists the public
   controller and scheduler trust anchors. Transfer jobs cannot substitute a
   scheduler key alongside a forged lease.
4. The source node generates the opaque object locally. Only its SHA-256 and
   byte length return over the bootstrap channel.
5. vSource admits signed inventories and issues an active `lan_mtls` lease.
   Both nodes verify the pinned controller-signed request, the scheduler-signed
   lease, request/object membership, lease ID/digest/fence, account, source,
   destination, transport, and expiry.
6. The destination listens on one explicitly declared literal private,
   loopback, CGNAT, or ULA address. Public, wildcard, broadcast, multicast,
   documentation, and operator-CIDR-expanded public listeners fail closed.
7. TLS verifies both certificate chains, SANs, certificate fingerprints, SPKI
   fingerprints, account IDs, and node roles. The destination publishes the
   object only after content hash and size verification and returns a receipt
   bound to the full transfer context.
8. Each node records the admitted lease revision in a persistent replay fence.
   A stable owner-only lock serializes concurrent admissions. Reuse of the same
   or an older fencing token fails; crashes remain fail-stop.

SSH is only a pinned administrative bootstrap carrier. It starts fixed CLI
subcommands and carries public certificates/contracts. The workload bytes are
created on the source and reach the destination only through `lan_mtls`.

## Generic physical invocation

Run the coordinator with a strict JSON config:

```bash
python -m services.unisync.mesh_smoke --config /absolute/path/mesh-mtls.json
```

The config supplies both node IDs, SSH aliases and host-key fingerprints,
remote Python/repository/state paths, certificate SANs, the destination's
literal private bind address, pinned known-hosts file, state database,
registry, timeout, and exclusive evidence output path. No machine-specific
address, user, alias, or filesystem path is compiled into the harness.

The evidence file is created exclusively at mode 0600. It contains public
certificate and contract metadata, exact signed documents, the negotiated TLS
version/cipher, object digest/size, verified receipt, and explicit claims and
non-claims. It contains neither private keys nor object bytes.

The first accepted physical run is summarized in
[`docs/evidence/PRIVATE_MESH_MTLS_PHYSICAL_2026-07-17.md`](../../docs/evidence/PRIVATE_MESH_MTLS_PHYSICAL_2026-07-17.md).

## Non-claims

This slice does not provide production CA/HSM operations, certificate renewal
or rotation, online revocation distribution, CRL/OCSP, NAT traversal, relay,
automatic failure recovery, hardware attestation, AIVM workload isolation,
model execution, public-fabric tenancy, or a completed planetary SSI. The
Phase 5 enrollment and mTLS checklist boxes remain open until those lifecycle
and release requirements are separately closed.
