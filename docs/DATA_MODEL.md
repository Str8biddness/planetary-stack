# Synthesus Knowledge Cloud Data Model

The Knowledge Cloud is split into five planes. This keeps local Synthesus installs fast while preserving enough source material to rebuild, audit, and expand the cloud.

## 1. Runtime artifact plane

Path: `artifacts/`

This is the compiled bundle consumed by local Synthesus runtimes.

- `faiss.index` — semantic vector index
- `faiss_metadata.json` — vector-aligned metadata
- `knowledge.kndb` — KNDatabase binary payload
- `knowledge.kndb.meta.db` / `knowledge.meta.db` — metadata sidecars
- `models/swarm_embedder.pkl` — fitted query embedder
- `knowledge_cloud/*.json` — lore, transitions, chaining, learned transition data
- `manifest.json` — SHA-256/size verification contract

## 2. Source dataset plane

Path: `sources/`

This plane declares upstream public datasets and how to transform them. Raw third-party archives are not blindly vendored because license and redistribution rules vary.

Current enabled sources:

- Jeopardy clue TSV from `jwolle1/jeopardy_clue_dataset`
- ConceptNet 5.7 assertions

Planned/pinned-before-enable sources:

- Hugging Face mathematical reasoning datasets
- Hugging Face character/dialogue datasets
- Kaggle datasets that require explicit credential/license handling

## 3. Grounding corpus plane

Path: `grounding_corpus/`

Curated/generated text corpora used for grounding, transition learning, and narrative simulation support.

Examples:

- `kaggle_grounding_v1.txt`
- `massive_grounding_v1.txt`
- `massive_coding_v1.txt`
- `world_building_v1.txt`
- `unified_grounding_v1.txt`

## 4. Pattern plane

Path: `patterns/`

Pattern memory used by PPBRS and narrative response selection.

- `patterns/global/initial_patterns.json`
- `patterns/characters/*/patterns.json`
- Character knowledge/personality/bio seed data
- Character schemas and registry

## 5. Synthetic narrative plane

Path: `synthetic/`

Scripts and recipes that produce structured lore, transition graphs, and synthetic narrative simulation entries.

- `synthetic/lore_forge/lore_forge.py`
- `synthetic/generation_scripts/mass_generate_entries.py`
- `synthetic/generation_scripts/learn_transitions.py`
- `synthetic/generation_scripts/generate_bulk_patterns.py`

## 6. Support model plane

Path: `support_models/`

Small support artifacts that are not the FAISS query embedder but still support local runtime behavior and training.

- vocabularies
- policy priors
- checkpoints
- parameter cloud snapshots/stats

## Integrity contracts

- `artifacts/manifest.json` validates runtime downloads.
- `manifests/source_manifest.json` validates source/pipeline/pattern/synthetic/support planes.
- Both manifest types reject duplicate artifact paths so one file identity cannot carry competing provenance or integrity records.
- Runtime clients should use the artifact manifest.
- Rebuild/audit tools should use both manifests.
