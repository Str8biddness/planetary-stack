# Synthesus Knowledge Cloud

Standalone public artifact repository for the Synthesus FAISS Knowledge Cloud.

This repo exists so anyone running Synthesus locally can bootstrap the shared knowledge layer without rebuilding the corpus. It contains the FAISS index, metadata, KNDatabase sidecars, world-lore JSON, transition/chaining data, the trained swarm embedder, and a cryptographic manifest.

## Public mirror

The always-online mirror is:

```text
https://zo.pub/syntech/synthesus-knowledge
```

Synthesus defaults to this URL through `SYNTHESUS_KNOWLEDGE_CLOUD_URL` unless sync is disabled.

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

Current manifest summary:

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

Download and verify the bundle directly:

```bash
python scripts/sync_knowledge_cloud.py --dest ./data
python scripts/validate_bundle.py --root ./data
```

To download from the checked-in `artifacts/` folder instead of the public mirror:

```bash
python scripts/sync_knowledge_cloud.py --dest ./data --base-url "file://$PWD/artifacts"
```

## Publish/update workflow

1. Build or refresh the bundle in a staging directory.
2. Regenerate `manifest.json` with SHA-256 and byte sizes.
3. Replace `artifacts/` in this repo.
4. Validate locally:

```bash
python scripts/validate_bundle.py --root artifacts
python scripts/sync_knowledge_cloud.py --dest /tmp/synthesus-kc-smoke --base-url "file://$PWD/artifacts"
```

5. Commit and push this repo.
6. Sync the hosted mirror:

```bash
zopub sync synthesus-knowledge artifacts
```

## Versioning contract

- `manifest.json` uses `version: "1"`.
- Artifact paths are part of the public client contract.
- Clients must verify size and SHA-256 before trusting downloaded files.
- Missing optional artifacts should degrade behavior, not break startup.

## License

MIT. See `LICENSE`.
