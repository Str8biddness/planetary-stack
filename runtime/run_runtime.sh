#!/usr/bin/env bash
# Boot the Synthesus CHAL runtime from the c101 branch checkout, with the
# expansion-drive endpoints + semantic grounding. Uses the shared venv in
# ~/synthesus-ultra/.venv (fastembed + MiniLM ONNX already installed).
cd "$(dirname "$0")" || exit 1
export PYTHONPATH="packages/reasoning:packages/kernel:packages/knowledge:packages/core:packages:."
export SYNTHESUS_API_KEY="${SYNTHESUS_API_KEY:-dev-key-change-me}"
export PORT="${PORT:-5010}"
export SYNTHESUS_CGPU_REALIZER="${SYNTHESUS_CGPU_REALIZER:-llm}"
export SYNTHESUS_EMBEDDER="${SYNTHESUS_EMBEDDER:-semantic}"
echo "[run_runtime] Synthesus CHAL runtime (drive endpoints + semantic grounding) on :${PORT}"
exec /home/dakin/synthesus-ultra/.venv/bin/python packages/api/production_server.py "$@"
