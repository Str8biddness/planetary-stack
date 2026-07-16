# Repository source map

This file records the exact sources used to seed the monorepo. It is updated
as each subtree is imported.

| Monorepo path | Source | Branch | Imported commit | State |
| --- | --- | --- | --- | --- |
| `apps/synthesus/` | `git@github.com:Str8biddness/synthesus.git` | `fix/launch-async-guard` | `407fd40` | Imported with history |
| `knowledge/knowledge-cloud/` | `git@github.com:Str8biddness/synthesus-knowledge-cloud.git` | `agent/repair-knowledge-cloud-bundle` | `ab549df` | Imported with history and LFS pointers |
| `platform/planetary-os/` | `git@github.com:Str8biddness/aivm-planetary-os.git` | `main` | `11209e9` | Imported with history |
| `platform/synthesus-os/` | `git@github.com:reality-core-systems/synthesus-os.git` | `main` | `db72d05` | Imported with history |
| `research/synthetic-intelligence-network/` | `git@github.com:Str8biddness/synthetic-intelligence-neural-network.git` | `main` | `3f5afc3` | Imported with history |

## Deliberate exclusions

- `/home/dakin/synthesus-ultra-` has the same tracked tree hash as
  `synthesus-os` at `db72d05` and is therefore not imported a second time.
- Caches, virtual environments, build products, logs, installed runtime
  state, and downloaded models are not repository sources.

## Import method

Each source was imported as a Git subtree without squashing. This retains the
available commit graph and provides a route for emergency synchronization
while canonical ownership is moved into the monorepo. The source clones were
unshallowed before import where necessary.

## Security scan state

A preliminary tracked-filename scan and high-confidence token/private-key
signature scan returned no credential candidates. This does not replace a
full history-aware secret scanner. Run `gitleaks` or an equivalent tool before
changing the GitHub repository from private to public.
