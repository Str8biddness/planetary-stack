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

Planned aggregate manifests such as Hugging Face or Kaggle may stay `default_enabled: false`, but every `pending[]` dataset still needs its own unique `id`, `license.spdx`, non-empty `license.notes`, and a non-empty `rebuild_command`. Duplicate pending IDs are rejected across all source manifests so a future public dataset cannot enter the rebuild substrate with ambiguous source identity. Rebuild commands are required even for disabled planned datasets because they bind future public-source expansion to an auditable regeneration route before the source can become mounted CHAL hardware.
