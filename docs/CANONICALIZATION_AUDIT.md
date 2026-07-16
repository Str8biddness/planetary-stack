# Canonicalization audit

## Initial finding

The active Synthesus repository contains a runtime at
`apps/synthesus/runtime/`. The historical Synthesus OS seed contains a second
runtime-shaped tree at `platform/synthesus-os/`.

A Git-tree comparison performed after import found:

- 388 differing paths.
- 99 modified paths.
- 79 paths present only in the historical platform seed.
- 210 paths present only in the active runtime.

The difference is substantial and is not safe to resolve by deleting either
tree wholesale. The platform seed contains unique CHAL, AIVM, kernel, trained
support artifacts, vSource documentation, and test material. The active
runtime contains later launch hardening, memory provenance work, fixtures,
and the currently tested desktop/runtime integration.

## Provisional ownership decision

`apps/synthesus/runtime/` is the canonical product runtime during migration.

`platform/synthesus-os/` is a read-only migration seed except for:

- extracting unique CHAL contracts;
- extracting AIVM isolation and execution work;
- extracting Cognitive Hypervisor work;
- extracting vSource and software-defined hardware specifications;
- extracting kernel code and tests that do not already have a canonical home;
- recording provenance for unique trained/support artifacts.

No new product feature should be implemented twice.

## Extraction order

1. Inventory unique architecture documents and promote them into `docs/`.
2. Compare CHAL frame and hypervisor implementations and tests.
3. Compare AIVM isolation, scheduler, and execution implementations and tests.
4. Compare kernel source while excluding committed build products.
5. Compare Knowledge Cloud integrations against the standalone package.
6. Compare API and desktop surfaces.
7. Move unique accepted work into the canonical runtime with targeted tests.
8. Move the remaining historical tree under `archive/` and enforce read-only
   status in CI.

## Required evidence for each extraction

- Source and destination paths.
- Reason the selected implementation is canonical.
- Tests added or retained.
- Real validation output.
- License and artifact-provenance impact.
- Explicit list of historical files retired.
