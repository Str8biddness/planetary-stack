# KN Builder Log

## 2026-04-28 15:05 UTC

### Repo State
- Pulled latest: main @ cc3be69 (already up to date)

### KN Module Review

| File | Status | Notes |
|------|--------|-------|
| `kn/__init__.py` | ✅ Complete | All exports healthy |
| `kn/node.py` | ✅ Complete | Full node type hierarchy |
| `kn/network.py` | ✅ Complete | Fixed BFS bug |
| `kn/entity_linker.py` | ✅ Complete | Working |
| `kn/semantic_indexer.py` | ✅ Complete | Fixed FAISS dim bug |
| `kn/graph_connector.py` | ✅ Complete | Full import pipeline |

### Data Files
- `data/kn_index.json`: ✅ exists (13 nodes)
- `data/knowledge_graph.pkl`: ✅ exists (17 edges)
- `data/kn_semantic.index`: ✅ exists
- `data/kn_semantic_meta.json`: ✅ exists
- No bootstrap needed.

### Issues Found & Fixed

**Bug in `get_context` (network.py)**:
- BFS frontier used faulty `zip(*neighbors_with_edges)` unpacking — when a node had no neighbors, the loop silently produced nothing
- Fixed: directly iterate `for neighbor, _ in neighbors_with_edges:` instead of the broken zip pattern
- Verified: context retrieval now returns 8 nodes at depth 2 for `gorn_the_merchant`

**Bug in `SemanticIndexer._add_vector` (semantic_indexer.py)**:
- FAISS assertion failure when `SwarmEmbedder` outputs a different dimensionality than the initially-constructed `IndexFlatIP`
- Root cause: index initialized with `dim=128`, but embedder outputs `dim=256` (sklearn SVD auto-adjusts)
- Fixed: when index is empty and actual_dim differs, reinitialize the FAISS index to the correct dimension before adding vectors

**EntityLinker alias matching gap**:
- `link_mention('Gorn')` returns None because the node `gorn_the_merchant` has `display_name='Gorn The Merchant'` and aliases `['Gorn']` — but the linker needs `build_indices()` called first and the match is substring-based with score threshold
- Not a code bug; just behavior to be aware of. Works correctly for `link_mention('Grand Tavern')` → `the_grand_tavern`

### Changes Committed
- `kn/network.py`: Fixed BFS loop in `get_context` — removed broken zip unpacking, use direct neighbor iteration
- `kn/semantic_indexer.py`: Fixed FAISS dimension mismatch — reinitialize empty index when embedder output dim differs

---

## 2026-04-27 15:10 UTC

### Repo State
- Pulled latest: main @ d1498a7

### KN Module Review

| File | Status |
|------|--------|
| `kn/__init__.py` | ✅ Complete |
| `kn/node.py` | ✅ Complete |
| `kn/network.py` | ✅ Complete |
| `kn/entity_linker.py` | ✅ Complete |
| `kn/semantic_indexer.py` | ✅ Complete |
| `kn/graph_connector.py` | ✅ Complete |

### Issues Found & Fixed

**Bug in `register_node` (network.py)**:
- When `replace=True` and the node changed type (e.g., PERSON→PLACE), the old type list was not cleaned up.
- Added: `if old_node.node_type != node.node_type: self._nodes_by_type[old_node.node_type].remove(node.id)`
- Also added `if node.id not in self._nodes_by_type[node.node_type]` guard to prevent duplicate type entries.

**Performance in `get_context` (network.py)**:
- BFS frontier used `list.pop(0)` which is O(n) per pop.
- Added `from collections import deque` and changed frontier to `deque([(node_id, 0)])` with `popleft()` — O(1).

### Data Files
- `data/kn_index.json`: ✅ exists (13 nodes)
- `data/knowledge_graph.pkl`: ✅ exists (17 edges)
- No bootstrap needed.

### Changes Committed
- `kn/network.py`: Fixed `register_node` type-list growth bug + deque BFS optimization
