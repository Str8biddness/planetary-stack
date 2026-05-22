# Synthesus Knowledge Cloud

Standalone public repository for the Synthesus Knowledge Cloud data supply chain.

This repo exists so anyone running Synthesus locally can bootstrap the shared knowledge layer without rebuilding the corpus, while still preserving the source manifests, grounding corpora, pattern banks, and synthetic narrative generation pipeline needed to audit or regenerate the cloud.

## Public mirror

The always-online artifact mirror is:

```text
https://zo.pub/syntech/synthesus-knowledge
```

Synthesus defaults to this URL through `SYNTHESUS_KNOWLEDGE_CLOUD_URL` unless sync is disabled.

## Repository layout

```text
artifacts/              # compiled runtime bundle for local Synthesus installs
sources/                # upstream dataset manifests and license/fetch metadata
pipelines/              # ingestion, build, validation, and publish pipeline code
patterns/               # global + character pattern/knowledge/persona seed data
synthetic/              # lore forge, transition learning, synthetic generation scripts
grounding_corpus/       # curated/generated grounding text corpora
support_models/         # vocabularies, priors, checkpoints, small support artifacts
manifests/              # source-plane manifests generated from this repository
docs/                   # integration, source, rebuild, and data-model documentation
scripts/                # client sync + validation utilities
```

## Artifact layout

```text
artifacts/
  manifest.json
  faiss.index
  faiss_metadata.json
  knowledge.kndb
  knowledge.kndb.meta.db
  knowledge.meta.db
  models/
    swarm_embedder.pkl
  knowledge_cloud/
    world_lore.json
    transitions.json
    learned_transitions.json
    chaining_patterns.json
```

| Artifact | Purpose |
|---|---|
| `faiss.index` | Vector index for semantic retrieval |
| `faiss_metadata.json` | Metadata records aligned to FAISS vector IDs |
| `models/swarm_embedder.pkl` | Local embedder used to generate compatible query vectors |
| `knowledge_cloud/world_lore.json` | Structured lore and high-signal knowledge entries |
| `knowledge_cloud/transitions.json` | Hand-curated transition graph for sequence linking |
| `knowledge_cloud/learned_transitions.json` | Learned transition candidates |
| `knowledge_cloud/chaining_patterns.json` | Pattern-chaining support data |
| `knowledge.kndb` | KNDatabase binary payload |
| `knowledge.kndb.meta.db` | KNDatabase metadata sidecar |
| `knowledge.meta.db` | Additional knowledge metadata sidecar |

## Source and generation planes

The cloud is more than the FAISS files. The repo also carries:

- Jeopardy and ConceptNet source manifests
- planned Hugging Face and Kaggle source manifests
- generated grounding corpora such as `world_building_v1.txt` and `massive_grounding_v1.txt`
- global and character-specific pattern banks
- character knowledge/personality/bio seeds
- synthetic lore generation scripts
- transition-learning scripts
- small vocab/policy/checkpoint support artifacts

See:

- `docs/DATA_MODEL.md`
- `docs/SOURCES.md`
- `docs/REBUILDING.md`
- `docs/PIPELINE_ROADMAP.md`

## Use from Synthesus

From a local Synthesus checkout:

```bash
export SYNTHESUS_KNOWLEDGE_CLOUD_URL="https://zo.pub/syntech/synthesus-knowledge"
export SYNTHESUS_KNOWLEDGE_SYNC_MODE="auto"
python -m knowledge_integration.cloud_sync --root ./data
```

Current Synthesus builds also try to auto-bootstrap missing cache files on startup when the standard `data/` cache is empty.

Disable cloud sync when you need fully offline/local behavior:

```bash
export SYNTHESUS_KNOWLEDGE_SYNC_MODE=off
```

## Use without Synthesus

Download and verify the compiled runtime bundle directly:

```bash
python scripts/sync_knowledge_cloud.py --dest ./data
python scripts/validate_bundle.py --root ./data
```

To download from the checked-in `artifacts/` folder instead of the public mirror:

```bash
python scripts/sync_knowledge_cloud.py --dest ./data --base-url "file://$PWD/artifacts"
```

## Validation

```bash
python scripts/validate_bundle.py --root artifacts
python scripts/validate_source_planes.py --root .
python scripts/build_source_manifest.py --root .
python scripts/sync_knowledge_cloud.py --dest /tmp/synthesus-kc-smoke --base-url "file://$PWD/artifacts"
```

## Publish/update workflow

1. Build or refresh the bundle in a staging directory.
2. Regenerate `artifacts/manifest.json` with SHA-256 and byte sizes.
3. Replace `artifacts/` in this repo.
4. Validate locally.
5. Commit and push this repo.
6. Sync the hosted mirror:

```bash
zopub sync synthesus-knowledge artifacts
```

## Versioning contract

- `artifacts/manifest.json` uses `version: "1"`.
- Artifact paths are part of the public client contract.
- Clients must verify size and SHA-256 before trusting downloaded files.
- Missing optional artifacts should degrade behavior, not break startup.
- Source-plane manifests exist for rebuild/audit workflows, not runtime sync.

## License

MIT. See `LICENSE`.
