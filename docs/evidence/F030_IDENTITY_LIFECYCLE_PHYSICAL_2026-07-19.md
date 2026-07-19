# F-030 identity lifecycle — physical partial gate — 2026-07-19

## Purpose

F-030's five checked boxes previously cited only code (`18cb37a`) with **no
physical evidence**, while F-030's acceptance and the global evidence rules
require physical machines. This run exercises the identity lifecycle across
three real machines over the pinned SSH carrier and records, honestly, both
what is proven and what is **physically blocked**.

- Machines: `AIVM` (192.168.68.52), `dakin-MS-7C95` (192.168.68.54),
  `dako-MS-7C89` (192.168.68.57), all running the identical implementation
  (`e66fbec`; the coordinator enforces implementation equality).
- Coordinator evidence: `f030-evidence.json` (sha256 `f971d42507ec72f6…`).

## Physically proven

1. **Enroll (3 nodes, keys never leave the node).** Each machine ran
   `enroll-init`, generating its TLS key locally and returning only a CSR —
   no private-key material crossed the wire (asserted). Three distinct
   hostnames and three distinct node-local TLS keys.
2. **Issue + install.** The coordinator CA issued a certificate per node
   (fingerprints `959f7f9b…`, `7247e015…`, `649875dd…`; serials
   `35437752…`, `314fd9da…`, `4dda5687…`) and each node installed and
   confirmed its exact certificate.
3. **Active enrollment.** The registry reported all three peers active.
4. **Revoke → fail closed.** Revoking `node:private-mesh:ms7c89` caused
   `active_peer` to raise "peer enrollment is revoked"; the registry record
   status became `revoked`.
5. **CRL.** `generate_crl` produced a CRL containing the revoked node's
   serial (1 revoked entry).
6. **Rollback / resurrection prevention.** Re-registering the revoked node
   was blocked, and a second revoke with a different reason was rejected.
7. **Replace.** A fresh replacement identity
   (`node:private-mesh:aivm-replacement`, new TLS key) enrolled, was issued a
   certificate (`7c499564…`), and became active.

## Physically BLOCKED — F-030 is NOT acceptance-complete

F-030's acceptance requires "enroll, **rotate**, expire, revoke, **recover**,
and replace." Two of those cannot be executed at all with the current code:

- **Renewal / key rotation is not physically executable.** The node CLI
  (`services/unisync/mesh_node_cli.py`) has `enroll-init`, `enroll-install`,
  `prepare`, `serve`, `send` — but **no renewal command**, and
  `create_tls_enrollment` refuses to reuse an existing key. The CA-side
  `renew_certificate` / registry `renew_peer` / `rotate_peer_key` exist, but
  there is no node-side path to produce a renewal CSR from the existing key,
  so same-key renewal/rotation cannot be driven across machines.
- **Account/key recovery** has the same gap: no node-side command exists to
  drive it end-to-end.
- **Installer-driven enrollment** (F-030's first, still-unchecked box) is not
  present; enrollment here is coordinator-driven over the SSH carrier.

## Merge-state finding (added after the run)

On the real `origin/main` (`9e94e69`), **all six F-030 boxes are unchecked**
and the later F-030 lifecycle commits — `18cb37a` "Complete F-030 subtasks",
the certificate-renewal API, and the online-revocation endpoint — are **not
merged**; they exist only on unmerged branches (`agent/f030-online-revocation`
and, inadvertently, an early build of the F-060 branch). Their policy tests
(`tests/unisync/test_mesh_authority_policies.py::test_rotate_peer_key`,
`test_transfer_ownership`) **fail in CI** ("mesh state directory must be an
owner-controlled mode-0700 directory"). So F-030 is not merely physically
unverified — much of it is unmerged with failing tests. This physical run used
the branch code, which is why the lifecycle primitives were available.

## Conclusion

The F-030 *core* lifecycle (enroll / issue / revoke / CRL / rollback-
prevention / replace) is physically verified across three machines with keys
never copied. But **rotate and recover are physically impossible with the
current node CLI**, so F-030's acceptance is not met and the gate is not
finished. The concrete next step to close it is to add node-side
renewal/recovery commands (a `renew-init` that signs a CSR from the existing
key, plus install) and re-run the full lifecycle including rotation. Not
addressed here either: independent adversarial review and mTLS-transport-level
rejection of a revoked peer.
