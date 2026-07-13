# Synthesus Ultra archive — what we took into launch

**Private source:** `git@github.com:Str8biddness/synthesus-ultra-.git`  
**Inventory tip:** `db72d05` (2026-06-28) — see session inventory report.

## Bottom line

Ultra is the **seed monorepo**. Launch (`Str8biddness/synthesus`) is the **successor** for
SI image, formant voice, desktop WebOS, Pattern-ISA AIVM, and RAG hardening.
Do **not** re-port Ultra’s thin `vsa_pipeline_image` over public `image_service`.

## Imported into this repo (valuable, local-first)

| Path | What |
|------|------|
| `benchmarks/fixtures/ultra_si_proof/` | Real PNG + early larynx WAV from Ultra runs |
| `runtime/tests/fixtures/organ_smoke/` | Small smoke slices of organ training JSON |
| `scripts/import_ultra_synthetic.sh` | Pulls full proprietary dumps **locally** (gitignored) |
| `runtime/tests/test_organism_conversation_smoke.py` | Locks conversation-organism ability demo |

## Kept out of git (closed moat)

Full organ training dumps live under Ultra:

`packages/core/synthetic_data/*.json` (~6.7 MB)

`.gitignore` already blocks `packages/core/synthetic_data/`. To train organs locally:

```bash
./scripts/import_ultra_synthetic.sh ~/synthesus-ultra-repo
# or: ./scripts/import_ultra_synthetic.sh ~/aios_framework
```

## Do not port from Ultra (anti-moat / superseded)

- Multi-cloud rclone “software-defined hardware” as default product path  
- Parameter-cloud **required** HTTP without offline fallback  
- Replacing public formant / image_service with Ultra ancestors  
- Firebase / cloud-primary AIVM blueprints  

## Optional later harvest (dirty local trees only)

`~/aios_framework` may contain uncommitted experiments (`mesh_coordinator`, `vsd`, …)
that are **not** on Ultra `origin/main`. Review before any merge.
