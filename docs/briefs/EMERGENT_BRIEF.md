# Outsourcing brief — Synthesus front end, expansion drive, mobile

Written 2026-07-21. Verified against `main` at the time of writing — the file
inventory, design tokens, endpoints and test baselines below were read from the
tree, not from memory. A previous brief in this project described an *unmerged*
branch's contents as if they were on `main` and sent an agent down the wrong
path; check these facts still hold before handing this out.

**Scope warning.** This is four substantial phases. Handing all of it to one
agent in one pass will produce shallow work on at least three. Give Phase 1
alone first and judge the output — it is self-contained with clear pass/fail.

**Phase 3 is the one to hesitate over.** A plausible-looking bug there means a
user's private grounding corpus is pushed to a cloud remote, silently. The zone
boundary exists in code, but a sync loop that simply never calls it would pass
every test not specifically looking for that.

---

## THE PROMPT (everything below is the brief)

You are working on Synthesus / Planetary Stack — a private-mesh AI desktop.

### ACCESS
Repo: `github.com/Str8biddness/planetary-stack` — PRIVATE. You need read+write
access granted before starting. Branch from `main`. Open PRs; do not merge.

### READ THIS BEFORE WRITING CODE
`AGENT_LOG.md` — governing rules at the top, last ~400 lines for recent context.
These rules are non-negotiable and violating them makes the work unusable:

- NEVER present simulated, mocked, or fixture-only behaviour as verified or
  physical. If you did not run it, say so.
- NEVER touch or check a box in `FINISH_CHECKLIST.md`.
- Never delete a security finding or a record of a failed attempt.
- No placeholder keys, no fake signatures, no `validator=None`.
- NO MOCK DATA IN THE UI. A value that cannot be measured renders the word
  "unknown" — never a plausible-looking number. Do not write random-telemetry
  generators.
- Every claim in a commit or PR body must be backed by a command you actually
  ran and its real output.

### STACK REALITY — verified, do not assume otherwise
Frontend: `apps/synthesus/desktop/` — vanilla JS served as static files by a
Python native shell. **NO build system. No npm, no package.json, no bundler,
no React, no TypeScript, no JSX.**
Backend: FastAPI in `synthesusd.py` (loopback, API-key auth) + `terminal_server.py`.

**NO EXTERNAL DEPENDENCIES.** No CDN links, no Google Fonts, no npm packages.
This product's core claim is that it runs on the user's machine with no network;
a CDN tag in the boot path breaks it offline. Vendor anything needed into
`assets/` with its licence (Inter is already vendored at
`assets/fonts/InterVariable.woff2`).

### WHAT ALREADY EXISTS (accurate inventory)
Files: `index.html`, `script.js`, `styles.css`, `design-system.css`,
`synthesusd.py`, `device_policy.py`, `host_metrics.py`, `mesh_discovery.py`,
`terminal_server.py`, `xterm.js`.

Design tokens in `design-system.css` — USE THESE, invent nothing:

    colour  --bg-0/1/2, --panel, --panel-raised, --hairline, --hairline-strong,
            --purple, --purple-light, --purple-bright, --purple-deep,
            --success, --warning, --error, --fg, --fg-muted, --fg-dim
    type    --font, --font-mono, --w-title/section/button/body/meta,
            --t-title, --t-h2, --t-body, --t-meta, --t-micro,
            --lh-tight, --lh-body, --lh-loose
    space   --s1..--s6 (8px scale, no arbitrary values)
    shape   --r-btn (14px), --r-card (18px), --r-pill
    depth   --shadow-1/2/3, --elev-1/2/3
    motion  --spring, --t-fast, --t-base, --t-slow

Brand is BLACK / WHITE / PURPLE. Purple is the only accent hue — no blue or
cyan. Sentence case, never ALL-CAPS labels. Logo:
`assets/synthesus-mark-{32,64,128,512}.png` (white mark, transparent).

Existing breakpoints: 420, 720, 900, 1240, 1500, 2400, 3000px, plus
`prefers-reduced-motion`. EXTEND these; do not add a parallel set.

Real endpoints (use only these; do not invent APIs):

    GET  /health, /ready
    GET  /api/system/metrics      real /proc readings; fields may be null
    GET  /api/settings            PUT /api/settings/evidence
    GET  /api/devices             POST /api/devices
    PUT  /api/devices/{id}/capabilities
    DELETE /api/devices/{id}      GET /api/devices/discovered
    POST /api/jobs                GET /api/jobs/{id}
    GET  /api/jobs/{id}/results/{sha}
    WS   /ws/terminal/{session_id}

