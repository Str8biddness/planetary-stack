# AGENT_LOG.md — session continuity for memory-provenance build

## 2026-07-13 — feat/ultra-valuable-import: pull real Ultra value (no engine regress)

### What
- Inventory found Ultra origin/main is an **ancestor** of launch; engines already superseded.
- Imported **valuable** non-regressive assets only:
  - `benchmarks/fixtures/ultra_si_proof/` — real SI PNG + early larynx WAV
  - `runtime/tests/fixtures/organ_smoke/` — small committed slices of organ training JSON
  - `scripts/import_ultra_synthetic.sh` — full dumps to gitignored `packages/core/synthetic_data/`
  - `docs/ULTRA_ARCHIVE.md` + AGENTS.md pointer
  - `runtime/tests/test_organism_conversation_smoke.py`

### Explicitly not imported
- Thin Ultra `vsa_pipeline_image` (would downgrade public image_service)
- Multi-cloud SDS / parameter-cloud-required paths as product default

### Branch
`feat/ultra-valuable-import` — Claude review; do not merge without check.

## 2026-07-13 — feat/scale-si-hybrid: merge main + Claude review fixes

### What
- Merged `origin/main` (ingest-flush + qa-sev1 wow) into scale branch; both preserved.
- FIX 1: `_cache_key` includes `enhance` + `enhance_strength` (no wrong-image cache hits).
- FIX 2: `enhance=realesrgan` unavailable → **503** (same honesty as piper); si_detail/si_upscale2 stay 200.

### Branch
`feat/scale-si-hybrid` — do not merge without Claude re-review.

## 2026-07-12 — feat/scale-si-hybrid: scale image + voice (no mocks)

### Research brief → shipped tiers
**Image (Q1)**
- Pure SI construction remains default stock/master (diagrams moat intact).
- `enhance=si_detail` — classical multi-scale unsharp (always-on, deterministic).
- `enhance=si_upscale2` — Lanczos 2× + detail (always-on).
- `enhance=realesrgan` — optional local ONNX; **loud 503** if model/ORT missing.
- Capabilities card documents honest photoreal ceiling.

**Voice (Q2)**
- Formant path: Fujisaki-lite F0 + anticipatory coarticulation + raised-cosine diphone joins.
- `backend=formant` default; `backend=piper` opt-in — **503** if missing.

### Branch
`feat/scale-si-hybrid`

## 2026-07-12 — fix/qa-sev1 wow: full QA close + instrument front-end

### Fixed
- File explorer: real home tree with `path`, preview pane, GET `/api/ide/read` (path-contained)
- Drive: dual `/api/drive/*` + `/api/v1/drive/*` aliases; local text paste ingest
- Dock: labeled buttons + active glow; boot opens Chat+Vitals once
- Login/chat/explorer instrument chrome; boot flash; offline oath on lock screen

### Branch
`fix/qa-sev1` (merged to main)

## 2026-07-12 — fix/qa-sev1: QA punch-list SEV-1/2

### What (from Full QA Report July 12)
1. **BUG-1 dock clip**: full-width wrap dock — 📡⚙️🧠 hit-testable
2. **BUG-2 image HTTP 500**: shell `image_proxy` restored real POST
3. **BUG-3 chat**: reachable after dock fix; `/api/chat` on shell
4. **BUG-4 voice audio**: `load()` / `canplay` then play
5. **BUG-5 foreman poll**: only while `#win-foreman` open

### Branch
`fix/qa-sev1` (merged to main)


## 2026-07-11 — SW-1..SW-5 Persona-Clone Expert Swarm

### What
New package `runtime/packages/swarm/` (disjoint from `foreman/`):
- **SW-1** `registry.py` — Expert registry (persona + system_prompt + namespace + optional adapter_ref). Deltas only.
- **SW-2** `scheduler.py` + `model_client.py` — ONE shared Ollama base model; fan-out expert system prompts; missing expert/adapter → degraded, no fabricated text.
- **SW-3** `arbiter.py` — merge via `QuadBrainOrchestrator`; SwarmAnswer.sources carry C-001 verification tiers.
- **SW-4** `adapters/` — LoRA/persona-delta DATA validation; refuse executables; base-compat check.
- **SW-5** `envelope_firecracker.py` — loud BLOCKED/NotImplementedError on single-GPU local host.

### Why
GPU-bound inference: never N model copies. Isolation between cooperating experts is forbidden on one GPU.

### Proof
`pytest runtime/tests/test_persona_clone_swarm.py` → 11 passed (real Ollama llama3.2:3b).

### Pre-review hardening (same branch)
- Honest v1 boundary: `adapter_applied=False`, `adapter_status=persona_prompt_delta_only|validated_not_applied`.
- Arbiter prefers expert seed prose over template CGPU surfaces (`swarm: [expert:…]`).
- Export `SwarmRuntime` + `README.md` quick start.
- Stricter persona-marker tests; all `model_id`s must be the single base.

### Branch
`feat/persona-clone-swarm` — commit per section; do not merge without review.

---

## 2026-07-11 — REQUEST CHANGES fix (reviewer anti-collapse hole)

### Coordination note — C-001 unfreeze (Law #4 security exception)
- **Spec rev:** MEMORY_BLUEPRINT.md r1 → **r2**
- **Why unfreeze frozen contract:** Reviewer found `gate()` trusted a caller-supplied
  `verification` tier, so `gate({provenance:grounded_cited, verification:2})` returned
  VERIFIED. Latent (writeback re-derives) but contract-level hole.
