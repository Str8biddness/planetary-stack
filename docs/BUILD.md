# Profile-aware Rebuild

`synthesus-kc build <profile>` is the orchestrator that produces a new artifact bundle from sources. It is intentionally **dry-run by default**: it validates the source planes, derives sample sizes from the profile, prints the plan, and exits. Add `--execute` to actually run the pipeline.

## Dry-run

```bash
synthesus-kc build profiles/public-base.yaml
```

Prints the resolved plan as JSON:

```json
{
  "profile": {
    "profile_name": "public-base",
    "sample_jeopardy": 87500,
    "sample_conceptnet": 75000,
    "embed_dim": 128,
    "outputs": {"faiss": true, "kndb": true, "sqlite_meta": true, "source_manifest": true},
    "sources": ["jeopardy", "conceptnet", "world_lore", "synthetic_lore", "character_patterns"]
  },
  "executed": false,
  "exit_code": null,
  "manifest_path": null,
  "artifact_count": 0,
  "provenance": null
}
```

## Execute

```bash
synthesus-kc build profiles/public-base.yaml --execute
```

Steps:

1. Validate source planes (`pipelines/*`, `sources/*`, `patterns/*`, `synthetic/*`, `grounding_corpus/*`, `support_models/*`).
2. Shell out to `python -m pipelines.build.run_population` with the derived sample sizes and embed dim.
3. Validate runtime bundle semantics before stamping, including FAISS vector count versus metadata records, FAISS dimension versus the persisted swarm embedder dimension, and persisted swarm embedder dimension versus the profile's declared `embedding.dim`.
4. Walk `artifacts/` and regenerate `artifacts/manifest.json` from real file hashes.
5. Capture provenance (profile, git sha, embedder fingerprint, dataset versions, host) and stamp it into the manifest's `build` block.

## Stamp without rebuilding

If the artifacts are already correct but the manifest is missing provenance (e.g. produced by a legacy build):

```bash
synthesus-kc stamp-manifest --profile profiles/public-base.yaml
```

The original `generated_at` is preserved; `manifest_revised_at` and `build` are added/updated.

`stamp-manifest --profile ...` fails without rewriting `manifest.json` when the existing runtime bundle is semantically incompatible. It must not be used to bless stale generated artifacts such as a `faiss.index` built at one dimension with a `models/swarm_embedder.pkl` persisted at another dimension, or an internally aligned retrieval pair built at a dimension that disagrees with the selected profile. Rebuild or replace the generated bundle first, then stamp.

## Profiles

| Profile | Intent | max_entries |
|---|---|---|
| `public-base` | Default mirror; balanced trivia + commonsense + lore | 250,000 |
| `npc-narrative` | Narrative-heavy NPC build; lower commonsense weight | 150,000 |
| `full-local` | Maximum local corpus; expensive | 1,000,000 |
