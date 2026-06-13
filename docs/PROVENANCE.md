# Build Provenance

`artifacts/manifest.json` carries a `build` block describing exactly what produced the bundle. Any consumer can read it and reason about freshness, source versions, and identity without trusting external metadata.

## Schema

```json
{
  "version": "1",
  "kind": "synthesus-knowledge-artifacts",
  "generated_at": "<ISO timestamp — when the bundle was actually generated>",
  "manifest_revised_at": "<ISO timestamp — when the manifest was last stamped>",
  "roots": ["."],
  "build": {
    "package_version": "0.2.0",
    "generated_by": "synthesus-kc build|stamp-manifest|info",
    "profile": "public-base",
    "git_commit": "<full sha or null>",
    "git_short_commit": "<short sha or null>",
    "git_branch": "main",
    "git_dirty": false,
    "python_version": "3.12.1",
    "platform": "Linux-...",
    "host": "<hostname or null>",
    "embedder": {
      "path": "models/swarm_embedder.pkl",
      "sha256": "<sha256>",
      "size": 4443817
    },
    "source_manifest": {
      "path": "manifests/source_manifest.json",
      "sha256": "<sha256>",
      "size": 25100,
      "kind": "synthesus-knowledge-source-plane",
      "generated_at": "<ISO timestamp>",
      "roots": ["sources", "synthesus_knowledge_cloud", "pipelines", "docs", "patterns", "synthetic", "grounding_corpus", "support_models", "corpus"],
      "artifact_count": 151
    },
    "datasets": {
      "jeopardy": {"version": "1", "id": "jeopardy_clue_dataset", "license": "..."},
      "conceptnet": {"version": "1", "id": "conceptnet5_assertions", "license": "..."}
    }
  },
  "artifacts": [
    {"path": "faiss.index", "size": 770794029, "sha256": "..."}
  ]
}
```

## Why it matters

- **Reproducibility** — anyone can know which profile + git sha + embedder produced the bundle.
- **Inspectability** — local Synthesus runtimes can refuse to load a bundle when the embedder fingerprint disagrees with the FAISS index expectation.
- **Auditability** — license fields per source make later distribution decisions reviewable.
- **Source-plane integrity** — the source-manifest fingerprint ties a stamped runtime bundle back to the exact hash set that admitted sources, validation package code, pipelines, provenance docs, patterns, synthetic corpora, support models, and hardware/emulation corpora into the rebuild plane.
- **Drift detection** — `manifest_revised_at` separates "bundle generated" from "manifest re-stamped".

## How it's produced

- `synthesus-kc build --execute` runs the full pipeline, then stamps a fresh manifest.
- `synthesus-kc stamp-manifest --profile profiles/public-base.yaml` re-stamps an existing bundle without rerunning the pipeline. The original `generated_at` is preserved; only `manifest_revised_at` and the `build` block are updated.
- `synthesus-kc info` prints the same provenance shape without modifying any file — useful for support diagnostics.

Before an executed build or profile-aware manual re-stamp writes `manifest.json`, the CLI validates runtime bundle semantics that hashes alone cannot prove. FAISS vector count must match `faiss_metadata.json`, FAISS dimensionality must match `models/swarm_embedder.pkl`, and the persisted swarm embedder dimension must match the selected profile's `embedding.dim`. A mismatch aborts stamping so provenance cannot accidentally legitimize incompatible generated retrieval artifacts.

Artifact and source manifests also reject duplicate `artifacts[].path` entries. A duplicate path is ambiguous provenance because two records can claim the same mounted file identity with different size/hash metadata, so validation fails before the bundle or source plane can be treated as CHAL hardware.

Source-plane validation also rejects duplicate top-level source manifest IDs across non-aggregate `sources/*.yaml` files, and rejects collisions between admitted source IDs and planned `pending[]` dataset IDs. A source ID is the durable upstream identity carried into source-manifest fingerprints, rebuild audits, and later runtime bundle provenance, so admitted and future-promoted sources cannot claim the same ID.

The aggregate catalog in `sources/datasets.yaml` is also validated against those concrete source IDs. Every `public_sources[].id` must be unique inside the aggregate file and must match a non-aggregate source manifest with its own license, loader, upstream locator, cache target, and output schema declarations. If the aggregate entry repeats `type`, `loader`, `default_enabled`, `license`, `upstream` locator values, `local_cache.files`, `filters`, or `output_schema`, those fields must match the backing manifest. Aggregate cache file entries resolve through `local_cache.directory` and must match declared concrete `cache_path` values. This keeps public Knowledge Cloud source catalogs from drifting away from the provenance-clean manifests that actually admit mounted CHAL source hardware.

`build.source_manifest` is captured from `manifests/source_manifest.json` when present. Production `synthesus-knowledge-artifacts` manifests must include this fingerprint to pass `synthesus-kc validate`; unstamped runtime bundles are treated as incomplete CHAL hardware identity. Rebuild operators should run `synthesus-kc build-source-manifest --root .` and `synthesus-kc verify-source-manifest --root .` before stamping so the runtime artifact manifest points at a current source-plane hash set.
