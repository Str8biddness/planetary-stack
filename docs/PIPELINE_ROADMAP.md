# Pipeline Roadmap

## Current state

The repository now has the full Knowledge Cloud shape:

- compiled runtime artifacts
- source manifests
- ingestion/build/publish pipeline copies
- grounding corpora
- character/global pattern banks
- synthetic lore and transition generation scripts
- support models/checkpoints

## Next hardening steps

1. Convert copied pipeline modules into an installable package, e.g. `synthesus_kc/`.
2. Remove imports that depend on the main Synthesus runtime checkout.
3. Add a single `kc` CLI:
   - `kc fetch`
   - `kc generate-synthetic`
   - `kc build`
   - `kc validate`
   - `kc publish`
4. Add dataset license gates before enabling Hugging Face/Kaggle raw-source mirroring.
5. Add rebuild provenance into `artifacts/manifest.json`:
   - source revisions
   - sample sizes
   - transform versions
   - embedding parameters
6. Add query-quality benchmark set before publishing refreshed FAISS bundles.

## Architectural rule

The artifact repo should own the data supply chain. The Synthesus runtime repo should consume the cloud, not secretly contain the only rebuild path.
