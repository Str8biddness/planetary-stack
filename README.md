# Planetary Stack

Planetary Stack is the integration repository for a local-first cognitive
desktop and a secure, distributed compute fabric.

The product begins as software that unifies machines a user already owns. It
can then grow into trusted private cells and an opt-in public resource network.
The interface may run as a WebSocket desktop, but the scheduler, node runtime,
knowledge plane, and isolation boundary remain independent services.

## System shape

```text
Planetary Desktop
       |
       | authenticated localhost WebSocket / HTTP
       v
Synthesus Cognitive Controller
       |
       v
CHAL device contracts
       |
       +-------------------+
       |                   |
       v                   v
vSource control plane   Knowledge Cloud
       |
       v
Unisync data plane
       |
       v
AIVM-isolated workers
```

The repository initially preserves the boundaries and histories of the
standalone projects. Migration then removes duplicate implementations and
turns those boundaries into shared packages.

## Planned layout

| Path | Responsibility |
| --- | --- |
| `apps/synthesus/` | Current local AI desktop, installer, and canonical launch path |
| `platform/planetary-os/` | Planetary kernel, kiosk shell, and Unisync design seed |
| `platform/synthesus-os/` | CHAL, AIVM, Cognitive Hypervisor, vSource blueprints, and legacy runtime seed |
| `knowledge/knowledge-cloud/` | Knowledge package, rebuild pipeline, manifests, and LFS artifacts |
| `research/synthetic-intelligence-network/` | Experimental neural-network research |
| `docs/` | Cross-component architecture, migration, security, and release contracts |
| `scripts/` | Repository-wide diagnostics and validation |

`synthesus-ultra-` is not imported separately because its tracked tree is
identical to the imported `synthesus-os` seed at commit `db72d05`.

## Start here

```bash
make doctor
make status
make test-knowledge-source
make test-synthesus
```

The full consolidation and launch sequence is in
[`MIGRATION_CHECKLIST.md`](MIGRATION_CHECKLIST.md).

## Licensing

This is currently a mixed-license repository. Synthesus is AGPL-3.0; several
platform, research, and Knowledge Cloud components are MIT. See
[`LICENSES.md`](LICENSES.md) and the license file within each imported
component.