The UI already has: an Overview surface (left rail, top bar with search, hero,
metric cards with sparklines, right panel with gauges), workspaces replacing
floating windows, Devices & Permissions, Settings, a dock.

### PHASE 1 — Mobile PWA (highest priority)
An earlier attempt was built against a stale tree; redo against `main`.

- `manifest.webmanifest` + `theme-color` meta, icons from the existing marks.
- A service worker caching the app shell for offline launch. Version the cache,
  clean old caches on activate, and **never cache `/api/*`** — stale API data
  would render fabricated-looking state.
- PWAs need a secure context: HTTPS **or localhost**. Phone nodes serve
  `http://localhost:8081` on the device itself, which qualifies. Do not
  introduce anything assuming HTTPS or an external origin.
- Mobile pass on the Overview: rail collapses, right panel hides, touch targets
  >=44px, no horizontal scroll at 360/390/412px.
- Phone worker view: this device's status (working/idle/paused), items done,
  battery via the Battery Status API where readable and "unknown" where not.
  Thermal has no web API — render "unknown", do not estimate it.

### PHASE 2 — Finish the desktop front end
- **Login screen**: centred glass card, large logo, friendly copy, minimal text,
  single primary action. Animated background reusing the existing aurora layer.
- **AI chat as the centrepiece**: conversation history left, messages centre,
  context right (model, memory, workspace). Increase message spacing and bubble
  padding. Show avatars, timestamps, tool usage, reasoning status, code blocks,
  markdown. It must resemble a premium AI IDE, not a messaging app.
- **Terminal**: rounded, tabs, syntax highlighting, no retro styling. It already
  works over `/ws/terminal/{session_id}` with xterm.js — restyle, do not rewire.
- **Empty states everywhere**: illustration, explanation, primary + secondary
  action. Never a blank panel.
- Window internals (Vitals, Config) still use their original layouts and look
  foreign against the new shell — bring them onto the design system.

### PHASE 3 — Expansion drive sync
The "expansion drive" is NOT a disk. It is a grounding-ingestion pipeline
(`/api/v1/drive/ingest|paste|preview|sources|remotes`, rclone-backed).

Build a push/pull sync loop over the existing content-addressed store
(`services/unisync/storage.py` — `ContentAddressedStore`), moving content
between nodes over the existing lease-bound mTLS transport.

**THE ZONE BOUNDARY IS NON-NEGOTIABLE.** `services/storage_zones.py` already
exists and defines it. The sync loop MUST call it:

    NODE       never syncs, never leaves the device
    OUTPUT     syncs freely over mesh; circulating means AVAILABLE, not BELIEVED
    GROUNDING  mesh only; workers may NOT write to it
    EXTERNAL   the only zone permitted to leave the home (git/rclone)

Moves are an allowlist. `GROUNDING -> EXTERNAL` does not exist and must not be
added — that move is personal data leaving the user's home, and it fails
silently in production. Promotion into GROUNDING requires
`promote_to_grounding()` with an owner approval. There is no bypass flag and you
must not add one.

Sync design notes: content is immutable and content-addressed, so there are no
write conflicts on content — only on references. Use digests for diffing, make
jobs idempotent (leases already carry fencing tokens), and add backpressure so a
fast node cannot flood a slow one.

### PHASE 4 — Termux node terminal
Spare Android phones join as workers via Termux + proot-distro. Run
`terminal_server.py` on the phone inside proot and route its session into the
existing desktop terminal UI, so every node is manageable from one surface.
Note: proot has no root, no Podman, no FUSE. Do not design around mounting.

### TESTS — required
Follow the existing style in `apps/synthesus/desktop/test_ui_wiring.py`: it
asserts every markup handler is defined and every element the script reads
exists. For anything you add, test the REFUSALS, not just the happy path.

Run from repo root:

    .venv/bin/python -m pytest apps/synthesus/desktop -q \
        --ignore=apps/synthesus/desktop/test_desktop_security.py
    .venv/bin/python -m pytest tests -q
    node --check apps/synthesus/desktop/script.js

Baselines you must not regress: **92 desktop tests, 475 full-suite** (1 skipped
— an opt-in live-Ollama test). `test_desktop_security.py` cannot be collected
(missing `jwt` module) — pre-existing, leave it alone.

Bump the `?v=` cache-bust on `styles.css`/`script.js` in `index.html` whenever
you change either. A prior session shipped three rounds of invisible CSS by
forgetting this.

### REPORTING — this matters as much as the code
For each PR: what you ran, what its real output was, and an explicit HONEST GAPS
section listing what you did NOT verify. If you cannot render the UI, say "the
page was never rendered" plainly. Append an `AGENT_LOG.md` entry in the
established style.
