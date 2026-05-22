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
3. Walk `artifacts/` and regenerate `artifacts/manifest.json` from real file hashes.
4. Capture provenance (profile, git sha, embedder fingerprint, dataset versions, host) and stamp it into the manifest's `build` block.

## Stamp without rebuilding

If the artifacts are already correct but the manifest is missing provenance (e.g. produced by a legacy build):

```bash
synthesus-kc stamp-manifest --profile profiles/public-base.yaml
```

The original `generated_at` is preserved; `manifest_revised_at` and `build` are added/updated.

## Profiles

| Profile | Intent | max_entries |
|---|---|---|
| `public-base` | Default mirror; balanced trivia + commonsense + lore | 250,000 |
| `npc-narrative` | Narrative-heavy NPC build; lower commonsense weight | 150,000 |
| `full-local` | Maximum local corpus; expensive | 1,000,000 |
