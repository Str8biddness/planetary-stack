# Changelog

## 0.2.0 — 2026-05-22

Major optimization pass. The Knowledge Cloud repo is now an auditable, robust supply chain rather than a static bundle.

### Added
- **Provenance metadata** in `artifacts/manifest.json` — package version, git commit, profile, embedder fingerprint, dataset versions, host, Python version.
- **Mirror failover** — `SYNTHESUS_KNOWLEDGE_MIRRORS` env var or repeatable `--mirror` flag; downloads fail over across mirrors on transient failure.
- **Parallel + resumable sync** — `ThreadPoolExecutor` with HTTP `Range` resume so a flap on `faiss.index` (770 MB) does not restart from byte 0.
- **`status` command** — local vs remote drift report with size and sha256 checks, plus extras detection.
- **`bootstrap` command** — one-shot installer for local Synthesus runtimes; writes a `.bootstrap.json` marker recording mirror, manifest revision, and package version.
- **`build` command** — profile-aware orchestrator that wraps `pipelines/build/run_population.py`, captures provenance, and stamps the manifest. Dry-run by default, `--execute` runs the pipeline.
- **`stamp-manifest` command** — regenerate `artifacts/manifest.json` and add provenance without rerunning the pipeline.
- **`verify-source-manifest` command** — re-hash every file in `manifests/source_manifest.json` and report drift.
- **`info` command** — prints package version, resolved mirrors, git info, embedder fingerprint, dataset versions.
- **`serve` command** — tiny developer HTTP mirror over the `artifacts/` directory for end-to-end sync tests.
- **License declarations** in `sources/*.yaml` for Jeopardy, ConceptNet, planned Hugging Face, and planned Kaggle integrations.

### Changed
- Bumped package to `0.2.0`.
- `sync.py` rewritten with `SyncReport` / `ArtifactResult` types, parallel pool, retry+backoff, range resume, and mirror failover.
- `manifest.py` supports flat `.` root, exposes `verify_source_manifest`, and is consistent about excluding `manifest.json` from itself.
- `artifacts/manifest.json` now carries `kind`, `roots`, `manifest_revised_at`, and a `build` provenance block.

### Tests
- `tests/test_cli.py` extended.
- `tests/test_sync.py` — multi-artifact sync, idempotent re-sync, mirror failover (file://-mirror with first-mirror missing).
- `tests/test_status.py` — drift detection across missing, size mismatch, sha mismatch, and extras states.
- `tests/test_provenance.py` — provenance capture + manifest stamping round-trip.
- `tests/test_build.py` — dry-run plan output.

## 0.1.0 — 2026-05-21

- Split Synthesus Knowledge Cloud into a standalone public repository.
- Added manifest-verified runtime artifact bundle.
- Added source/pipeline/pattern/synthetic/support planes.
- Added initial `synthesus_knowledge_cloud` Python package and `synthesus-kc` CLI.
