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
