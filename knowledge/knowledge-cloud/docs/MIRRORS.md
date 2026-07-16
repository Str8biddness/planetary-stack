# Mirrors and Failover

The Knowledge Cloud client resolves an ordered list of mirrors and fails over across them on any transient failure (404, timeout, connection reset, hash mismatch). The primary mirror is the always-online zo.pub collection.

## Precedence (highest first)

1. `--base-url` on the CLI
2. `--mirror` flags on the CLI (repeatable)
3. `SYNTHESUS_KNOWLEDGE_MIRRORS` env var (comma-separated)
4. `SYNTHESUS_KNOWLEDGE_CLOUD_URL` env var (single mirror)
5. Built-in defaults: `https://zo.pub/syntech/synthesus-knowledge`

## Examples

```bash
# Default — zo.pub
synthesus-kc sync --dest ./data

# Internal staging plus public fallback
SYNTHESUS_KNOWLEDGE_MIRRORS="https://kc-staging.internal,https://zo.pub/syntech/synthesus-knowledge" \
  synthesus-kc sync --dest ./data

# Local file:// mirror for end-to-end testing
synthesus-kc sync --dest ./data --mirror "file://$PWD/artifacts"
```

## Why GitHub `raw.githubusercontent.com` is not a default

The large artifacts in this repo are tracked via Git LFS. `raw.githubusercontent.com` returns the LFS pointer text rather than the file bytes, which would corrupt downstream consumers. Do not add it to your mirror list unless you can guarantee LFS smudge resolution on the server side.

## Resumable downloads

`sync` uses HTTP `Range` requests to resume partial downloads. The 770 MB `faiss.index` does not have to restart from byte 0 on a connection flap. If a mirror refuses `Range`, the client falls back to a clean re-download from the same mirror before trying the next one.

## Parallelism

`--workers N` (default 4) controls the concurrency. Per-artifact retries with exponential backoff are applied independently before failover to the next mirror.
