# F-030 identity lifecycle — full physical gate — 2026-07-19

## What was proven

The complete node-identity lifecycle was driven across **three physical
machines** over the pinned SSH carrier, all running the identical
implementation (`d97310a`; the coordinator enforces implementation equality).
Private keys never left any node — only CSRs and certificates crossed the wire.

- Machines: `AIVM` (192.168.68.52), `dakin-MS-7C95` (192.168.68.54),
  `dako-MS-7C89` (192.168.68.57).
- Coordinator evidence: `f030b-evidence.json` (sha256 `482732e31198c248…`).

Lifecycle steps, all passing:

1. **Enroll** — three distinct hosts, distinct node-local TLS keys; issue +
   install; all three active in the registry.
2. **Renew (same key)** — the new `renew-init` node command produced a CSR
   from the node's **existing** key (same `tls_public_key_sha256`), the CA
   `renew_certificate` issued a fresh certificate (new serial `a2381bd8…`,
   same public key), and the registry `renew_peer` kept the peer active.
3. **Rotate (new key)** — the node generated a new key, the CA
   `rotate_peer_key` issued a certificate on the new key, and the registry
   rotated to it while staying active.
4. **Revoke** — revoking `node:private-mesh:ms7c89` made `active_peer` fail
   closed; `generate_crl` produced a CRL with the revoked serial.
5. **Rollback / resurrection prevention** — re-registering the revoked node
   was blocked.
6. **Recover (ownership transfer)** — `transfer_ownership` moved
   `node:private-mesh:aivm` to a new account: the old account's enrollment
   was revoked and the new account's enrollment became active.
7. **Replace** — a fresh replacement identity (new key) enrolled and became
   active.

## Code that made this real (commit `d97310a`)

- Brought the F-030 CA-side policy code (`rotate_account_key`,
  `rotate_peer_key`, `transfer_ownership`, audit) onto clean `main` and fixed
  its two failing tests (both were test-setup bugs: state dir must be 0700;
  `active_peer` raises `AuthorizationError`, not `MeshSecurityError`).
- Added the previously-missing node-side same-key renewal path:
  `mesh_identity.create_renewal_csr` + the `renew-init` node CLI command.

## Honest remaining gaps

- **Installer-driven enrollment** (F-030 box 1) is not implemented;
  enrollment here is coordinator-driven over the SSH carrier. This box stays
  unchecked.
- **Renewed/rotated certificate re-install on the node** has no code path —
  `install_certificate` refuses to replace an installed certificate ("a TLS
  certificate is already installed; rotation is a separate gate"). Renewal and
  rotation are therefore proven at the CA + registry level; the node does not
  yet re-install the reissued certificate.
- **Certificate expiry** was not physically forced (short-TTL wait);
  `check_certificate_expiry` exists and is unit-tested.
- Independent adversarial review of the identity subsystem has not been done.

## Conclusion

F-030's core lifecycle — enroll, renew, rotate, revoke, recover (transfer),
and replace — is physically verified across three machines with keys never
copied, and the supporting code is merged and green. Two node-side
completeness gaps (renewed-cert re-install; installer enrollment) and
independent review remain before F-030 can be called fully finished.
