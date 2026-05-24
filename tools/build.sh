#!/usr/bin/env bash
# build.sh - Synthesus 2.0 build script
# Usage: ./build.sh [--dev] [--docker] [--test]
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

PYTHON=${PYTHON:-python3}
VENV_DIR=".venv"

log() { echo "[build.sh] $*"; }

# ------------------------------------------------------------
# Parse args
# ------------------------------------------------------------
DEV=false
DOCKER=false
TEST=false
for arg in "$@"; do
  case $arg in
    --dev)    DEV=true ;;
    --docker) DOCKER=true ;;
    --test)   TEST=true ;;
    *) echo "Unknown arg: $arg"; exit 1 ;;
  esac
done

# ------------------------------------------------------------
# Python venv
# ------------------------------------------------------------
if [ ! -d "$VENV_DIR" ]; then
  log "Creating virtual environment..."
  $PYTHON -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
log "Python: $(python --version)"

# ------------------------------------------------------------
# Install deps
# ------------------------------------------------------------
log "Installing dependencies..."
pip install --upgrade pip -q

if $DEV; then
  pip install -e ".[dev]" -q
else
  pip install -e "." -q
fi

# ------------------------------------------------------------
# Create data directories
# ------------------------------------------------------------
mkdir -p data characters

# ------------------------------------------------------------
# Tests
# ------------------------------------------------------------
if $TEST; then
  log "Running tests..."
  python -m pytest tests/ -v --tb=short
fi

# ------------------------------------------------------------
# Docker
# ------------------------------------------------------------
if $DOCKER; then
  log "Building Docker image..."
  docker build -t synthesus:latest .
  log "Docker image built: synthesus:latest"
fi

# ------------------------------------------------------------
# Done
# ------------------------------------------------------------
log "Build complete."
log "To start the API server:"
log "  source .venv/bin/activate && uvicorn api.gateway:app --reload"
