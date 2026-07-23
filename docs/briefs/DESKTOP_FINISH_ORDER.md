# SYNTHESUS — DESKTOP FINISH ORDER

Work order for the desktop and the forge. Read this whole file before writing
code. It assumes no prior context beyond the repository itself.

---

## 0. FIRST — PROVE YOU ARE IN THE RIGHT REPOSITORY

The two previous outsourced attempts failed by scaffolding a *new* application
instead of extending this one. Both produced a React/FastAPI/Mongo app with no
common ancestor with `main`. Do not repeat it.

```bash
git log --oneline -1                       # must NOT say "Initial commit"
git rev-list --count HEAD                  # thousands, not single digits
ls services/ apps/synthesus/ contracts/    # all three MUST exist
git merge-base --is-ancestor origin/main HEAD && echo OK || echo NOT BRANCHED FROM MAIN
```

If any check fails, **stop and report it**. Do not scaffold, do not produce a
patch file.

---

## 1. WHAT THIS PRODUCT IS

A **local-first private AI desktop**. Its entire claim is that the user's data
stays on machines they own. Anything that breaks that claim is worse than
useless.

The frontend is **vanilla JS served as static files**:
`apps/synthesus/desktop/{index.html,script.js,styles.css,design-system.css}`.

> **NO build system. No npm, no package.json, no bundler, no React, no JSX, no
> TypeScript. No CDN links, no Google Fonts, no remote APIs.**

A network dependency in the boot path breaks the product. Inter is vendored at
`assets/fonts/InterVariable.woff2`. Vendor anything else into `assets/` with its
licence.

### Process topology

```
browser
  └── :8081  Flask shell (synthesus_native_shell.py) — static files, some APIs, PROXY
        └── :5011  synthesusd.py — auth boundary, holds the API key
              └── :5010  CHAL runtime (production_server.py)
                    └── mesh / AIVM workers
```

The browser **never** receives the API key. If the UI needs a controller
endpoint, the Flask shell must proxy it (see `forge_render_proxy`). Endpoints
that exist on `:5011` but are not proxied will 404 from the page — that is a
real, current gap, not a mystery.

Run it:

```bash
cd apps/synthesus
SYNTHESUS_HEADLESS=1 ./launch.sh --standard    # UI on http://127.0.0.1:8081
```

`SYNTHESUS_HEADLESS=1` serves the identical desktop over HTTP with no GTK
window — use it on any machine without a display.

---

## 2. NON-NEGOTIABLE RULES

1. **NO MOCK DATA IN THE UI.** A value that cannot be measured renders the word
   `unknown`. Never a plausible-looking number. No random-telemetry generators.
2. **Brand is black / white / purple.** Purple is the only accent hue — no blue,
   no cyan, no gold/pink/orange gradients. **Sentence case, never ALL-CAPS
   labels.** Use tokens from `design-system.css`; invent nothing. 8px spacing
   scale, no arbitrary values.
3. **Do not weaken forge determinism.** `services/forge_render/native/Makefile`
   omits `-march=native` and sets `-ffp-contract=off`. Either would let two
   machines produce different pixels and seam at tile boundaries.
4. **The storage-zone boundary is absolute.** `GROUNDING → EXTERNAL` does not
   exist and must never be added. No bypass flag.
5. **Never touch `FINISH_CHECKLIST.md`.** Never delete a security finding or a
   record of a failed attempt from `AGENT_LOG.md`.
6. **Do not modify** mesh transport, enrolment, entitlements, or the C++
   reasoning kernel (`zo_kernel`). They are load-bearing and physically
   verified. The *forge* native core is in scope; the reasoning kernel is not.
7. **Every claim must be backed by a command you actually ran.** If you could
   not verify something, say so plainly.

---

## 3. STATE OF PLAY

Recipe v2 exists **in C++ only** and is **not reachable from the app**.

Already done in `services/forge_render/native/forge_core.cpp`:

* A composable scene-graph evaluator (`sdf_v2`) and a renderer
  (`forge_render_region_v2`).
* v1 code above the v2 section is untouched. Verified: 16 v1 recipes across all
  four modes rendered through the pre-change and post-change `.so` — **0
  differing bytes**.
* Builds clean under `-Wall -Wextra` with the determinism flags unchanged.
* `tests/forge_render` 24 passed; desktop forge tests 40 passed.

Not done: Python binding, recipe code format, endpoint, refusal path,
committed tests. **That is Workstream A.**

### The v2 ABI (you will need this exactly)

```c
struct NodeV2  { int op; int a; int b; double p[6]; };   // a,b = child indices or -1
struct RecipeV2{ int hue; int glow; int palette; int cam; int root; int count; };

void forge_render_region_v2(const NodeV2* graph, const RecipeV2* rc,
                            int full_w, int full_h,
                            int x0, int y0, int x1, int y1,
                            int quality, uint8_t* out);
```

Op codes:

