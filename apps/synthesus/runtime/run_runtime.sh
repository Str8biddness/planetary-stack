#!/usr/bin/env bash
# Boot the Synthesus CHAL runtime with expansion-drive endpoints and semantic
# grounding. The checkout and its virtual environment may live anywhere.
set -euo pipefail

RUNTIME_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "$RUNTIME_DIR/.." && pwd)"
PYTHON_BIN="${SYNTHESUS_PYTHON:-$ROOT_DIR/.venv/bin/python}"

if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="$(command -v python3 || true)"
fi
if [ -z "$PYTHON_BIN" ] || [ ! -x "$PYTHON_BIN" ]; then
  echo "[run_runtime] no Python interpreter found; set SYNTHESUS_PYTHON" >&2
  exit 1
fi

cd "$RUNTIME_DIR"
export PYTHONPATH="packages/reasoning:packages/kernel:packages/knowledge:packages/core:packages:.${PYTHONPATH:+:$PYTHONPATH}"
export SYNTHESUS_API_KEY="${SYNTHESUS_API_KEY:-dev-key-change-me}"
export PORT="${PORT:-5010}"
export SYNTHESUS_CGPU_REALIZER="${SYNTHESUS_CGPU_REALIZER:-llm}"
export SYNTHESUS_EMBEDDER="${SYNTHESUS_EMBEDDER:-semantic}"
if [ -z "${SYNTHESUS_KNOWLEDGE_ROOT:-}" ]; then
  MONOREPO_KNOWLEDGE_ROOT="$ROOT_DIR/../../knowledge/knowledge-cloud/artifacts"
  if [ -f "$MONOREPO_KNOWLEDGE_ROOT/manifest.json" ]; then
    export SYNTHESUS_KNOWLEDGE_ROOT="$MONOREPO_KNOWLEDGE_ROOT"
  fi
fi
echo "[run_runtime] Synthesus CHAL runtime (drive endpoints + semantic grounding) on :${PORT}"
exec "$PYTHON_BIN" packages/api/production_server.py "$@"
