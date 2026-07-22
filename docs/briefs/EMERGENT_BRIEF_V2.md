# SYNTHESUS — EMERGENT BUILD BRIEF (v2)

Everything below is the instruction. Copy it whole.

---

## 0. READ THIS FIRST — HOW THE LAST ATTEMPT FAILED

Your previous run pushed a branch called `conflict_210726_1348em`. It had:

* **no common ancestor with `main`** — its own "Initial commit"
* **88 files** against the repository's 2,632
* **none of the codebase** — no `services/`, no `apps/synthesus/`, no `contracts/`
* a `README.md` reading "# Here are your Instructions"
* the actual work delivered as a **patch file** (`synthesus_phase3_and_forge.patch`)
  sitting inside that scaffold

You scaffolded a new application instead of cloning the repository. Git reported
a "merge conflict" because it was being asked to reconcile two unrelated
repositories. The work inside the patch was good and has been recovered by hand —
but do not do this again.

**MANDATORY FIRST STEPS. Do these before writing any code:**

```bash
git clone <repo-url> synthesus && cd synthesus
git log --oneline -1          # must show: 7ee1243 (or later) — NOT "Initial commit"
git rev-list --count HEAD     # must be in the thousands, not single digits
ls services/ apps/synthesus/ contracts/   # all three MUST exist
git checkout -b <your-branch> # branch FROM main, never from a fresh init
```

If `git log` shows "Initial commit" or those directories are missing, **stop** —
you are not in the repository. Do not proceed, do not scaffold, do not create a
patch file. Report that you could not obtain the repo.

Every commit must land on a branch whose ancestor is `main`. Verify before you
push:

```bash
git merge-base --is-ancestor origin/main HEAD && echo OK || echo "NOT BRANCHED FROM MAIN"
```

---

## 1. WHAT THIS PRODUCT IS

Synthesus is a **local-first private AI desktop**. Its entire claim is that a
user's data stays on machines they own. Everything below serves that claim, and
anything that breaks it is worse than useless.

There is a working mesh underneath: nodes enrol with mutual TLS, jobs run in
rootless Podman on a real second machine, and results return signed and
verified. That part is physically proven on real hardware. Do not redesign it.

---

## 2. THE STACK — VERIFIED, NOT ASSUMED

Verified against commit `7ee1243`. If something contradicts this, trust the
tree and say so in your report.

**Frontend** — `apps/synthesus/desktop/`
`index.html`, `script.js`, `styles.css`, `design-system.css`, `assets/sdf_forge.js`.
Vanilla JS served as static files by a Python native shell (GTK/WebKit).
**NO build system. No npm, no package.json, no bundler, no React, no JSX, no TypeScript.**

**Backend** — `apps/synthesus/desktop/synthesusd.py` (FastAPI, loopback, API-key
auth), `terminal_server.py` (PTY over WebSocket → xterm.js).

**Mesh / services** — repo root `services/`:
`forge_render/` (renderer + native C++ core), `storage_zones.py`,
`unisync/` (mTLS transport, zone_sync), `agent_harness.py`, `entitlement.py`,
`remote_pipeline.py`.

**Runtime** — `apps/synthesus/runtime/packages/`:
`core/consciousness_integrator.py` (the C(t) fusion), `characters/`
(archive + identity chain), `kernel/` (C++ kernel, CMake, builds to `zo_kernel`,
spoken to over **stdin IPC** with line-delimited JSON), `reasoning/`, `api/`.

**HARD CONSTRAINT — NO EXTERNAL DEPENDENCIES.** No CDN links, no Google Fonts,
no npm packages, no remote APIs. A network dependency in the boot path breaks
the product's core claim. Inter is already vendored at
`assets/fonts/InterVariable.woff2`. Vendor anything else into `assets/` with its
licence.

**Design tokens** live in `design-system.css`. Use them; invent nothing:

```
colour  --bg-0/1/2 --panel --panel-raised --hairline --hairline-strong
        --purple --purple-light --purple-bright --purple-deep
        --success --warning --error --fg --fg-muted --fg-dim
type    --font --font-mono --w-title/section/button/body/meta
        --t-title --t-h2 --t-body --t-meta --t-micro
        --lh-tight --lh-body --lh-loose
space   --s1..--s6   (8px scale, no arbitrary values)
shape   --r-btn(14px) --r-card(18px) --r-pill
depth   --shadow-1/2/3  --elev-1/2/3
motion  --spring --t-fast --t-base --t-slow
```

Brand is **black / white / purple**. Purple is the only accent hue — **no blue,
no cyan**. Sentence case, never ALL-CAPS labels. Logo at
`assets/synthesus-mark-{32,64,128,512}.png`.

**Real endpoints** — use only these; do not invent APIs:

```
GET  /health  /ready
GET  /api/system/metrics          real /proc readings; fields may be null
GET  /api/settings                PUT /api/settings/evidence
GET  /api/devices                 POST /api/devices
PUT  /api/devices/{id}/capabilities   DELETE /api/devices/{id}
GET  /api/devices/discovered
POST /api/jobs                    GET /api/jobs/{id}
GET  /api/jobs/{id}/results/{sha}
POST /api/forge/render            → image/png  (server-side renderer)
WS   /ws/terminal/{session_id}
```

---

## 3. NON-NEGOTIABLE RULES

1. **NO MOCK DATA IN THE UI.** A value that cannot be measured renders the word
   `unknown`. Never a plausible-looking number. Do not write random-telemetry
   generators. This has been enforced across the whole codebase and a reviewer
   will check.