```
primitives   0 sphere(r)         1 box(bx,by,bz)     2 torus(R,r)
             3 capsule(h,r)      4 cylinder(h,r)     5 cone(h,r)
             6 octahedron(s)     7 hexprism(h,r)     8 plane(y)
combinators 20 union            21 subtract         22 intersect
            23 smooth_union(k)  24 smooth_subtract(k) 25 smooth_intersect(k)
transforms  40 translate(x,y,z) 41 scale(s)         42 rotate_x(a)
            43 rotate_y(a)      44 rotate_z(a)      45 twist(k)
            46 bend(k)          47 mirror(fx,fy,fz) 48 repeat(px,py,pz)
            49 round(r)         50 shell(t)
fractals    60 menger(iters)    61 gyroid(scale,thick)
            62 mandelbulb(iters,power)               63 apollonian(iters,s)
```

**Invariant: a child index is always strictly less than its parent's index.**
Cycles are therefore unrepresentable, and a malformed graph off the wire is a
bounds check rather than a hang. Preserve this when validating input.

---

## 4. THE WORK

Do the workstreams in order. **A gates B.** C and D are independent and may be
done by a separate agent in parallel.

---

### WORKSTREAM A — Make Recipe v2 reachable

Without this, the C++ work is dead code.

- [ ] **A1. ctypes binding.** In `services/forge_render/engine.py`, add
      `_CNodeV2` / `_CRecipeV2` mirroring the ABI above, and bind
      `forge_render_region_v2`. Do not disturb the existing v1 binding.
- [ ] **A2. `RecipeV2` model.** A dataclass holding `nodes: list[Node]`,
      `root`, plus `hue/glow/palette/cam`. Validate on construction: op codes
      known, child indices in range **and strictly less than the parent index**,
      node count bounded (suggest ≤ 64), parameters finite.
- [ ] **A3. `SF2` code format.** v2's shareable artifact, the counterpart to
      `SF1.0.6.35.285.60.0.42`. Requirements: round-trips exactly, is URL-safe
      and copy-pasteable, and is version-tagged so `SF1` and `SF2` are never
      confused. Reject malformed input with a specific error, never a silent
      default. Suggested: `SF2.` + base64url of a canonical compact encoding.
- [ ] **A4. Render entry point.** `render_full_v2(recipe, w, h, quality)` and a
      tile variant matching the v1 signature so the distributed renderer can
      call it unchanged.
- [ ] **A5. Refuse loudly without the native core.** v2 has no Python mirror by
      design. When `native_available()` is false, a v2 render must raise/return
      an explicit error naming the build command
      (`make -C services/forge_render/native`). It must **never** fall back to a
      different-looking image.
- [ ] **A6. Endpoint.** Extend `POST /api/forge/render` in
      `apps/synthesus/desktop/synthesusd.py` to accept a v2 recipe (`code`
      starting `SF2.`, or an explicit graph). Keep existing bounds: 32–2048px,
      quality 8–128. Return `X-Forge-Recipe` with the **v2** code actually
      rendered. Reject a v2 request with 503 and a clear body when the native
      core is missing.
- [ ] **A7. Tests** in `tests/forge_render/`:
  - [ ] **v1 byte-identity is a permanent regression test.** Render a fixed set
        of v1 recipes and assert bytes against committed fixtures.
  - [ ] `SF2` round-trip; malformed codes rejected with a named error.
  - [ ] Graph validation: forward/self child reference, out-of-range index,
        unknown op, oversized graph — each refused.
  - [ ] Determinism: same graph rendered twice → identical bytes.
  - [ ] Tile/whole-frame agreement: a tile of a frame equals that region of the
        full frame (this is the seam guarantee).
  - [ ] Native-missing refusal for v2.

**Acceptance:** a `SF2.` code POSTed to `/api/forge/render` returns a PNG, and
the same code returns byte-identical output on a second call.

---

### WORKSTREAM B — Chat drives the forge *(Priority 2)*

The showcase moment: a user types a description and gets an image, on their own
machine, with no model involved.

Note the endpoint docstring already anticipates this: *"It is also what a chat
request calls, so a prompt and a slider produce the same image."*

- [ ] **B1. Routing decision.** Chat already routes `draw/imagine/render` to the
      **SI scene engine** (`/api/v1/image`), which is a *different* renderer.
      Decide explicitly how a message reaches the forge instead, and write the
      reasoning down. Options: scene-vocabulary match (gyroid, menger, lattice,
      sponge, fractal…), an explicit `/forge` command, or a new `forge` mode in
      the `/api/v1/image/intent` classifier. **Do not silently hijack existing
      draw behaviour** — that is a regression for users who want the SI engine.
- [ ] **B2. Prompt → graph.** Map a prompt to a `RecipeV2`. Reuse
      `apps/synthesus/runtime/packages/reasoning/image_intent.py` and
      `scene_plan.py` (mood/hue extraction) rather than starting over. Must be
      **deterministic**: same prompt → same graph, and therefore same image.
