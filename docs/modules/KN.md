# KN — Knowledge Node System

> Synthesus 3.0 — Knowledge Index Architecture

## Overview

The KN (Knowledge Node) system is Synthesus's persistent, queryable memory layer for entities, relationships, and facts. It organizes knowledge as a graph of typed nodes connected by weighted edges, with optional vector-based semantic search via FAISS.

## Architecture

```
User Query
    │
    ▼
KnowledgeNetwork (graph storage + keyword search)
    │
    ├──► SemanticIndexer (FAISS + SwarmEmbedder)
    │         ~50KB TF-IDF+SVD embedder, <1ms inference
    │
    └──► EntityLinker (mention → canonical node resolution)
              │
              ▼
         Response Enhancement
```

## Key Files

| File | Purpose |
|------|---------|
| `kn/__init__.py` | Module entry point — exports all public classes |
| `kn/node.py` | NodeType, EdgeType, Edge, KNode, and typed subclasses |
| `kn/network.py` | KnowledgeNetwork — core graph manager |
| `kn/semantic_indexer.py` | SemanticIndexer — FAISS-backed vector semantic search |
| `kn/entity_linker.py` | EntityLinker — text-to-node mention resolution |
| `kn/graph_connector.py` | GraphConnector — bulk import pipeline |
| `packages/knowledge/mount_table.py` | Synthesus 5 CHAL mount-table boot and Knowledge Cloud artifact integrity verification |
| `knowledge_integration/kaggle_loader.py` | KaggleLoader — High-quality fact ingestion from Jeopardy/ConceptNet |

## Core Components

### KnowledgeNetwork (`kn/network.py`)

Manages the persistent graph of typed nodes and weighted edges. Supports auto-save, keyword search, and contextual subgraph retrieval.

```python
from kn import KnowledgeNetwork, SemanticIndexer, EntityLinker, GraphConnector
from kn.node import NodeType, KNode

kn = KnowledgeNetwork(index_path="data/kn_index.json", graph_path="data/knowledge_graph.pkl")
kn.register_node(KNode(id="gorn", node_type=NodeType.PERSON, content="A merchant in the riverside tavern."))
kn.add_edge("gorn", "tavern", EdgeType.LOCATED_AT, weight=0.9)
results = kn.search("merchant", top_k=5)
```

### SemanticIndexer (`kn/semantic_indexer.py`)

Vector-based semantic similarity search using TF-IDF + SVD embeddings (SwarmEmbedder) backed by FAISS IndexFlatIP. Recent updates include **Similarity Floor Tuning (0.12)** and **TF-IDF threshold adjustments** for better recall in noisy domains.

```python
indexer = SemanticIndexer(kn=kn)
indexer.index_nodes(kn.list_nodes())
results = indexer.search("fire-breathing creatures", top_k=5)
```

### EntityLinker (`kn/entity_linker.py`)

Resolves textual mentions (names, aliases, pronouns) to canonical node IDs with fuzzy matching and LRU caching.

```python
linker = EntityLinker(kn=kn)
result = linker.link_mention("Gorn the merchant")
if result:
    print(f"Resolved to: {result.node_id} (confidence: {result.confidence:.2f})")
```

### GraphConnector (`kn/graph_connector.py`)

Bridges external data sources (JSON, world lore) into the KN graph with automatic edge creation and duplicate detection.

```python
connector = GraphConnector(kn=kn, linker=linker, indexer=indexer)
stats = connector.import_json("data/world_lore.json", create_edges=True)
print(f"Imported {stats['nodes_added']} nodes, {stats['edges_added']} edges")
```

## Node Types

| Type | Description |
|------|-------------|
| `PERSON` | Characters, NPCs, players |
| `PLACE` | Locations, cities, buildings |
| `ITEM` | Objects, artifacts, weapons |
| `FACTION` | Organizations, guilds, governments |
| `EVENT` | Historical or in-world events |
| `CREATURE` | Monsters, beasts, dragons |
| `KNOWLEDGE` | Facts, lore, rules |
| `UNKNOWN` | Uncategorized |

## Edge Types

| Type | Description |
|------|-------------|
| `RELATED_TO` | General relationship |
| `LOCATED_AT` | Spatial containment |
| `PART_OF` | Hierarchical membership |
| `ALLIED_WITH` | Alliance or friendship |
| `HOSTILE_TOWARD` | Opposition or enemy |
| `CAUSED_BY` | Causal chain |
| `KNOWS_ABOUT` | Knowledge relationship |
| `AFFECTED_BY` | Influence relationship |

## Knowledge Population