- **Fix:** `gate()` always re-derives via `classify(provenance)`; caller tier ignored.
  Same for `resolve_legacy_metadata` / `annotate_metadata` authority.

### Blocker fix — C-004 human proof (invert polarity)
- **Hole:** `_event_is_external_confirm` only rejected self-declared bots. Omitting
  markers + `{action:"confirm"}` looked like a human confirm. API-key auth is not
  human auth → agents with the key could forge VERIFIED (model collapse path).
- **Fix (Foreman allow-list lesson):** deny-by-default positive human proof:
  1. `actor_kind == "human"`
  2. `channel ∈ HUMAN_CHANNELS` allow-list
  3. `confirmed_by` acceptable human identity (blocks `auth:…`, agents, placeholders)
  4. **Server-issued single-use `human_attestation`** minted only after
     `X-Synthesus-Human-Session` matches `SYNTHESUS_HUMAN_SESSION_SECRET`
- **C-005:** `POST /api/v1/human/attestation` for minting; `/api/v1/feedback` never
  invents human proof from the API key; passes client fields through only.
- **Reviewer probe now fails:**
  `verify_human_confirm_proof({action:"confirm", answer_id:"a1"}) → False
  (missing_human_actor_kind)`

### Files touched this fix
- `runtime/packages/knowledge/memory_provenance.py` (C-001 r2)
- `runtime/packages/knowledge/feedback_verification.py` (C-004)
- `runtime/packages/api/production_server.py` (C-005)
- `runtime/tests/test_memory_provenance.py` (C-006)
- `MEMORY_BLUEPRINT.md` (r2)
- this log

---

## 2026-07-11 — feat/memory-provenance (build agent)

### Mission
Implement provenance + verification-tagged memory model so crystallized Mc grows
only from verified external signal. Anti-collapse invariant: no path lets
`LLM_GENERATION` become `VERIFIED` or long-term ground truth without an external
event.

### C-001 — Frozen contract
- **What:** Added `runtime/packages/knowledge/memory_provenance.py` with
  `Provenance`, `Verification`, `VERIFICATION_WEIGHT`, `classify()`, `gate()`,
  plus helpers `annotate_metadata`, `resolve_legacy_metadata`, `weight_for`.
- **Why:** Center-line contract every consumer imports; gate is the anti-collapse
  valve (`LLM_GENERATION` → always `(False, UNVERIFIED)` even if tier is forged).
- **Proof:** unit smoke + `tests/test_memory_provenance.py` C-001 cases green.

### C-002 — Storage + retrieval (`rag_pipeline.py`)
- **What:** `add_patterns` / `append_patterns` enrich metadata with provenance
  fields; `ingest_documents` tags `USER_DOCUMENT`/`VERIFIED`; `retrieve()` ranks
  by `similarity × VERIFICATION_WEIGHT` and returns `verification` on each source.
  Legacy metadata loads via `resolve_legacy_metadata` (user_docs→VERIFIED; else GROUNDED).
- **Why:** Verified knowledge must out-rank drafts at equal similarity.

### C-003 — Crystallization gate (`memory_writeback.py`)
- **What:** `classify_writeback_provenance` + `gate()` before any long-term store.
  Grounded+cited traces → `GROUNDED_CITED` with `provenance_refs`; raw/trace-only
  → `LLM_GENERATION` → rejected (`session_only`, reason
  `gate_rejected_llm_generation_or_unverified`). CHAL ref list preserved under
  `chal_provenance`.
- **Why:** Stop ungrounded LLM answers from crystallizing into Mc.

### C-004 — Feedback bridge (`feedback_verification.py`)
- **What:** `upgrade_from_feedback(event, items=...)` upgrades a linked item to
  `USER_CONFIRMED`/`VERIFIED` only for real external confirms/corrections.
  Self-triggered / model-origin events refused. Corrections rewrite content as VERIFIED.
- **Why:** Sole promotion path from draft → verified is the user.

### C-005 — API wiring (`production_server.py`)
- **What:** `_apply_chal_memory_writeback` passes full `trace` into writeback (gate).
  `/api/v1/feedback` calls C-004 and returns `verification_upgrade`. Query sources
  already surface tiers from C-002 retrieve. Health endpoint unchanged.
- **Why:** End-to-end external signal path.

### C-006 — Adversarial tests (`test_memory_provenance.py`)
- **What:** Tests (a)–(e) plus multi-vector adversarial summary that forges tier,
  launders via crystallized target, self-triggers feedback, etc. — all fail closed.
- **Collateral:** Updated `test_chal_memory_policy.py` /
  `test_chal_api_memory_writeback.py` expectations for C-001 metadata shape and
  gate rejection of ungrounded critic-only writebacks (required by anti-collapse).

### Anti-collapse statement (reviewer attempt)
Tried and failed to crystallize a raw generation as a fact by:
1. Forging `verification=2` on `provenance=llm_generation` through `gate()` → forced UNVERIFIED, rejected.
2. `annotate_metadata(..., verification=VERIFIED)` on LLM_GENERATION → forced UNVERIFIED.
3. Writeback with only `trace://` self-ref / critic-only provenance → gate rejects, zero store records.
4. `target_memory_type=crystallized` laundering → still gate-rejected.
5. Feedback with `self_triggered=True` or `origin=llm` → upgrade refused; tier stays UNVERIFIED.
6. Low rating (2) → no upgrade.

