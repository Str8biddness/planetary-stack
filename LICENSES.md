# License map

Planetary Stack contains components with different licenses. A root-level
license must not be interpreted as relicensing an imported component.

| Component | Imported path | License |
| --- | --- | --- |
| Synthesus engine | `apps/synthesus/` | AGPL-3.0 (by choice, not obligation) |
| Synthesus character content | `apps/synthesus/runtime/packages/characters/` | Proprietary — Synthesus Character Content Licence 1.0 |
| Synthesus Knowledge Cloud | `knowledge/knowledge-cloud/` | MIT |
| Synthesus OS / CHAL seed | `platform/synthesus-os/` | MIT |
| Synthetic Intelligence Network | `research/synthetic-intelligence-network/` | MIT |
| AIVM Planetary OS | `platform/planetary-os/` | License clarification required |

Every component retains its original `LICENSE` file when one exists. New
cross-component code needs an explicit license decision before public release.
Until that decision is recorded, do not copy AGPL implementation code into an
MIT component or claim that the repository has one uniform license.



## Engine and character content are separate works

The engine is free software under AGPL-3.0. The character content it runs —
bio, personality, knowledge, pattern files, `.sxc` archives and identity
chains — is proprietary and licensed separately (see
`apps/synthesus/runtime/packages/characters/LICENSE`).

This split is deliberate and is the commercial model: the engine can be shared,
studied and modified; the characters are the product. Keep it clean —

* do not move character content into an AGPL-licensed path, and
* do not copy AGPL engine code into the characters package.

Every `.sxc` carries its licence terms inside the manifest, covered by the
archive digest, so terms cannot be stripped from an artifact without the
archive failing verification.

The AGPL choice on the engine is the copyright holder's, not an obligation
inherited from an imported dependency (verified 2026-07-21: `apps/synthesus/`
has a single contributor). It can therefore be revisited if the commercial
model requires it.
