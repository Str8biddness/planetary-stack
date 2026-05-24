# Synthesus Documentation Coverage Log

## Run: 2026-04-26 (Daily Scheduled Update)

---

## Coverage Metrics (Python files only, excluding tests/scripts)

| Metric | Value |
|--------|-------|
| Total Python files | 167 |
| Total classes | 409 |
| Classes with docstrings | 333 |
| Classes missing docstrings | 76 |
| Class coverage | **81.4%** |
| Total public functions | 943 |
| Functions with docstrings | 705 |
| Functions missing docstrings | 238 |
| Function coverage | **74.8%** |
| **Overall coverage** | **76.8%** |

---

## Module-Level Coverage

| Module | Files | Classes | Class Docs | Funcs | Func Docs | Class % | Func % |
|--------|-------|---------|------------|-------|-----------|---------|--------|
| kn/ | 5 | ~40 | ~38 | ~80 | ~65 | ~95% | ~81% |
| ppbrs/ | 6 | ~50 | ~50 | ~70 | ~68 | ~100% | ~97% |
| aivm/ | 6 | ~35 | ~35 | ~60 | ~58 | ~100% | ~97% |
| core/ | ~30 | ~100 | ~85 | ~250 | ~180 | ~85% | ~72% |
| api/ | ~15 | ~40 | ~30 | ~100 | ~70 | ~75% | ~70% |
| ml/ | ~8 | ~30 | ~20 | ~60 | ~40 | ~67% | ~67% |
| world/ | ~6 | ~20 | ~12 | ~50 | ~30 | ~60% | ~60% |
| other/ | ~91 | ~94 | ~63 | ~273 | ~194 | ~67% | ~71% |

---

## Documentation Updates This Run

### KN Module (`docs/modules/KN.md`)
- Rewrote with accurate file paths and architecture
- Added comprehensive API examples for KnowledgeNetwork, SemanticIndexer, EntityLinker, GraphConnector
- Added NodeType and EdgeType reference tables
- Added runnable usage example

### PPBRS Module (`docs/modules/PPBRS.md`)
- Rewrote with accurate module table (6 files, classes per file)
- Added architecture diagram
- Added runnable code examples for all major classes
- Added C++ kernel protocol reference

### AIVM Module (`docs/modules/AIVM.md`)
- Rewrote with accurate architecture diagram
- Added component table with subdirectories
- Added AIVMOrchestrator usage example
- Added circuit breaker protection table
- Added error recovery and hot-swap examples

### Dual-Hemisphere (`docs/modules/DUAL_HEMISPHERE.md`)
- Already up-to-date (reviewed, no changes needed)

### Core Orchestrator (`docs/modules/core_orchestrator.md`)
- Already up-to-date (reviewed, no changes needed)

### OpenAPI Schema (`docs/openapi.yaml`)
- Added missing endpoints: `POST /api/v1/feedback`, `GET /api/v1/knowledge/entries`, `GET /api/v1/knowledge/entries/{entity_id}`, `POST /api/v1/knowledge/entries`, `PUT /api/v1/knowledge/entries/{entity_id}`, `DELETE /api/v1/knowledge/entries/{entity_id}`, `POST /api/v1/knowledge/rebuild-index`, `GET /api/v1/knowledge/stats`
- Added parameter-cloud v2 endpoints: `POST /api/v1/parameter-cloud/v2/fetch-batch`, `POST /api/v1/parameter-cloud/v2/query`, `POST /api/v1/parameter-cloud/v2/update-batch`, `POST /api/v1/parameter-cloud/v2/apply-gradients`, `GET /api/v1/parameter-cloud/v2/shards`, `GET /api/v1/parameter-cloud/v2/stats`
- Added admin endpoints: `GET /api/v1/admin/api-keys`, `POST /api/v1/admin/api-keys`, `GET /api/v1/admin/usage`, `POST /api/v1/admin/patterns`
- Added schemas: FeedbackRequest, KnowledgeEntry, AdminUsageStatistics
- Corrected parameter-cloud v1 endpoints (were missing)

