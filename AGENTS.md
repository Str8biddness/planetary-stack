# Synthesus Knowledge Cloud Repository

## Purpose
This repository is the standalone public data-plane and rebuild pipeline for the Synthesus Knowledge Cloud. It is not the Synthesus runtime itself; it carries the immutable runtime artifacts, integrity manifests, source declarations, grounding corpora, pattern banks, synthetic lore generation scripts, and lightweight client tooling needed by local Synthesus installs.

## Operating Rules
- Keep `artifacts/manifest.json` as the runtime artifact integrity source of truth.
- Keep `manifests/source_manifest.json` current when changing source/pipeline/pattern/synthetic/support planes.
- Do not edit binary artifacts by hand. Replace the bundle, regenerate manifests, then validate.
- Large generated artifacts are intentionally tracked here so local Synthesus users can bootstrap without rebuilding the corpus.
- The public hosted mirror should stay aligned with `artifacts/`: `https://zo.pub/syntech/synthesus-knowledge`.
- If artifact paths change, update `README.md`, `docs/INTEGRATION.md`, and `scripts/sync_knowledge_cloud.py` together.
- Source manifests live in `sources/`; do not add raw third-party archives unless redistribution/license terms are clear.
- Treat `patterns/`, `grounding_corpus/`, `synthetic/`, and `support_models/` as rebuild/audit planes, not the minimal runtime download path.

## Validation
Run before publishing changes:

```bash
python scripts/validate_bundle.py --root artifacts
python scripts/validate_source_planes.py --root .
python scripts/build_source_manifest.py --root .
python scripts/sync_knowledge_cloud.py --dest /tmp/synthesus-kc-smoke --base-url file://$PWD/artifacts
```

## Architecture Boundary
The artifact repo owns the data supply chain. The Synthesus runtime repo should consume the cloud through manifest-verified sync and should not be the only place where rebuild logic/data exists.
