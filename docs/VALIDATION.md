# Initial monorepo validation

Date: 2026-07-16

## Repository integration

- Five standalone histories imported as unsquashed Git subtrees.
- `synthesus-ultra-` excluded because its tracked tree matches the imported
  `synthesus-os` seed at `db72d05`.
- Knowledge Cloud LFS pointers imported and the current 615 MB checkout
  hydrated from the existing local LFS object store.
- Preliminary filename and high-confidence token/private-key signature scans
  found no tracked credential candidates. A dedicated `gitleaks` or equivalent
  history scan is still required before making the repository public.

## Passing checks

### Root diagnostics

```text
required_missing=0
```

Optional tools reported honestly as degraded on this machine: Bun, CMake,
QEMU, xorriso, and NVIDIA tooling.

### Knowledge Cloud

```text
validated 10 artifacts
source planes ok: 25 required paths, 7 character pattern banks
54 passed
```

The real HTTP sync test requires localhost socket access and passed outside
the restricted execution sandbox.

### Planetary kernel

The bare-metal `synthesus.bin` target builds successfully from an isolated
temporary directory. Imported `.o`, binary, and generated ISO staging files
are no longer tracked at the monorepo head.

Linker warnings remain for:

- missing `.note.GNU-stack` in `boot.o`;
- relocations in read-only `.text`;
- a position-independent executable producing `DT_TEXTREL`.

Full ISO packaging is blocked on this host because `xorriso` is not installed.

## Open runtime regression

The full imported Synthesus runtime suite completed with:

```text
1 failed, 1725 passed, 30 skipped, 3 xfailed
```

Failure:

```text
tests/test_knowledge_evolution.py::test_knowledge_evolution_propagation
```

The standalone checkout skips this test when no Knowledge Cloud
`world_lore.json` artifact is mounted. The integrated monorepo mounted the real
Knowledge Cloud, causing the test to execute and reveal that a newly witnessed
fact persisted to `evolution.json` but was not selected over older lore during
the next NPC query.

This is a genuine integration regression, not a subtree import mismatch. It
must be fixed under the Synthesus runtime's nested agent ownership rules before
the full suite can be declared green.

## GitHub publication

Publication is currently blocked because the local GitHub CLI credential for
`Str8biddness` is expired or invalid. The local repository and commits remain
intact. Re-authentication is required before creating and pushing
`Str8biddness/planetary-stack`.
