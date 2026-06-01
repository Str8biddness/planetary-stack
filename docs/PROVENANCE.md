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
- **Drift detection** — `manifest_revised_at` separates "bundle generated" from "manifest re-stamped".

## How it's produced

- `synthesus-kc build --execute` runs the full pipeline, then stamps a fresh manifest.
- `synthesus-kc stamp-manifest --profile profiles/public-base.yaml` re-stamps an existing bundle without rerunning the pipeline. The original `generated_at` is preserved; only `manifest_revised_at` and the `build` block are updated.
- `synthesus-kc info` prints the same provenance shape without modifying any file — useful for support diagnostics.

Before an executed build or manual re-stamp writes `manifest.json`, the CLI validates runtime bundle semantics that hashes alone cannot prove. FAISS vector count must match `faiss_metadata.json`, and FAISS dimensionality must match `models/swarm_embedder.pkl`. A mismatch aborts stamping so provenance cannot accidentally legitimize incompatible generated retrieval artifacts.