- [ ] **B3. Inline result.** Render the PNG in the conversation with the
      **recipe code beneath it**, plus a copy control. The code is the
      reproducibility story — it is not decoration.
- [ ] **B4. Loading and failure states.** Server renders take seconds. Show
      progress; a frozen panel reads as a crash. On failure say what failed.
- [ ] **B5. Be honest about capability in the UI.** Even with v2 the mapping is
      bounded. Say what a prompt can and cannot do rather than implying
      arbitrary geometry.
- [ ] **B6. Tests.** Prompt→graph determinism; the router sending SI prompts to
      SI and forge prompts to forge; inline render wiring; failure path.

**Acceptance:** typing a description in chat produces an image and a code that
re-renders identically when pasted into the forge panel.

---

### WORKSTREAM C — IDE additions, native

The desktop already has an IDE window (`/api/ide/files`, `/api/ide/read`) and a
terminal (xterm.js over the Unix-socket PTY). These are **extensions to it**.

`Str8biddness/synthesus-ide` is a **reference for features only**. Its design
system directly contradicts this product (gold/pink/orange gradients, ALL-CAPS
labels, Tailwind, React, and it explicitly forbids Inter). **Port capabilities,
never its styling or stack.**

- [ ] **C1. Resizable split panes** — explorer / editor / panel / terminal.
      Vanilla JS, pointer events, no library. Persist sizes locally.
- [ ] **C2. File CRUD** — create, rename, delete via the controller, with
      confirmation on destructive actions. Refuse writes outside the permitted
      root and prove it with a test.
- [ ] **C3. AI code actions** — explain / refactor / NL→code on a selection,
      through the existing chat path to the local model. Never send code to a
      remote API.
- [ ] **C4. Preview pane** — render a local HTML file in an iframe. Same-origin
      only, no remote loads.
- [ ] **C5. Plugin hooks** *(optional, last)* — a registration surface for panel
      contributions. Do not build a marketplace.

**Acceptance:** each addition works in the browser at `:8081`, uses only design
tokens, and adds no external dependency.

---

### WORKSTREAM D — Login screen and consistency *(Priorities 3 & 4)*

- [ ] **D1. Login screen.** First impression. Centred glass card, large logo
      (`assets/synthesus-mark-128.png`), friendly copy, minimal text, one
      primary action. Reuse the existing animated background. Currently only
      partly styled.
- [ ] **D2. Consistency pass.** Vitals, System Configuration and Quadbrain still
      use their original internal layouts and look foreign against the shell.
      Bring them onto the design tokens. **Chrome only — do not rewire their
      behaviour.**
- [ ] **D3. Keyboard and focus.** Controls reachable by keyboard, visible focus
      rings, sensible tab order.

---

## 5. VERIFICATION — RUN THESE, REPORT REAL OUTPUT

Establish the baseline **before** you change anything, then prove you did not
regress it.

```bash
V=apps/synthesus/.venv/bin/python

$V -m pytest -q tests/forge_render
$V -m pytest -q tests
(cd apps/synthesus/desktop && $V -m pytest -q .)
node --check apps/synthesus/desktop/script.js

# forge native core must rebuild clean
make -C services/forge_render/native
```

Known-good at time of writing: `tests/forge_render` **24 passed**; desktop forge
tests (`test_forge_endpoint.py test_forge_wiring.py`) **40 passed**. The prior
brief cites **142** (desktop + forge_render) and **~520** full-suite —
**measure, do not assume**, and report the number you actually saw.
`test_desktop_security.py` may fail to collect without `jwt`; that is
pre-existing.

Live render check through the running stack:

```bash
set -a; . apps/synthesus/synthesus.env; set +a
curl -s -H "X-API-Key: $SYNTHESUS_API_KEY" -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:5011/api/forge/render \
  -d '{"code":"SF1.0.6.35.285.60.0.42","width":256,"height":256,"quality":48}' \
  -D - -o /tmp/forge.png | grep -i x-forge && file /tmp/forge.png
```

Expect `x-forge-native: 1`. A `0` means the slow Python path is serving and the
native core did not load.

> **Bump the `?v=` cache-bust** on `styles.css` / `script.js` in `index.html`
> whenever you change either. A prior session shipped three rounds of invisible
> CSS by forgetting this, and it will waste your reviewer's time before it
> wastes yours.

---

## 6. DELIVERABLE

* **One branch per workstream, branched from `main`, each with its own PR.**
  Small reviewable PRs beat one large one. Do not merge without review.
* An `AGENT_LOG.md` entry per PR in the established style, ending with an
  explicit **HONEST GAPS** section listing what you did *not* verify.
* If you could not render or visually confirm a UI change, write **"the page was
  never rendered"** plainly. Do not imply otherwise.
* Do not check a `FINISH_CHECKLIST.md` box. That file is not yours to edit.
* Commit trailer: `Co-Authored-By: <your agent name>`

**If you run short of time, finish Workstream A rather than starting all four.**
A reachable Recipe v2 is worth more than four half-wired features.