The only successful path to VERIFIED was a real external confirm/correction event
via `upgrade_from_feedback`, which sets `USER_CONFIRMED`.

### Test commands (from `runtime/` with venv)
```
python -m pytest tests/test_memory_provenance.py tests/test_chal_memory_policy.py tests/test_chal_api_memory_writeback.py -q
```
All green at handoff (35 passed when API deps present; 2 skipped without fastapi).

## 2026-07-11 — Multi-phase autonomous finish (native-kernel / polish / module-audit)

### Phase 1 feat/native-kernel — DONE
- Compile fixes: resonance_observer includes, geometric_optics pybind, GeometricEngine shared_ptr, voice_vcu memory, test_emul link.
- IPC: main.cpp JSON query parse + dual keys; bridge.py IPC payload; hemisphere_bridge resolves `kernel/build/zo_kernel`, KernelBridge auto-IPC.
- Proof: `make` builds `zo_kernel` + `_synthesus_kernel*.so`; stdin IPC JSON response; log `KernelBridge initialized in ipc mode`; left query `source=cpp_kernel`.

### Phase 2 feat/polish — DONE
- `scikit-learn==1.8.0` pin in runtime/requirements.txt; retrieve without InconsistentVersionWarning.
- llm_device DEFAULT_SYSTEM_PROMPT VERBATIM codes; live Ollama answered `ZXQ-7741-BETA`.
- production_server startup RAG embedder warm-up; cold ingest 4.66s vs after-warm ~0s.

### Phase 3 feat/module-audit — DONE
- CAPABILITY_LEDGER.md: REAL/STUB/BROKEN with import evidence.
- Fixed: core/memory/__init__.py garbage, unpc_engine/__init__.py syntax, production_server loot/dialogue imports use real core modules not ml stubs.
- Honest stubs left as STUB (core/ml pass classes).

Do NOT merge — Claude reviews.

## 2026-07-11 — feat/launch-smoke (final pre-QC pass)

Merged into this branch: native-kernel, polish, module-audit.