The knowledge integration pipeline sources data from:
1. **Jeopardy Questions** — ~216,930 Q&A pairs (diverse trivia facts)
2. **ConceptNet Assertions** — ~2M commonsense knowledge edges

**Production Scale Population (2026-04-27):**
- Total index size: **501,819 vectors**.
- Verified semantic search quality across Science, History, Geography, and Fiction domains.
- Integrated **Lore Forge** synthetic data for narrative grounding.

Data flows through:
1. `knowledge_integration/kaggle_loader.py` — Download and parse external datasets
2. `knowledge_integration/kn_populator.py` — Transform raw data into KN nodes
3. `knowledge_integration/lore_forge.py` — Generate high-fidelity synthetic lore nodes
4. Build artifacts stored in `data/` (gitignored)

## Synthesus 5 CHAL Mount Table

The Knowledge Cloud now boots as mounted CHAL hardware when a local artifact `manifest.json` is present. `KnowledgeCloudMountTable` reads the manifest, maps known artifacts into typed mounts, and verifies each file's declared byte size and SHA-256 before activating the mount.

Default mount mappings:

| Artifact | Mount | Type |
|----------|-------|------|
| `knowledge_cloud/world_lore.json` | `/mnt/rom/world_lore` | ROM |
| `knowledge_cloud/evolution.json` | `/mnt/rom/evolution` | ROM |
| `knowledge_cloud/transitions.json` | `/mnt/params/transitions` | PARAMETER_DISK |
| `knowledge_cloud/chaining_patterns.json` | `/mnt/params/chaining_patterns` | PARAMETER_DISK |
| `knowledge_cloud/learned_transitions.json` | `/mnt/params/learned_transitions` | PARAMETER_DISK |
| `models/swarm_embedder.pkl` | `/mnt/params/swarm_embedder` | PARAMETER_DISK |
| `faiss.index` | `/mnt/corpus/faiss` | GROUNDING_CORPUS |
| `faiss_metadata.json` | `/mnt/provenance/faiss_metadata` | SOURCE_PROVENANCE |
| `knowledge.kndb` | `/mnt/rom/knowledge_nodes` | ROM |
| `knowledge.kndb.meta.db` | `/mnt/provenance/kndb_metadata` | SOURCE_PROVENANCE |
| `knowledge.meta.db` | `/mnt/provenance/knowledge_metadata` | SOURCE_PROVENANCE |
| volatile hot-context cache | `/mnt/cache/hot_context` | CACHE_SEED |
| volatile memory writeback | `/mnt/mem/writeback` | WRITEBACK_MEMORY |

`CHALMemoryController` attempts this manifest-backed boot before falling back to legacy default mounts. Failed integrity checks deactivate the affected mount and set trust to `0.0`; strict boot mode raises immediately.

The cache and writeback mounts are CHAL boundaries rather than generated Knowledge Cloud files. They are always marked `volatile=true` and `artifact_backed=false`, so cold-start validation can verify the ROM/parameter/corpus/provenance partitions without encouraging agents to commit runtime cache or memory artifacts.

### Core CHAL Interface Metadata

The legacy mount-controller records in `packages/core/chal/interfaces.py` now carry the same minimum scheduling metadata expected by the Synthesus 5 frame contract:

| Record | Trace field | Budget field |
|--------|-------------|--------------|
| `TelemetryRecord` | `trace_id` | `budgets` |
| `ModuleMessage` | `trace_id` | `budgets` |
| `Checkpoint` | `trace_id` | `budgets` |
| `CognitiveTask` | `trace_id` | `budgets` seeded from `budget_ms` |
| `ExecutionPlan` | `trace_id` | aggregate `budgets` from child tasks |

`CHALMemoryController` emits telemetry with explicit latency budgets for mounted lookups, cache hits, degraded states, and runtime fallback. This keeps Knowledge Cloud hardware traces compatible with PPBRS firmware, hypervisor, and future replay/debug consumers without changing mount paths or public query response envelopes.

### Cold-Start Bundle Gate

Phase 10 release readiness now has an explicit cold-start integrity gate:

```bash
python tools/validate_knowledge_cold_start.py --root /home/workspace/synthesus-knowledge-cloud/artifacts
```

The command boots the Knowledge Cloud artifact manifest through `KnowledgeCloudMountTable` with strict SHA-256 and byte-size validation, then requires these active CHAL mounts before passing:

