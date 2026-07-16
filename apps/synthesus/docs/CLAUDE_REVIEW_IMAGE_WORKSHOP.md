# Claude Review Package — SI Image Workshop Stack

**Branch:** `feat/image-opt-enhance`  
**Engine:** `si-image-v6.1-workshop`  
**Date:** 2026-07-12  
**Product rule:** SI constructs form; LLM may plan recipes only; not diffusion; do not merge to main without review.

---

## 1. Executive summary

This branch extends Synthesus SI image generation from a VSA scene graph + CNC path raster into a **workshop**:

| Layer | Role |
|-------|------|
| **Plan** | Rules (+ optional sparse LLM) map language → entities / machines / composites |
| **Machines** | Mill (CNC paths), lathe (revolution), extrude (print-lite volumes) |
| **Stock** | Scene graph + plan (disk-backed `scene_id`), not the PNG |
| **Passes** | Re-render / orbit / ISP / grade / finish playlist |
| **Picture-edit** | Post-raster grade/text only (labeled) |
| **Intent** | Chat modes: draw / find / pass / refuse / talk |

Honest ceiling unchanged: **no faces, brands, landmarks-as-photo, generative fill.**

---

## 2. Architecture (stock vs readout)

```
User language
  → image_intent (draw|find|pass|refuse|talk)
  → scene_plan (synonyms, LATHE/EXTRUDE/composite, mood, material_lib)
  → pattern_document + inject machines/composites
  → world_camera (yaw/pitch/time)
  → CNC / lathe paint / extrude paint
  → camera_isp (optional quality=draft|full)
  → picture_edit (optional grade/text)
  → PNG + scene_id (session disk)
```

**Stock of truth:** `scene_doc` + `plan` in `image_session` (memory + `~/.cache/synthesus/image_sessions/`).  
**PNG:** camera readout after any pass.

---

## 3. File inventory (this expansion arc)

### New modules
| File | Purpose |
|------|---------|
| `runtime/packages/reasoning/scene_plan.py` | Language → SI plan, inject, monologue/outer voice |
| `runtime/packages/reasoning/image_contract.py` | Construction modes / honesty helpers |
| `runtime/packages/reasoning/lathe_paths.py` | Solid of revolution + yaw foreshortening |
| `runtime/packages/reasoning/extrude_paths.py` | Print-lite extruded boxes |
| `runtime/packages/reasoning/picture_edit.py` | Grade / vignette / text overlay |
| `runtime/packages/reasoning/image_session.py` | Multi-pass stock + disk + playlists + level import |
| `runtime/packages/reasoning/image_intent.py` | Chat intent + capability card + refuse alternatives |
| `runtime/packages/reasoning/image_materials_lib.py` | Mood palettes (procedural, not scraped media) |
| `runtime/packages/reasoning/docs/SI_IMAGE_CONTRACT.md` | Contract doc |
| `scripts/image_bench_regression.py` | Fixed-prompt latency smoke |
| `docs/CLAUDE_REVIEW_IMAGE_WORKSHOP.md` | This package |

### Heavily modified
| File | Change |
|------|--------|
| `image_service.py` | Plan, session, lathe/extrude meta, pass/playlist/level, ENGINE v6.1 |
| `vsa_pipeline_image.py` | Paint `lathe` / `extrude`; camera_yaw |
| `cnc_paths.py` | Bbox fill; `no_pocket` (earlier) |
| `camera_isp.py` | PIL blur; draft quality |
| `depth_buffer.py` | lathe/extrude depths |
| `api/schemas.py` + `production_server.py` | Request knobs; capabilities/intent/session routes |
| `desktop/index.html` + `script.js` | Grade, re-pass, playlist, plan inspector, chat modes, level re-render |

---

## 4. API surface (reviewers)

| Endpoint | Notes |
|----------|--------|
| `POST /api/v1/image` | Full generate; `compile_plan`, `keep_session`, `grade`, `scene_id`+`pass_only`, `playlist`, `level` |
| `GET /api/v1/image/capabilities` | Can/can't card |
| `GET /api/v1/image/sessions/{id}` | Session view (disk-backed) |
| `POST /api/v1/image/intent` | Classify draw/find/pass/refuse |
| `POST /api/v1/image/level` | Level export (existing) |
| `GET /api/v1/image/jobs/{id}` | Async HD/multi-frame |

---

## 5. Construction modes (meta.construction)

`native | mapped | composite | lathe | extrude | mill | mixed | retrieved | picture_edit`

Always: `not_diffusion: true`, preferred `stock: scene_graph`.

---

## 6. Validation performed

```text
pytest runtime/tests/test_image_roundout.py
# target: 26 tests (includes workshop disk/intent/playlist)

scripts/image_bench_regression.py
# fixed prompts: house, vase+crate, espresso, cabin dusk + pass smoke
```

Reviewer should re-run both after pull.

---

## 7. Known risks / review focus

1. **Disk sessions** — JSON under home cache; no authz between local users; ok for single-user desktop, not multi-tenant cloud without isolation.  
2. **LLM plan enrich** — optional, best-effort Ollama; invalid roles discarded; default auto only on sparse plans.  
3. **Level import** — rehydrates entities without reattaching live CNC Path objects; re-render uses role paint + may re-path if path_mode.  
4. **Lathe yaw** — foreshortening cue only; not true 3D orbit of a mesh.  
5. **Find mode** — intentionally not implemented media API; returns honest message.  
6. **Thread safety** — session dict + disk write under lock; parallel multiview deep-copies doc.  
7. **Cache key** — includes ENGINE_VERSION + plan fingerprint; bump engine on behavior change.  
8. **Do not merge to main** without Claude sign-off (project rule).

---

## 8. Product honesty checklist

- [x] SI ≠ diffusion in meta and UI copy  
- [x] Outer voice / monologue on plan  
- [x] Picture-edit labeled separately  
- [x] Refuse identity/landmark/brand with construct alternative  
- [x] Find mode not faked as SI render  
- [x] Chat labels `[draw · SI construct]` / `[find]` / `[pass]`  

---

## 9. Suggested review probes

1. `draw a vase and a crate on grass under a sky` → lathe_parts + extrude_parts ≥ 1, scene_id set.  
2. `pass_only` with yaw=20 + grade=warm → new PNG, same scene_id.  
3. `playlist=finish` → ≥3 frames.  
4. Kill process, `GET /sessions/{id}` or re-pass after reload from disk.  
5. `photo of Elon` via intent → refuse, no image.  
6. `find photo of barn` → find message, no fake SI claim.  
7. Import level JSON → re-render.  
8. Bench script all OK under budgets.

---

## 10. Out of scope (explicit non-goals)

- Diffusion / generative fill fallback  
- Photoreal identity or brand forgery  
- Full 3D mesh CAD  
- Production multi-tenant session ACL  

---

## 11. Merge recommendation

**REQUEST REVIEW** — large vertical feature. After approval: merge to main with squash or keep feature history; update `AGENTS.md` engine note if desired.

**Reviewer sign-off fields**

| Item | Status |
|------|--------|
| Architecture coherent with SI≠AI | _ |
| No silent diffusion path | _ |
| Tests green | _ |
| Disk session acceptable for deployment model | _ |
| Ready for main | _ |

---

*Prepared for Claude Code / human review. Implementation agent: Grok Build on feat/image-opt-enhance.*
