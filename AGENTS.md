# Synthesus Knowledge Cloud Repository

## Purpose
This repository is the standalone public artifact source for the Synthesus FAISS Knowledge Cloud. It is not the Synthesus runtime itself; it carries the immutable knowledge artifacts, integrity manifest, and lightweight client tooling needed by local Synthesus installs.

## Operating Rules
- Keep `artifacts/manifest.json` as the integrity source of truth.
- Do not edit binary artifacts by hand. Replace the bundle, regenerate the manifest, then validate.
- Large generated artifacts are intentionally tracked here so local Synthesus users can bootstrap without rebuilding the corpus.
- The public hosted mirror should stay aligned with this repo: `https://zo.pub/syntech/synthesus-knowledge`.
- If artifact paths change, update `README.md`, `docs/INTEGRATION.md`, and `scripts/sync_knowledge_cloud.py` together.

## Validation
Run before publishing changes:

```bash
python scripts/validate_bundle.py --root artifacts
python scripts/sync_knowledge_cloud.py --dest /tmp/synthesus-kc-smoke --base-url file://$PWD/artifacts
```
