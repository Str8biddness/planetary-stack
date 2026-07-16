# Repository source map

This file records the exact sources used to seed the monorepo. It is updated
as each subtree is imported.

| Monorepo path | Source | Branch | Imported commit | State |
| --- | --- | --- | --- | --- |
| `apps/synthesus/` | `git@github.com:Str8biddness/synthesus.git` | `fix/launch-async-guard` | `407fd40` | Pending import |
| `knowledge/knowledge-cloud/` | `git@github.com:Str8biddness/synthesus-knowledge-cloud.git` | `agent/repair-knowledge-cloud-bundle` | `ab549df` | Pending import |
| `platform/planetary-os/` | `git@github.com:Str8biddness/aivm-planetary-os.git` | `main` | `11209e9` | Pending import |
| `platform/synthesus-os/` | `git@github.com:reality-core-systems/synthesus-os.git` | `main` | `db72d05` | Pending import |
| `research/synthetic-intelligence-network/` | `git@github.com:Str8biddness/synthetic-intelligence-neural-network.git` | `main` | `3f5afc3` | Pending import |

## Deliberate exclusions

- `/home/dakin/synthesus-ultra-` has the same tracked tree hash as
  `synthesus-os` at `db72d05` and is therefore not imported a second time.
- Caches, virtual environments, build products, logs, installed runtime
  state, and downloaded models are not repository sources.

