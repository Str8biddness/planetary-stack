# Synthesus Integration Contract

## Runtime role

The Knowledge Cloud is a cacheable external substrate for Synthesus' left/right reasoning stack:

1. `core.rag_pipeline.RAGPipeline` loads `faiss.index` and `faiss_metadata.json`.
2. `core.knowledge_cloud.KnowledgeCloud` loads structured lore from `knowledge_cloud/*.json`.
3. `ml.swarm_embedder.SwarmEmbedder` loads `models/swarm_embedder.pkl` when present.
4. KNDatabase readers use `knowledge.kndb` and metadata sidecars when available.

The Synthesus runtime should treat these files as generated cache artifacts, not source code.

## Environment variables

| Variable | Meaning |
|---|---|
| `SYNTHESUS_KNOWLEDGE_CLOUD_URL` | Base URL containing `manifest.json` and artifact paths. Default mirror: `https://zo.pub/syntech/synthesus-knowledge`. |
| `SYNTHESUS_KNOWLEDGE_SYNC_MODE` | `auto`, `on`, or `off`. `off` disables bootstrap downloads. |

## Bootstrap rules

- Local `data/` remains the cache root for Synthesus.
- On startup, Synthesus may download missing/outdated artifacts into `data/`.
- Temporary test directories should not auto-sync unless explicitly requested.
- Every downloaded file must match the manifest size and SHA-256.
- Downloads should use temporary files and atomic replacement.

## Client compatibility

Clients should support the manifest fields below:

```json
{
  "version": "1",
  "generated_at": "ISO-8601 timestamp",
  "artifacts": [
    {
      "path": "faiss.index",
      "size": 123,
      "sha256": "..."
    }
  ]
}
```

Unknown manifest fields should be ignored. Unknown artifacts should not break older clients.