Additional launch polish:
- production_server: HemisphereBridge() uses package kernel path resolver (not PROJ_ROOT/zo_kernel)
- install.sh: SYNTHESUS_HUMAN_SESSION_SECRET + scikit-learn==1.8.0 pin in pip critical list
- core/ml/*: re-export real reasoning/core modules (no pass stubs)
- tools/redeploy_install.sh: safe rsync preserve env/venv/data
- tools/launch_smoke.sh: real HTTP/kernel/sklearn checks
- LAUNCH_CHECKLIST.md + kernel/README.md (IPC vs pybind honesty)

Proof: ml re-exports → reasoning/core real files; zo_kernel IPC ok;
redeploy generates human secret; smoke pass=4 offline (health fail until runtime up).

## 2026-07-11 — feat/launch-smoke (finish-rest pass, no CNC/swarm)

### Mission
Knock out remaining pre-QC launch gaps. Explicitly **did not** start CNC/G-code or new swarm product features.

### What changed
- Fixed `core/ml/dialogue_ranker.py` + `core/ml/loot_balancer.py` re-exports (were `from dialogue_ranker` without package path → ModuleNotFoundError outside install PYTHONPATH). Now try `core.*` then relative `..*`.
- `production_server.py` prefers `from core.loot_balancer` / `core.dialogue_ranker` first.
- `CAPABILITY_LEDGER.md` updated: `core/ml/*` documented as RE-EXPORT of real targets, not pass stubs.
- Live runtime proof + full `tools/launch_smoke.sh`.

### Verified (pasted real)
```
pytest tests/test_memory_provenance.py tests/test_chal_memory_policy.py -q
→ 38 passed

./tools/launch_smoke.sh  (runtime up, API_KEY=dev-key-change-me)
  PASS  health HTTP 200 (ml_models_loaded loot=true dialogue=true)
  PASS  query HTTP 200 body=... source=cognitive_hypervisor ...
  PASS  feedback without human proof did not crystallize (HTTP 200)
  PASS  image HTTP 200 (bytes=7527)
  PASS  sklearn embedder (1.8.0 ok)
  PASS  zo_kernel IPC
  PASS  VERBATIM in llm_device
  PASS  install.sh human session secret
=== summary: pass=8 fail=0 skip=0 ===

Server log: KernelBridge initialized in ipc mode
  Hemisphere Bridge ready (kernel_bin=.../kernel/build/zo_kernel, KernelBridge mode=ipc)
```

### Already complete on branch (no further code)
- LM Studio local free / Pro gate cloud-only (`LOCAL_BACKENDS = ("ollama", "lmstudio")`)
- GPU autodetect in install.sh + tools/enable_gpu.sh (on main lineage)
- SYNTHESUS_FAST_MODE already in hypervisor on this branch
- Attestation UI, settings/tiers, voice backends already ancestors of launch-smoke

### Left off / do NOT
- Do **not** merge to main — Claude reviews `feat/launch-smoke`
- CNC/G-code: not started (user forbid)
- New swarm features: not started
- Remote Mint redeploy: still needs working SSH when user wants it

### Recommended next
1. Claude review + merge `feat/launch-smoke`
2. Redeploy install dir with `tools/redeploy_install.sh` on the box that ships
3. Optional: re-run smoke after redeploy with production API key

## 2026-07-12 — feat/image-roundout

### Mission
Optimize + scale SI image generation into a well-rounded illustration product
(not diffusion). No CNC/G-code, no new swarm features.

### What changed
- `runtime/packages/reasoning/vsa_pipeline_image.py`
  - Full SHAPES ↔ renderer parity (`house`, `star_top`, fire inner flame)
  - Multi-object layout packing (ground + sky slots, seed jitter)
  - Styles: `flat` | `soft` | `night`
  - Aspect ratio + float32 raster
  - Richer tree canopy (layered discs) + multi-blob clouds
- `runtime/packages/reasoning/image_service.py`
  - LRU PNG cache (prompt+res+style+seed+aspect), env `SYNTHESUS_IMAGE_CACHE_SIZE`
  - Forwards style/seed/aspect; reports `cache_hit`, dims, roles
- `runtime/packages/api/schemas.py` — `ImageRequest` / `ImageResponse`
- `runtime/packages/api/production_server.py` — validates request, returns full envelope
- `runtime/tests/test_image_roundout.py` — 9 golden/parity tests

### Verified (pasted)
```
pytest tests/test_image_roundout.py -v
→ 9 passed

python packages/reasoning/image_service.py
→ entities: house, tree, grass, sky, sun, star
→ PNG 43966 bytes; cache_hit second call: True
```

### Honest ceiling
Still SI procedural illustration (~26 vocab concepts), not photoreal.
Photoreal / local SD remains optional future tier with explicit labeling.

### Left off
- Desktop Image Studio UI (next if product wants it)
- Optional raw PNG URL response (base64 still default)
- C++ optics paint acceleration (measure first)

### Do NOT merge without Claude review.

## 2026-07-12 — feat/image-studio

### Mission
Take SI image gen further: Image Studio UI + relation-aware layout + vocab growth.
Built on feat/image-roundout. No CNC, no swarm, no diffusion claims.

### What changed
- `scene_composer.SHAPES`: +road/path, river/stream, fence, boat, person, building/tower/castle, flower, bird, bridge, bush
- `vsa_pipeline_image.py`: relation parser (left of / right of / beside / behind / in front of / above / under / on); paint paths for all new roles
- `image_service.py`: vocab_version `image-studio-v1`
- Desktop: `win-image` Studio UI (prompt, style, res, aspect, seed, preview, entity chips)
- `synthesus_native_shell.py`: `POST /api/v1/image` proxy → runtime
- Tests: 12 golden (relations + studio vocab)

### Verified
```
pytest tests/test_image_roundout.py -v
→ 12 passed

generate_image('a person left of a house ... bird ... flower')
→ real PNG; person+house entities present
```

### How to use
Dock 🎨 → SI Image Studio. Runtime must be on :5010 (shell proxies).

### Honest ceiling
Still SI illustration, not photoreal. Relations are binary phrase-based.

### Do NOT merge without Claude review.

## 2026-07-12 — feat/image-wow

### Mission
Push SI image gen toward product wow: atmosphere, disk cache, variations,
chat "draw this", Studio gallery/download. Still SI (not Midjourney photoreal) —
position for the huge illustration/local-privacy audience honestly.

### What changed
- `image_service.py`: disk cache `~/.cache/synthesus/image_cache`, detail high|standard,
  `generate_variations(n)`, vocab_version `image-wow-v1`
- `vsa_pipeline_image.py`: high-detail trees (limbs), haze, vignette, grain, contact shadows
- API: `detail`, `variations` on ImageRequest; multi-PNG envelope
- Desktop Studio: detail, ✦4× variations, Save, recent gallery
- Chat: `draw …` / `/draw …` / `imagine …` → SI image inline
- Shell proxy forwards detail + variations
- Tests: **13 passed**

### Positioning note (for review / mon)
SI path = local, deterministic, private, infinite res vector-style scenes.
Not a drop-in for photoreal Midjourney. Monetizable as: private studio +
"draw in chat" + no cloud GPU bill. Optional labeled AI tier later.

### Verified
```
pytest tests/test_image_roundout.py → 13 passed
```

### Do NOT merge without Claude review.

## 2026-07-12 — feat/image-camera (camera/TV ISP, not diffusion)

### Mission
Keep hammering image quality + scale. Path to *photo-real look* without
copying diffusion: **digital camera + smart-TV ISP math** on the SI scene graph.

### Thesis (aligned with research)
Diffusion invents content. Cameras/TVs invent *appearance* of a captured signal:
AE, white balance, bloom/glare, DOF, chromatic aberration, filmic tonemap,
local contrast (clarity), sensor noise, sRGB OETF, vignette.
Apply that stack to SI geometry → photographic finish, still pure SI content.

### What changed
- NEW `runtime/packages/reasoning/camera_isp.py` — full CPU ISP pipeline
- `render_doc(..., look=photo|cinema|vivid|tv|raw)`
- `image_service` / API / Studio / chat draw default toward `look=photo`
- Vocab: lake/pond/meadow, barn/cabin, forest/pine, lamp, car (primitive reuse)
- Tests: **14 passed** including `test_camera_isp_photo_look`

### Honest ceiling
- Photo *look* ≠ Midjourney inventing novel objects/faces
- Content ceiling still vocabulary; ISP is the finish, not the model
- Provenance: `engine=synthesus_vsa_geometric+camera_isp`, `isp.pipeline` listed

### Verified
```
pytest tests/test_image_roundout.py → 14 passed
camera_isp demo → /tmp/camera_isp_demo.png with ae/bloom/dof/filmic/...
```

### Do NOT merge without Claude review.

## 2026-07-12 — feat/image-cnc-paths (CNC form language)

### Mission
All-in: wire CNC path math into SI image construction. Not raw G-code UI —
the *math* (G1/G2/G3, offset, contour fill, multi-pass) builds form; camera ISP
still owns photo look.

### What changed
- NEW `runtime/packages/reasoning/cnc_paths.py`
  - Line/arc segments, polyline, house/tree/person/fence/boat/building/…
  - Discretize, tool-radius offset, multi-pass offsets
  - Raster stroke + closed fill with AA
  - Provenance sample as g-like ops (`G1 X…`, `G3 …`, `CLOSE`)
- `pattern_document` / `render_doc` `path_mode=True` (default)
- API/Studio/shell: `path_mode` toggle; engine string includes `cnc_paths`
- Tests: **15 passed**

### Stack (form → finish)
```
prompt → scene graph → CNC paths (form) → raster → camera ISP (look)
```

### Honest
- CNC = precision construction, not Midjourney content invention
- Users never type G-code; ops are internal + debug sample

### Verified
```
pytest tests/test_image_roundout.py → 15 passed
cnc_paths demo → /tmp/cnc_paths_demo.png
```

### Do NOT merge without Claude review.

## 2026-07-12 — feat/image-materials (materials + sky + CNC pocket)

### Mission
Continue image stack: surface response + atmospheric sky + deeper CNC multi-pass.

### What changed
- NEW `materials.py` — Lambertian + Schlick fresnel + roughness/metalness shading
- NEW `sky_model.py` — Preetham-lite analytical sky (zenith/horizon/aureole)
- `cnc_paths.paint_path` — multi-pass pocket fills + material shading
- `render_doc` bg uses sky model; ground uses material shade
- vocab_version `image-materials-v1`
- Tests: **16 passed**

### Stack
```
prompt → scene graph → CNC paths (form + pocket) → materials shade
       → sky model → camera ISP (look)
```

### Verified
```
pytest tests/test_image_roundout.py → 16 passed
```

### Do NOT merge without Claude review.

## 2026-07-12 — feat/image-depth-presets

### Mission
1) Cinematic scene presets  2) Per-object depth map + true DOF bokeh.
Also documents SI multi-axis opinion: real DOF only when Z is first-class.

### What changed
- NEW `scene_presets.py` — cottage_dawn, harbor_day, city_dusk, mountain_lake,
  night_village, orchard, bridge_crossing, tv_vivid_park
- NEW `depth_buffer.py` — per-object Z, z-test write, focus picker
- `camera_isp.depth_of_field` uses depth_map when present (`dof_z`)
- `render_doc` builds depth while painting paths; passes focus to ISP
- Studio preset buttons; API `preset` field; shell `/api/v1/image/presets`
- Tests: **17 passed**

### Verified
```
pytest tests/test_image_roundout.py → 17 passed
```

### Do NOT merge without Claude review.

## 2026-07-12 — feat/image-multiview (yaw orbit + time axis)

### Mission
Keep going: real camera yaw + time-of-day axes on the same SI scene graph.
Same world → many projections (bridge to virtual worlds). Still not diffusion.

### What changed
- NEW `world_camera.py` — parallax-by-Z orbit, sun path, night moon
- `generate_multiview` / `generate_time_sequence` in image_service
- API: `views`, `yaw_span`, `frames`, `yaw_deg`, `time_of_day`
- Studio: ⟲ 3 views, ⏱ 4 times buttons
- Tests: **18 passed**

### Axes now
X, Y (plane) · Z (depth) · yaw (orbit) · time (sun)

### Verified
```
pytest tests/test_image_roundout.py → 18 passed
world_camera demo: house cx shifts with yaw; night → moon
```

### Do NOT merge without Claude review.

## 2026-07-12 — feat/image-world-export (pitch + GIF + level JSON)

### Mission
Continue SI world stack: camera pitch, animated GIF export of sequences,
portable level JSON for virtual-world handoff. Still not diffusion.

### What changed
- `world_camera.py` — pitch DOF (horizon shift + vertical parallax)
- NEW `gif_export.py` — GIF/WebP from frame metas
- NEW `level_export.py` — `synthesus.si_level.v1` scene graph dump
- API: pitch_deg, as_gif, return_level; `POST /api/v1/image/level`
- Studio: ⏱ frames+GIF, ⧉ Level download
- Tests: **19 passed**

### Axes
x, y, z, yaw, pitch, time

### Verified
```
pytest tests/test_image_roundout.py → 19 passed
```

### Do NOT merge without Claude review.

## 2026-07-12 — feat/image-orbit-day

### Mission
Orbiting-day cinematic (yaw×time GIF) + tiny SI level viewer (X×Z map).

### What changed
- `generate_orbit_day` — same seed world, yaw+time schedules, GIF attach
- API: `orbit_day`, `orbit_frames`
- Studio: 🌐 Orbit day button; canvas level viewer + file open
- Level export also paints into viewer
- Tests: **20 passed**

### Verified
```
pytest tests/test_image_roundout.py → 20 passed
```

### Do NOT merge without Claude review.

## 2026-07-12 — feat/image-perf-review-fix (Claude review blockers)

### Claude findings addressed
1. **PERF blocker** — replaced O(edges×pixels) PIP fill/stroke with PIL scanline
   polygon/line + Gaussian soft AA. Pocket passes 3→2.
2. **Default res** — API/schema default 1024→512.
3. **Cache key** — explicit `ENGINE_VERSION=si-image-v2-pil-fill` in key.
4. **Honesty** — "Neural Load/link" → "SI Grid Load" / "SI link".

### Benchmark (pasted, look=raw, path_mode=True, seed=7)
```
res= 256     0.53s   (was ~2.7s in review env)
res= 512     1.44s
res=1024     7.48s   (was 79.11s — ~10× faster)
```
Tests: **20 passed in 2.99s** (was ~20s suite time).

### Remaining non-blocking
- 2048 still heavy; async job later
- Further vectorize materials if needed

### Do NOT merge without Claude re-verify.

## 2026-07-12 — feat/image-async-jobs

### Mission
Continue after Claude perf fix: merge main, async jobs for HD/multi-frame
(soft-DoS guard), job poll API, Studio polling.

### What changed
- Merged `origin/main` (ac98b91) into image tip
- NEW `image_jobs.py` — 2-worker queue, TTL, status/progress
- `execute_image_request` — single sync entry for API + workers
- POST /api/v1/image → 202 + job_id when async_mode or res≥1024 or multi-frame
- GET /api/v1/image/jobs/{id}
- Studio polls job_id with progress %
- Tests: **21 passed**

### Verified
```
pytest tests/test_image_roundout.py → 21 passed (~4.5s)
```

### Do NOT merge without Claude re-review of async + prior perf fix.

## 2026-07-12 — feat/image-bbox-perf (Claude follow-up #6)

### Mission
BBox-restrict per-object fill/stroke/materials so raster cost ∝ object area,
not full frame × objects. Output-preserving (outside bbox coverage = 0).

### What changed
- `cnc_paths.raster_fill_bbox` / `raster_stroke_bbox` — PIL only on padded bbox
- `paint_path` blends materials/depth only on crop slices
- `depth_buffer.write_depth` accepts matching crop shapes
- ENGINE_VERSION → `si-image-v3-bbox-fill`
- Test: bbox vs full-frame support agreement

### Benchmark (pasted, look=raw, path_mode, seed=7)
```
res= 256    0.19s   (was 0.53s after PIL; was ~2.7s original review)
res= 512    0.20s   (was 1.44s)
res=1024    0.59s   (was 7.48s / originally 79s)
photo512    0.56s
tests: 22 passed in 1.39s
```

### Do NOT merge without Claude re-verify.

---

## 2026-07-12 — feat/image-opt-enhance (ISP parallel + draft)

### Mission
Continue SI image optimization after bbox-fill: faster ISP, draft preview
quality, shared scene graph for multi-frame, parallel frame renders.

### What changed
- `camera_isp.box_blur` — PIL Gaussian on mono or full RGB (not 3× mono);
  smaller bloom/DOF radii for camera looks
- `cnc_paths.paint_path` — honor `path.meta["no_pocket"]` to skip multi-pass pocket
- `image_service`
  - `ENGINE_VERSION = si-image-v4-isp-parallel` (cache invalidation)
  - `DETAILS` includes **draft** (standard paint + CNC contours, no pocket)
  - `_build_base_scene` shared once for multiview / time / orbit-day
  - `ThreadPoolExecutor` parallel frames (up to 4 workers)
  - meta exposes `engine_version`
- Desktop + schema: draft detail option documented
- Test: `test_draft_detail_and_engine_v4`

### Benchmark (use_cache=False, seed=3)
```
ENGINE si-image-v4-isp-parallel
draft512     0.182s
raw512       0.166s
photo512     0.418s
photo1024    1.624s
multiview3   0.328s   (shared scene + parallel)
orbit3       0.034s
tests: 23 passed in 1.46s
```

### Honest notes
- Draft is preview speed (no pocket), not a fake photoreal shortcut.
- ISP is camera/TV math on SI geometry — still not diffusion.
- Do NOT merge to main without Claude re-review.

### Branch
`feat/image-opt-enhance` (from `feat/image-bbox-perf`) — commit `61f79cd`

---

## 2026-07-12 — feat/image-opt-enhance (scene plan compiler)

### Mission
Fully build LLM/rules scene compile: outer voice + inner monologue + puzzle-piece
composites so free language maps into SI constructible shapes (not diffusion).

### What changed
- **New** `runtime/packages/reasoning/scene_plan.py`
  - Rule compiler always on: synonyms, multi-word phrases, mood→camera,
    composite recipes (espresso, robot, cart, windmill, table, …) + heuristic
    assemblies from allowed roles only
  - Optional Ollama enrich via `use_llm_plan` / `SYNTHESUS_IMAGE_LLM_PLAN`
  - `inject_composites` appends paintable prims + optional CNC paths
  - Honesty: `construction` native|mapped|composite|mixed, outer_voice, monologue
- `image_service.generate_image` / `execute_image_request` default `compile_plan=True`
- Multiview/orbit/time share planned base graph
- API schema + production_server knobs; desktop chat draw + Studio show voice/plan
- ENGINE_VERSION → `si-image-v5-scene-plan`
- Tests: `test_scene_plan_compile_and_composite_render` (24 image tests green)

### Usage
```python
# rules only (default offline)
generate_image("espresso machine on grass under a sky", out, use_llm_plan=False)
# optional LLM enrich
# SYNTHESUS_IMAGE_LLM_PLAN=1  or  use_llm_plan=True
```

### Honest ceiling
LLM/rules supply recipes and routing; SI still only paints known roles.
Composites are procedural stand-ins, not photoreal invention.

---

## 2026-07-12 — feat/image-opt-enhance (v6 machine dialects + multi-pass)

### Mission
Full roadmap: lathe + extrude + plan routing + session multi-pass + picture-edit.

### What shipped
- `image_contract.py` + `docs/SI_IMAGE_CONTRACT.md` — honesty modes, stock=scene_graph
- `lathe_paths.py` — solid of revolution paint (cup/vase/column/bottle/fruit…)
- `extrude_paths.py` — print-lite box volumes + strata lines
- `image_session.py` — in-memory scene stock for multi-pass
- `picture_edit.py` — grade / vignette / text overlay (post-raster)
- `scene_plan` routes LATHE_ENTITIES / EXTRUDE_ENTITIES; inject machines
- `vsa_pipeline_image` paints `role=lathe|extrude`
- API: `scene_id`, `pass_only`/`from_scene`, `grade`, `edit_text`, `keep_session`
- `apply_scene_pass()` re-render without re-prompt
- ENGINE `si-image-v6-machine-pass`
- Tests: 25 passed (`test_lathe_extrude_session_and_picture_edit`)

### Multi-pass usage
```python
m = generate_image("a vase on grass under a sky", out, keep_session=True)
apply_scene_pass(m["scene_id"], out2, yaw_deg=20, look="cinema", grade="warm")
# API: { "scene_id": "...", "pass_only": true, "yaw_deg": 15, "grade": "cool" }
```

---

## 2026-07-12 — feat/image-opt-enhance (v6.1 workshop full pack)

### Mission
Implement full suggestion set: disk sessions, playlists, intent modes, materials,
level re-render, Studio inspector/capabilities, bench, Claude review package.

### Shipped
- Disk-backed `image_session` + playlists (finish/orbit/day_cycle)
- More lathe profiles + yaw foreshortening; extrude entities expanded
- `image_intent` draw/find/pass/refuse + capability card
- `image_materials_lib` mood palettes
- Level → session → re-render; level viewer click + re-render button
- Studio: plan inspector, can/can't, finish job playlist
- Chat: mode labels + pass knobs + refuse alternatives
- API: `/capabilities`, `/intent`, `/sessions/{id}`, playlist + level on `/image`
- `scripts/image_bench_regression.py` green
- `docs/CLAUDE_REVIEW_IMAGE_WORKSHOP.md` for Claude
- ENGINE `si-image-v6.1-workshop` · **26 tests passed**

### Do NOT merge without Claude review of this package.

## 2026-07-12 — feat/status-strip: instrument subsystem strip

### What
- Always-visible top strip `#instr-status-strip` (instrument tokens, mono, tabular).
- Polls real `GET /api/v1/health` every 4s: KERNEL status · MODEL · LLM green/red dot · uptime.
- Fixed chip: `⦸ OFFLINE — nothing leaves this machine` (accent cyan).
- Degrades to `—` when health unreachable — never fakes numbers.
- Does not cover dock; `paddingTop` on main for clearance.

### Proof
- Health sample: `status=online`, `llm.model=llama3.2:3b`, `ollama_reachable` drives dot, `uptime_seconds` real.
- DOM: body > `#instr-status-strip` with `#strip-kernel`, `#strip-model`, `#strip-llm-dot`, `.strip-offline`.

### Branch
`feat/status-strip` — do not merge without Claude review.
## 2026-07-12 — feat/voice-ui: SI Voice Studio + POST /api/v1/voice

### What
- Backend: `POST /api/v1/voice` in `production_server.py` — formant larynx (`larynx_vocalizer` / `formant_plan`) via `run_in_threadpool`.
  Returns `{audio_base64 WAV, phonemes, utterance_id, engine: si_formant_klatt, not_neural_tts}`.
  Rate-limited like `/api/v1/image`. **503 LOUD** if engine missing — no neural TTS fallback.
- Shell proxy: `POST /api/v1/voice` in `synthesus_native_shell.py` → runtime.
- Frontend: `#win-voice` instrument window + dock 🔊. Knobs: slower/faster/higher/lower/rising_final.
  Plays returned WAV; shows phonemes + "SI formant · no TTS model" caption.

### Proof (live curl, runtime :5010)
```
curl -s -X POST http://127.0.0.1:5010/api/v1/voice \
  -H 'Content-Type: application/json' \
  -d '{"text":"hello world","seed":25,"knobs":{"rising_final":true}}'
```
- HTTP 200; `audio_base64` decodes to **RIFF/WAVE** PCM 16-bit mono 16 kHz (31984 bytes).
- header `RIFF....WAVE`; phonemes `hello:HH EH L OW | world:W ER L D`; engine `si_formant_klatt`.
- Honest quality: **intelligible-but-robotic** formant speech — not natural TTS.

### Markup
`#win-voice.instr-window` with `.instr-caption`, knobs, SPEAK, `<audio id="voice-audio">`.

### Branch
`feat/voice-ui` — do not merge without Claude review.
## 2026-07-12 — feat/tier-badges: instrument trust chips in real chat

### What
- Answer-level instrument badges: ✓ Verified / ~ Grounded / • Unverified from real chat payload
  (`/api/chat` → runtime `/api/v1/query` sources + verification).
- Citation chips (`.instr-cite-chip`) from `data.sources`.
- 👍 confirm still mints `/api/human/attestation` then `/api/feedback` → runtime `/api/v1/feedback`.
  On upgrade: badge flips to ✓ Verified. If human-session secret missing: **fail closed** (stay Grounded).

### Proof
- Real query path returns `answer_id` + `sources`; UI renders `instr-tier-badge` + citation chips.
- Confirm path hits shell feedback proxy → `/api/v1/feedback`; without secret stays not upgraded.

### Branch
`feat/tier-badges` — do not merge without Claude review.
---

## 2026-07-12 — feat/loose-ends

### a. image_intent draw triggers
Widened DRAW routing for "make/create/generate a picture|image|drawing|illustration of X".
Bare "make coffee" stays talk (not draw).
Tests: `runtime/tests/test_image_intent_draw.py` 4 passed.

### b. feat/ui-bugfixes
Rebased onto latest main (`d96ae83`) → tip `6eeb493`. Conflict in `desktop/index.html`
cache bust only (kept main v=10031→10032). Foreman 404 poller stop still present.
Left for Claude review; **not merged**.

### Branch
`feat/loose-ends` — do not merge without Claude review.
---

## 2026-07-12 — feat/image-perf (bbox SDF/fill lock)

### What
BBox-restricted path fill/stroke was already merged via image-opt-enhance
(`raster_fill_bbox` / `paint_path` crop blend). This branch locks the claim:

### Proof (this machine, look=raw, path_mode, seed=7)
```
historical_1024_pre_bbox_s 79.0  # Claude review era
OK res= 512   0.26s  budget<=5.0
OK res=1024   0.50s  budget<=10.0
test_image_roundout.py: 26 passed
```
Target 1024 well under 10s: **met (~0.5s)**.

### Added
- `scripts/image_perf_bench.py` — fails if 1024 > 10s

### Branch
`feat/image-perf` — no further fill rewrite needed; output-preserving bbox already live.
---

## 2026-07-12 — feat/path-safety (centralize safe_id)

### What
- Added `runtime/packages/core/utils/safe_path.py` with `safe_id` / `safe_join`
  (path-traversal defense for user ids used as filenames).
- Replaced 4 copy-pasted sanitizers:
  - `image_session._disk_path`
  - `formant_session._path`
  - `production_server._PersistentList`
  - `state_persistence` NPC char_id
- Tests: `runtime/tests/test_path_safety.py` (6 passed).

### Proof
`pytest runtime/tests/test_path_safety.py -v` → 6 passed.
Crafted ids like `../../../../tmp/evil` resolve inside intended roots only.

### Branch
`feat/path-safety` — do not merge without Claude review.

---

## 2026-07-13 — feat/model-fetchers (optional local neural rails)

### What
- Added opt-in-only installers:
  - `scripts/fetch_realesrgan.sh`
  - `scripts/fetch_piper_voice.sh`
- Added `docs/OPTIONAL_NEURAL.md` with enable/disable/remove steps and license/source notes.
- No runtime endpoint or 503 behavior changes.
- Real-ESRGAN source note: upstream xinntao publishes official x4 PyTorch weights, not an official prebuilt x4 ONNX asset. The fetcher refuses third-party ONNX mirrors, verifies the official weights, and exports a local ONNX.

### Proof
Piper fetcher:
```text
checksum PASS: piper_linux_x86_64.tar.gz
checksum PASS: en_US-lessac-low.onnx
checksum PASS: en_US-lessac-low.onnx.json
Installed Piper CLI and voice:
/home/dakin/.local/share/synthesus/bin/piper
/home/dakin/.local/share/synthesus/voices/en_US-lessac-low.onnx
/home/dakin/.local/share/synthesus/voices/en_US-lessac-low.onnx.json
```

Real-ESRGAN fetcher:
```text
checksum PASS: RealESRGAN_x4plus.pth
ONNX export wrote /tmp/.../realesrgan-x4.onnx (68366684 bytes)
onnxruntime load PASS: inputs=1 outputs=1
Installed Real-ESRGAN ONNX:
/home/dakin/synthesus/runtime/data/models/realesrgan-x4.onnx
```

Without optional artifacts present:
```text
clean image_realesrgan_available= False model= None
clean voice_piper_available= False bin= None model= None
clean POST /api/v1/voice status= 503 error= voice_engine_unavailable
clean POST /api/v1/image status= 503 error= realesrgan_unavailable
```

After opt-in install:
```text
GET /api/v1/image/capabilities realesrgan.available= True model= /home/dakin/synthesus/runtime/data/models/realesrgan-x4.onnx
GET /api/v1/voice/capabilities piper.available= True bin= /home/dakin/.local/share/synthesus/bin/piper model= /home/dakin/.local/share/synthesus/voices/en_US-lessac-low.onnx
POST /api/v1/voice status= 200
voice wav header= b'RIFF' bytes= 48940 channels= 1 rate= 16000 frames= 24448
POST /api/v1/image status= 200
image png format= PNG size= (512, 512) bytes= 251376 engine= synthesus_vsa_geometric+plan_composite enhance= realesrgan
```

### Branch
`feat/model-fetchers` — do not merge without Claude review.
