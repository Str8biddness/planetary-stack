# Rebuilding the Knowledge Cloud

This repo now preserves the runtime bundle plus the rebuild supply chain. The high-level flow is:

```text
source manifests
→ fetch/cache upstream datasets
→ normalize KnowledgeEntry records
→ generate synthetic lore/patterns/transitions
→ build KNDatabase + FAISS
→ generate manifests
→ publish repo + zo.pub mirror
```

## Minimal validation

```bash
python scripts/validate_bundle.py --root artifacts
python scripts/validate_source_planes.py --root .
python scripts/build_source_manifest.py --root .
```

## Runtime bundle smoke test

```bash
python scripts/sync_knowledge_cloud.py \
  --dest /tmp/synthesus-kc-smoke \
  --base-url "file://$PWD/artifacts"
python scripts/validate_bundle.py --root /tmp/synthesus-kc-smoke
```

## Source-aware rebuild path

The copied pipeline modules are intentionally close to the Synthesus runtime modules so they can be refactored into a proper package without losing behavior.

Primary modules:

- `pipelines/ingest/kaggle_loader.py`
- `pipelines/build/kn_populator.py`
- `pipelines/build/run_population.py`
- `pipelines/build/swarm_embedder.py`
- `synthetic/lore_forge/lore_forge.py`
- `synthetic/generation_scripts/*.py`

Current caveat: some copied scripts still assume the Synthesus runtime tree is importable. The artifact repo is now source-complete enough to audit and version those scripts, but the next hardening step is to remove runtime-relative imports and convert this into an installable package.

## Publication

After artifacts are rebuilt and validated:

```bash
git add -A
git commit -m "Refresh knowledge cloud bundle"
git push origin main
zopub sync synthesus-knowledge artifacts
```

The public mirror remains:

```text
https://zo.pub/syntech/synthesus-knowledge
```