- `/mnt/rom/world_lore`
- `/mnt/params/transitions`
- `/mnt/params/chaining_patterns`
- `/mnt/params/learned_transitions`
- `/mnt/params/swarm_embedder`
- `/mnt/corpus/faiss`
- `/mnt/provenance/faiss_metadata`
- `/mnt/rom/knowledge_nodes`
- `/mnt/provenance/kndb_metadata`
- `/mnt/provenance/knowledge_metadata`
- `/mnt/cache/hot_context`
- `/mnt/mem/writeback`

The tool also validates retrieval-semantic compatibility across the mounted FAISS corpus, FAISS metadata, and persisted swarm embedder. A bundle is not cold-start ready if `faiss.index` and `models/swarm_embedder.pkl` disagree on vector dimension, or if `faiss_metadata.json` does not contain the same record count as the FAISS index. This catches hash-valid but retrieval-incompatible mounted hardware before the runtime reaches golden-query health checks.

By default, the command uses `SYNTHESUS_KNOWLEDGE_ROOT` when set, then the companion `synthesus-knowledge-cloud/artifacts` checkout when present, and finally the runtime `data/` directory. It is also part of `tools/synthesus5_focused_suite.py`, so the source-only Synthesus 5 release gate now fails if the mounted Knowledge Cloud bundle cannot cold boot.

## Synthesus 5 Hot-Context Cache

`CHALMemoryController` now keeps a bounded L1 hot-context cache in front of mounted Knowledge Cloud ROM lookups. Cache keys normalize query whitespace/case and include the trust budget, so repeated local questions can be served from the CHAL controller without re-entering the KnowledgeCloud backend while still preserving the original mounted-source telemetry.

Telemetry distinguishes first-pass hardware lookup from cache locality:

- First lookup: `operation_id="kc_lookup"`, `cache_hit=False`, `metadata.hot_context=False`, and `metadata.mounts[]` lists the active ROM mount path, partition, namespace, locality, trust level, and latency profile.
- Repeat lookup: `operation_id="hot_context_hit"`, `cache_hit=True`, and `metadata.hot_context=True`.

Mounted lookup telemetry now also preserves artifact provenance on each active
mount when the mount came from a manifest-backed Knowledge Cloud artifact:
`relative_path`, `actual_size`, `actual_sha256`, and `integrity_ok`. The
Synthesus 5 hypervisor copies this KAL telemetry into
`debug.cognitive_hypervisor.knowledge_provenance` for grounded `mode="chal"`
responses, so final response metadata can show which mounted hardware supplied
context without changing the stable `QueryResponse` envelope.

The cache is volatile and source-only: it does not write generated artifacts into `data/`, the standalone Knowledge Cloud repo, or the public artifact mirror. Runtime/debug surfaces can inspect it with `get_hot_context_stats()` and clear it with `clear_hot_context()`.

Validation:

```bash
python -m py_compile packages/knowledge/mount_table.py packages/knowledge/kal_adapter.py tests/test_knowledge_mount_table.py
PYTHONPATH=/home/workspace/Synthesus_4.0/packages:/home/workspace/Synthesus_4.0/packages/core:/home/workspace/Synthesus_4.0/packages/knowledge python -m pytest -q tests/test_knowledge_mount_table.py tests/test_kal.py
```

## Usage

```python
from kn import KnowledgeNetwork, SemanticIndexer, EntityLinker, GraphConnector
from kn.node import NodeType, KNode, PersonNode, PlaceNode, Edge, EdgeType

# Create network
kn = KnowledgeNetwork(index_path="data/kn_index.json", graph_path="data/knowledge_graph.pkl")

# Register typed nodes
kn.register_node(PersonNode(id="gorn", display_name="Gorn", content="A merchant."))
kn.register_node(PlaceNode(id="tavern", display_name="Riverside Tavern", content="A lively inn."))

# Connect them
kn.add_edge("gorn", "tavern", EdgeType.LOCATED_AT, weight=0.9, bidirectional=True)

# Search
results = kn.search("merchant", top_k=5)
for node, score, reason in results:
    print(f"  [{score:.2f}] {node.display_name}: {reason}")

# Context retrieval (subgraph)
ctx = kn.get_context("gorn", depth=2)
print(f"Context for gorn: {ctx['nodes'].keys()}")

# Semantic search
indexer = SemanticIndexer(kn=kn)
indexer.index_nodes(kn.list_nodes())
semantic = indexer.search("inn by the river", top_k=3)
```

## Performance

| Operation | Latency |
|-----------|---------|
| Embedding inference (SwarmEmbedder) | **<1ms** per query |
| FAISS search (top-10, 200K vectors) | **<5ms** |
| KN keyword search (1000 nodes) | **<2ms** |
| Entity linking (cached) | **<0.1ms** |
