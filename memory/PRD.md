# Synthesus / Planetary Stack — outsourcing engagement

## Context
Working on `github.com/Str8biddness/planetary-stack` (owner made it temporarily
public for this session). Cloned to `/tmp/planetary-stack`. Vanilla-JS desktop +
FastAPI, monorepo, NO build system, NO external deps (offline core claim).
Governing rules in `AGENT_LOG.md` / `AGENTS.md`: no simulated success, no mock
data in UI, never touch `FINISH_CHECKLIST.md`, back every claim with a real run.

## Environment note
This pod is aarch64. The repo's briefing baselines (92 desktop, 475 full) were
recorded on x86_64. On this host the pre-existing baseline is **78 desktop** and
**428 full-suite passing** (45 fail + 2 error are all one pre-existing arm64
cause: `platform.machine()`→`aarch64` normalised to `"arm64"`, which the
`ResourceInventory` pydantic literal rejects — unrelated to this work). Python
3.12 obtained via `uv`; deps: `pip install -e . pytest httpx fastapi uvicorn
websockets requests flask flask_cors werkzeug pywebview`.

## Done (2026-07-21)
- **Phase 3 — zone-aware expansion-drive sync** (`services/unisync/zone_sync.py`).
  Push/pull loop over `ContentAddressedStore` + injected mTLS `ObjectTransport`.
  Zone boundary (`services/storage_zones.py`) called as the first statement of
  every transfer; refused moves touch nothing. Digest diffing, idempotent,
  object-level backpressure, reference reconciliation. 20 refusal-first tests
  (`tests/unisync/test_zone_sync.py`) incl. grounding-never-over-public and
  node-never-leaves-device. Full suite: 428→448 passing (+20, zero new fails).
- **CSG + SDF Image Forge (v2)** (owner-requested wow feature). Vendored
  dependency-free WebGL2 raymarcher (`assets/sdf_forge.js`): union/intersect/
  difference, smooth union, Menger sponge, infinite lattice, gyroid orb. Soft
  shadows, AO, fresnel glow, purple palettes, vignette + film grain. Shareable
  recipe codes (`SF1.m.i.b.h.g.p.c`), free-text seeds, 6 named presets, PNG
  export. New `win-forge` window, design-token styled, degrades to "unknown"
  (no fake frame). 32 wiring/determinism tests. Rendered for real in headless
  Chromium (6 presets, non-empty PNGs). Cache-bust `?v=20260721l`.

Deliverable exported as `/app/synthesus_phase3_and_forge.patch` (commit on branch
`agent/phase3-zone-sync-and-forge`). Not pushed (no write creds; owner must grant
access or apply the patch and open the PR).

## Backlog / not done
- **Distributed forge rendering** (`services/forge_render/`): pinned CPU engine,
  work-stealing tiler, seamless composite, bloom overlap margin, adaptive
  local/distribute, real 3-number benchmark (crossover ~39ms/3 nodes here).
  17 tests. NOT wired into desktop UI (needs live nodes); mesh round-trip is an
  in-process lower bound.
- **Phase 2 — desktop front end** (login screen, AI-chat centrepiece, terminal
  restyle, empty states, bring Vitals/Config onto the design system). LARGE;
  deferred. Owner listed this second after Phase 3.
- **Phase 1 — mobile PWA** (manifest, service worker never caching /api, mobile
  Overview, phone worker view). A prior PR #50 targeted a stale tree; needs redo
  against merged main.
- **Phase 4 — Termux node terminal** (proot, no root/Podman/FUSE).
- Forge: render inside the real pywebview native shell; add scene presets/seeds.
