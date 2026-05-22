# Package and CLI

The Knowledge Cloud repo now exposes a self-contained Python package:

```bash
python -m synthesus_knowledge_cloud --help
```

Optional editable install:

```bash
python -m pip install -e .
synthesus-kc --help
```

## Commands

Validate the compiled runtime bundle:

```bash
python -m synthesus_knowledge_cloud validate --root artifacts
```

Validate source, pipeline, pattern, synthetic, grounding, and support planes:

```bash
python -m synthesus_knowledge_cloud validate-sources --root .
```

Rebuild the source-plane manifest:

```bash
python -m synthesus_knowledge_cloud build-source-manifest --root . --output manifests/source_manifest.json
```

Inspect a bounded build profile:

```bash
python -m synthesus_knowledge_cloud inspect-profile profiles/public-base.yaml
```

Sync the runtime bundle from the hosted mirror:

```bash
python -m synthesus_knowledge_cloud sync --dest ./data --base-url https://zo.pub/syntech/synthesus-knowledge
```

The legacy scripts in `scripts/` are now thin wrappers around this package so older workflows keep working.