2. **Never touch `FINISH_CHECKLIST.md`.**
3. **Never delete a security finding or a record of a failed attempt** from
   `AGENT_LOG.md`.
4. **The storage-zone boundary is absolute.** `services/storage_zones.py`
   defines four zones. `GROUNDING → EXTERNAL` does not exist and must never be
   added — that move is a user's private data leaving their home, and it fails
   silently. Promotion into grounding requires `promote_to_grounding()` with an
   owner approval; there is **no bypass flag** and you must not add one.
5. **Do not weaken the forge's determinism.** `services/forge_render/native/Makefile`
   deliberately omits `-march=native` and sets `-ffp-contract=off`. Either would
   let two machines produce different pixels and seam at tile boundaries. Do not
   "optimise" those flags.
6. **Every claim in a commit or PR must be backed by a command you actually
   ran.** If you could not verify something, say so plainly.

---

## 4. THE WORK — IN PRIORITY ORDER

There is a hard deadline. **Do them in this order and ship what is done.** A
polished Priority 1 beats four half-finished features.

### PRIORITY 1 — Make the Image Forge work and look finished

This is the showcase feature. It renders images from signed distance fields —
no model, no weights, no network, fully reproducible from a short recipe code.

* The GTK/WebKit shell has **no WebGL2**, so the interactive canvas cannot run
  there. `POST /api/forge/render` already exists and works (verified: 512×512 in
  2.7s). **Wire the UI to fall back to it automatically** when WebGL2 is
  unavailable, showing the returned PNG in the stage. Right now the user sees an
  "unavailable" message and nothing else.
* Show a **loading state** during server renders (they take seconds).
* The **recipe code** (`SF1.0.6.35.285.60.0.42`) is the shareable artifact —
  make Copy/Load obvious and give feedback when they work.
* Populate every dropdown from `services/forge_render` (`SCENES`, palettes) —
  presets currently render as empty boxes.
* Add a **resolution / quality selector** bounded to what the endpoint accepts
  (32–2048px, quality 8–128).
* Make the panel feel finished: proper spacing on the 8px scale, real empty and
  error states, keyboard-reachable controls, visible focus rings.

### PRIORITY 2 — Drive the forge from chat

The showcase moment is a user typing a description and getting an image, on
their own machine, with no model involved.

* Add an intent path so a chat message like *"render a gyroid lattice in deep
  purple"* maps to a `Recipe` and calls `/api/forge/render`.
* Render the result **inline in the conversation**, with the recipe code beneath
  it so it is reproducible.
* `apps/synthesus/runtime/packages/reasoning/image_intent.py` and
  `scene_plan.py` already do prompt parsing — reuse them rather than starting
  over.
* **Be honest in the UI about what it can do.** `Recipe` currently exposes
  `mode, iters, blend, hue, glow, palette, cam` — four scenes and six knobs. A
  prompt selects and tunes; it does not compose arbitrary geometry. Say so in
  the interface rather than implying more.

### PRIORITY 3 — Login screen

First impression. Centred glass card, large logo
(`assets/synthesus-mark-128.png`), friendly copy, minimal text, one primary
action. Reuse the existing animated background. Currently only partly styled.

### PRIORITY 4 — Consistency pass on the older windows

Vitals, System Configuration and Quadbrain still use their original internal
layouts and look foreign against the new shell. Bring them onto the design
tokens. Chrome only — **do not rewire their behaviour.**

### DO NOT ATTEMPT under time pressure
Do not modify the mesh transport, enrolment, entitlements, or the zone
boundary. Do not restructure `services/`. Do not touch the C++ kernel build.
Those are load-bearing, physically verified, and not where the demo value is.

---

## 5. VERIFICATION — RUN THESE, REPORT REAL OUTPUT

```bash
# from repo root
.venv/bin/python -m pytest apps/synthesus/desktop tests/forge_render -q \
    --ignore=apps/synthesus/desktop/test_desktop_security.py
.venv/bin/python -m pytest tests -q
node --check apps/synthesus/desktop/script.js
```

Baselines you must not regress: **142** (desktop + forge_render) and **~520**
full-suite. `test_desktop_security.py` cannot be collected here (missing `jwt`)
— pre-existing, leave it alone.

**Bump the `?v=` cache-bust** on `styles.css` / `script.js` in `index.html`
whenever you change either. A prior session shipped three rounds of invisible
CSS by forgetting this.

To see the app run:

```bash
~/.local/bin/synthesus --standard      # UI on http://127.0.0.1:8081
```

Test the render endpoint directly:

```bash
set -a; . ~/.local/share/synthesus/synthesus.env; set +a
curl -s -H "X-API-Key: $SYNTHESUS_API_KEY" -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:5011/api/forge/render \
  -d '{"code":"SF1.0.6.35.285.60.0.42","width":512,"height":512,"quality":48}' \
  -o /tmp/forge.png && file /tmp/forge.png
```

---

## 6. DELIVERABLE

* One branch per priority, branched from `main`, each with its own PR. **Do not
  merge.** Small reviewable PRs beat one large one.
* An `AGENT_LOG.md` entry per PR in the established style, ending with an
  explicit **HONEST GAPS** section listing what you did *not* verify.
* If you cannot render or visually confirm the UI, write "the page was never
  rendered" plainly. Do not imply otherwise.
* Commit trailer: `Co-Authored-By: <your agent name>`

**If you run short on time, ship Priority 1 finished rather than four things
started.**
