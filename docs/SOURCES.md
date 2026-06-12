# Knowledge Cloud Sources

Source declarations live under `sources/`.

## Enabled public sources

### Jeopardy clue dataset

- Manifest: `sources/jeopardy.yaml`
- Loader: `pipelines/ingest/kaggle_loader.py::load_jeopardy`
- Role: broad factual/trivia grounding
- Cache target: `data/jeopardy/`

### ConceptNet 5.7

- Manifest: `sources/conceptnet.yaml`
- Loader: `pipelines/ingest/kaggle_loader.py::load_conceptnet`
- Role: commonsense relationships
- Cache target: `data/conceptnet/`

## Curated/generated local corpora

Stored under `grounding_corpus/`:

- `kaggle_grounding_v1.txt`
- `massive_grounding_v1.txt`
- `massive_coding_v1.txt`
- `world_building_v1.txt`
- `unified_grounding_v1.txt`

These are already migrated because they represent Synthesus-specific generated/curated grounding material.

## Planned sources

### Hugging Face

Manifest: `sources/huggingface.yaml`

Do not enable automatic fetch until dataset IDs, revisions, splits, and licenses are pinned.

### Kaggle

Manifest: `sources/kaggle.yaml`

Do not commit Kaggle credentials or raw archives without checking redistribution rights.

## Source manifest validation contract

`synthesus-kc validate-sources --root .` now treats source manifests as provenance gates, not just file presence checks. Every `sources/*.yaml` declaration other than the aggregate `sources/datasets.yaml` must include:

- `version`, `id`, `name`, and `source_type`
- a `license.spdx` value and non-empty `license.notes`
- a `loader` value in `module.py::function` form
- an upstream locator (`url`, `repository`, `files`, or `docs`) for enabled sources

Top-level source manifest IDs must be unique across all non-aggregate `sources/*.yaml` files. Duplicate IDs are rejected because each source ID is a mounted hardware identity used by the source manifest fingerprint, rebuild plan, and artifact provenance trail. The same namespace also covers planned `pending[]` dataset IDs: a pending source cannot reuse the ID of an already-admitted source manifest because that would make later promotion into mounted CHAL provenance ambiguous.

The aggregate `sources/datasets.yaml` file may summarize `public_sources[]`, but every listed public source ID must resolve to a concrete non-aggregate source manifest such as `sources/jeopardy.yaml` or `sources/conceptnet.yaml`. Duplicate aggregate public-source IDs are rejected. When an aggregate entry repeats `type`, `loader`, `default_enabled`, `license`, `upstream` locator values, or `local_cache.files`, those values must match the backing manifest. Aggregate cache files are resolved against `local_cache.directory` and must appear as concrete `cache_path` declarations in the source manifest. This prevents the public rebuild catalog from advertising a CHAL source identity that has no license block, loader contract, upstream locator, source cache target, or matching source type/license/enablement state in the validated source-manifest plane.

Planned aggregate manifests such as Hugging Face or Kaggle may stay `default_enabled: false`, but every `pending[]` dataset still needs its own unique `id`, pinned upstream locator (`repo`, `url`, `repository`, `dataset`, or non-empty `files`), `license.spdx`, non-empty `license.notes`, and a non-empty `rebuild_command`. Duplicate pending IDs are rejected across all source manifests, and pending IDs may not collide with concrete source manifest IDs, so a future public dataset cannot enter the rebuild substrate with ambiguous source identity. Rebuild commands are required even for disabled planned datasets because they bind future public-source expansion to an auditable regeneration route before the source can become mounted CHAL hardware.
