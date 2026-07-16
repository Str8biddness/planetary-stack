# Local Synthesus Bootstrap

`synthesus-kc bootstrap` is the one-shot UX for "I just installed Synthesus locally and want the Knowledge Cloud right now."

## Default behavior

```bash
synthesus-kc bootstrap
```

1. Resolves the target data root:
   - explicit `--target` if provided
   - else `SYNTHESUS_DATA_DIR` env var
   - else `~/.synthesus/data`
2. Resolves the mirror list (see [`MIRRORS.md`](./MIRRORS.md)).
3. Downloads every artifact in the remote manifest in parallel, with resume and failover.
4. Verifies size + SHA-256 of every artifact against the manifest.
5. Writes `.bootstrap.json` into the target recording the package version, mirrors used, the actual mirror that served the manifest, and the timestamp.

The marker file is intentionally small and human-readable so support requests can paste it directly.

## Examples

```bash
# Default location
synthesus-kc bootstrap

# Custom target
synthesus-kc bootstrap --target /var/lib/synthesus/data

# Use an internal mirror with public fallback
synthesus-kc bootstrap --mirror https://kc-staging.internal \
                      --mirror https://zo.pub/syntech/synthesus-knowledge

# Force a re-download (overwrites local cache)
synthesus-kc bootstrap --force
```

## What Synthesus does with this

A Synthesus runtime that finds `<data_root>/manifest.json` and `<data_root>/.bootstrap.json` can skip its own first-run sync entirely. If a content drift is detected later, Synthesus can call `synthesus-kc sync` (or its in-tree `knowledge_integration.cloud_sync`) against the same `<data_root>` and the mirror failover behavior is identical.