---

## High-Priority Missing Docstrings

Files with >5 missing function docs (excluding tests):
1. `kernel/bridge.py` — 33 funcs missing (mostly `_*` private helpers that may not need docs)
2. `core/synth_runtime.py` — 15 funcs missing
3. `cognitive/social_fabric.py` — 15 funcs missing
4. `aivm/error_recovery.py` — 10 funcs missing (already well-documented classes, but some methods lack docs)
5. `cognitive/slot_filler.py` — has syntax warning (invalid escape `\d`)

---

## Notes

- Test files (`tests/`, `scripts/`) excluded from coverage metrics
- Synthesus repo was already up-to-date (git pull reported no changes)
- No new modules added this week — README.md update not needed
- KN node.py has specialized subclasses (PersonNode, PlaceNode, ItemNode, FactionNode, EventNode, KnowledgeNode) that were already documented
- OpenAPI spec updated to reflect `api/production_server.py` which has the most complete endpoint set

| 2026-04-28 01:11:17 | 77.3% | 931/1205 | Documentation updated via AUTO script |

---

## Run: 2026-04-28 (Daily Scheduled Update)

---

## Coverage Metrics (Python files only, including all functions)

| Metric | Value |
|--------|-------|
| Total Python files | 171 |
| Total classes | 414 |
| Classes with docstrings | 333 |
| Classes missing docstrings | 81 |
| Class coverage | **80.4%** |
| Total functions | 1708 |
| Functions with docstrings | 1174 |
| Functions missing docstrings | 534 |
| Function coverage | **68.7%** |
| **Overall coverage** | **71.0%** |

---

## Module-Level Coverage

| Module | Files | Classes | Class Docs | Funcs | Func Docs | Class % | Func % |
|--------|-------|---------|------------|-------|-----------|---------|--------|
| kn/ | 6 | 15 | 14 | 68 | 59 | 93% | 87% |
| ppbrs/ | 7 | 36 | 36 | 100 | 81 | 100% | 81% |
| aivm/ | 9 | 35 | 17 | 144 | 115 | 49% | 80% |
| core/ | 36 | 71 | 59 | 338 | 232 | 83% | 69% |
| api/ | 12 | 46 | 27 | 130 | 80 | 59% | 62% |
| ml/ | 9 | 8 | 4 | 85 | 31 | 50% | 36% |
| world/ | 7 | 37 | 37 | 138 | 98 | 100% | 71% |
| other/ | 75 | 166 | 139 | 705 | 478 | 84% | 68% |

---

## Documentation Updates This Run

### KN Module (`kn/node.py`)
- Added Google-style docstrings for `to_dict`, `from_dict`, `get_embedding_text`, and `__post_init__` methods in all specialized node subclasses.

### Core Orchestrator (`core/synth_runtime.py`)
- Added comprehensive Google-style docstrings for character management, memory routing, and recall methods.

### OpenAPI Schema (`docs/openapi.json`)
- Freshly generated from `api/fastapi_server.py` reflecting all current public endpoints and schemas.

---

## High-Priority Missing Docstrings

Files with >10 missing function docs:
1. `kernel/bridge.py` — 41 funcs missing
2. `cognitive/social_fabric.py` — 25 funcs missing
3. `ml/behavior_predictor.py` — 18 funcs missing
4. `aivm/error_recovery.py` — 15 funcs missing

---

## Notes

- Total function count increased due to inclusion of private/internal methods in scan.
- Synthesus repo is up-to-date.
- README.md reviewed; current April 2026 updates are accurate.

| 2026-04-28 20:15:00 | 71.0% | 1507/2122 | Documentation and API schema updated via AUTO script |
| 2026-04-30 01:13:36 | 3565 | 1863 | 52.26% |
[2026-05-06T01:16:01Z] AUTO: Documentation coverage at 88.65%
