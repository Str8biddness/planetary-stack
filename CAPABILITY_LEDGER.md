# CAPABILITY_LEDGER.md — Synthesus runtime package audit

| Field | Value |
|-------|-------|
| **Branch** | `feat/module-audit` |
| **Date** | 2026-07-11 |
| **Method** | Real `importlib` probes + AST source scan under `runtime/packages/` |
| **Python** | `~/synthesus/.venv/bin/python` |

**Legend**

| Status | Meaning |
|--------|---------|
| **REAL** | Importable; non-trivial implementation (logic/functions present) |
| **STUB** | Empty, `class X: pass`, or placeholder only |
| **BROKEN** | Import/syntax failure (now fixed if listed under Fixes) |
| **BLOCKED** | Known non-trivial gap — do not fake |

---

## Package summary

| Package | Verdict | Notes |
|---------|---------|-------|
| `core/` | **REAL** (with STUB islands) | CHAL hypervisor, hemisphere bridge, conscious state real; `core/ml/*` stubs |
| `reasoning/` | **REAL** | Intent/sentiment/emotion/behavior, image_service, chal firmware |
| `knowledge/` | **REAL** | RAG, provenance, feedback verification, cloud_sync, drive |
| `api/` | **REAL** | production_server, security_router (Dict/Any fixed on main) |
| `kernel/` | **REAL** | bridge.py + C++ (build on `feat/native-kernel`) |
| `foreman/` | **REAL** | privilege_model, bridge, executor (human-gated) |
| `swarm/` | **REAL** | persona-clone swarm (one base + deltas); Firecracker local BLOCKED |
| `aivm/` | **MIXED** | Package imports; many empty `__init__`s; devices/base is stub |
| `organs/` | **TS/REAL surface** | TypeScript organ registry (not Python-import audited) |
| `frontend/` | **TS/REAL surface** | Vite UI (not Python-import audited) |
| `characters/` | **DATA** | Character assets |

---

## Import probes (pasted evidence)

```
OK  core.conscious_state                          REAL
OK  core.hemisphere_bridge                        REAL
OK  core.chal.hypervisor                          REAL
OK  core.chal.quad_brain                          REAL
OK  core.chal.memory_writeback                    REAL
OK  core.chal.devices.llm_device                  REAL
OK  core.ml.intent_classifier                     import OK but SOURCE STUB (class pass)
OK  core.ml.sentiment_analyzer                    import OK but SOURCE STUB (class pass)
OK  reasoning.intent_classifier                   REAL  (production path)
OK  reasoning.sentiment_analyzer                  REAL  (production path)
OK  reasoning.emotion_detector                    REAL
OK  reasoning.image_service                       REAL
OK  reasoning.chal                                REAL
OK  knowledge.rag_pipeline                        REAL
OK  knowledge.memory_provenance                   REAL
OK  knowledge.feedback_verification               REAL
OK  knowledge.swarm_embedder                      REAL
OK  knowledge.cloud_sync                          REAL
OK  api.schemas                                   REAL
OK  api.security_router                           REAL
OK  kernel.bridge                                 REAL
OK  foreman.privilege_model                       REAL
OK  foreman.bridge                                REAL
OK  swarm.registry / scheduler / arbiter          REAL
OK  swarm.envelope_firecracker                    REAL (raises BLOCKED on local)
OK  aivm                                          REAL (package init)
```

**Source scan (class `pass` stubs):**

```
STUB class_pass_only  runtime/packages/core/ml/intent_classifier.py
STUB class_pass_only  runtime/packages/core/ml/sentiment_analyzer.py
STUB class_pass_only  runtime/packages/core/ml/emotion_detector.py
STUB class_pass_only  runtime/packages/core/ml/behavior_predictor.py
STUB class_pass_only  runtime/packages/core/ml/dialogue_ranker.py
STUB class_pass_only  runtime/packages/core/ml/loot_balancer.py
STUB class_pass_only  runtime/packages/core/ml/pattern_lm.py
STUB class_pass_only  runtime/packages/aivm/devices/base.py
```

**Known shadowing (documented):**

| Shadow path | Real path | Used by production_server? |
|-------------|-----------|----------------------------|
| `core/ml/intent_classifier.py` (`class IntentClassifier: pass`) | `reasoning/intent_classifier.py` | **reasoning** ✓ |
| `core/ml/sentiment_analyzer.py` (pass) | `reasoning/sentiment_analyzer.py` | **reasoning** ✓ |
| `core/ml/emotion_detector.py` (pass) | `reasoning/emotion_detector.py` | **reasoning** ✓ |
| `core/ml/behavior_predictor.py` (pass) | `reasoning/behavior_predictor.py` | **reasoning** ✓ |
| `core/ml/loot_balancer.py` (pass) | `core/loot_balancer.py` (REAL, 150 lines) | was wrongly importing `ml.*` — **fixed on this branch** |
| `core/ml/dialogue_ranker.py` (pass) | `core/dialogue_ranker.py` (REAL, 209 lines) | was wrongly importing `ml.*` — **fixed on this branch** |

---

## Trivial fixes on this branch (with proof intent)

1. **`core/memory/__init__.py`** — trailing garbage path broke AST parse → cleaned.
2. **`core/unpc_engine/__init__.py`** — broken quotes in `__all__` / concatenated source → fixed imports.
3. **`api/production_server.py`** — import `LootBalancer`/`DialogueRanker` from real `core/` modules first, not `ml/` stubs.

**Proof (re-import after fix):**

```
import core.memory          # OK
import core.unpc_engine     # OK
from loot_balancer import LootBalancer   # REAL
from dialogue_ranker import DialogueRanker  # REAL
assert LootBalancer.__doc__ and 'Balances' in (LootBalancer.__doc__ or '')
assert not (inspect.getsource(LootBalancer).strip().endswith('pass'))
```

---

## BLOCKED / non-trivial (honest — not faked)

| Item | Status | Reason |
|------|--------|--------|
| `core/ml/*` pass stubs | **STUB** | Intentionally empty stand-ins; real logic lives under `reasoning/` or `core/*.py`. Do not fill with fake bodies. |
| `aivm/devices/*` skeleton | **STUB/partial** | `devices/base.py` is pass-only; full device isolation not production-wired here. |
| `swarm` Firecracker local | **BLOCKED by design** | `FirecrackerLocalBlockedError` on single-GPU local (HOSTED-only). |
| Kernel pybind vs IPC API | **Documented mismatch** | pybind exports EmulEngine/Geometric*; IPC `zo_kernel` is the runtime path. Fixed/wired on `feat/native-kernel`. |
| Full organs/frontend TS audit | **OUT OF SCOPE** | Not Python-importable; ledger notes surface only. |
| Empty package `__init__.py` files | **STUB/empty** | Harmless namespace markers (knowledge, aivm, foreman). |

---

## AST inventory (approx.)

| Class | Count |
|-------|------:|
| REAL `.py` modules | ~291 |
| STUB (empty / pass-only / bare init) | ~22 |
| BROKEN syntax (before fix) | 2 (`memory`, `unpc_engine` inits) |
| BROKEN after fix | 0 (verified import) |

---

## How to re-run this audit

```bash
cd ~/synthesus
export PYTHONPATH=runtime/packages:runtime/packages/core:runtime/packages/knowledge:runtime/packages/reasoning:runtime/packages/api:runtime/packages/kernel:runtime/packages/foreman:runtime/packages/swarm:runtime
~/synthesus/.venv/bin/python -c "import core.chal.hypervisor, knowledge.rag_pipeline, swarm.registry, kernel.bridge; print('ok')"
```
