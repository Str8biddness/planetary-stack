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

The private repository is published at
`git@github.com:Str8biddness/planetary-stack.git`.

Git LFS accepted all 25 objects required by `main`:

```text
Uploading LFS objects: 100% (25/25), 615 MB
```

The source history contained a superseded 770 MB FAISS object whose
non-resumable upload repeatedly restarted. Before publication, a complete
backup bundle was verified and the monorepo history was normalized to replace
only that old LFS pointer with the repaired 261 MB pointer already present in
the imported Knowledge Cloud branch. The rewrite retained all 398 commits and
left the current repository tree unchanged.

A fresh clone of published commit `19c43ce` verified:

```text
SUMMARY required_missing=0 optional_missing=6
```

The sixth degraded item was intentional because the verification clone skipped
large LFS smudging. The doctor was corrected to distinguish pointer-only files
from hydrated objects. A separate LFS pull retrieved
`artifacts/knowledge.kndb` at 38,500 bytes with the expected SHA-256
`35aa50935f05151801e1c0b5473b9d6706ed0f212c78a9d1aae9cb22673b4627`.

## Authenticated local controller

The 2026-07-16 `synthesusd` service-boundary slice was validated against an
isolated headless desktop on shell port 18081 and controller port 15011 while
the primary desktop remained online:

```text
controller without API key: HTTP 401
controller health with install API key: online
runtime: online
terminal: online
terminal transport: unix_socket
terminal capability without desktop JWT: HTTP 401
terminal capability with logged-in desktop JWT: HTTP 200
terminal directory: 0700
terminal socket: 0600
unauthorized terminal WebSocket: rejected
JWT-bound authenticated PTY command + resize: passed
terminal capability absent from access logs: passed
desktop chat source: chal_runtime
isolated processes and socket after shutdown: absent
```

Focused source validation:

```text
10 passed
Python byte compilation: passed
JavaScript syntax check: passed
Installer shell syntax: passed
Desktop icon: 1254x1254 RGB PNG; favicon and launcher references present
```

Adversarial review remediation added source-level gates proving that controller
startup rejects missing/default API keys and non-loopback hosts, that the module
does not export a CLI-bindable ASGI app, and that terminal resize dimensions
stay within the unsigned-short PTY ioctl range.

The remediated entrypoint also passed a live loopback smoke: a known-default
key and `0.0.0.0` bind were refused before startup, the unique-key test daemon
returned HTTP 401 anonymously and HTTP 200 with its key, and neither test
capability appeared in its log.
