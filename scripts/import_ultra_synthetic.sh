#!/usr/bin/env bash
# Import full Ultra organ synthetic dumps into a LOCAL gitignored path.
# Never commit packages/core/synthetic_data/ (closed moat — see .gitignore).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${1:-$HOME/synthesus-ultra-repo}"
# fallbacks
if [[ ! -d "$SRC/packages/core/synthetic_data" ]]; then
  if [[ -d "$HOME/aios_framework/packages/core/synthetic_data" ]]; then
    SRC="$HOME/aios_framework"
  elif [[ -d "$HOME/synthesus-ultra/packages/core/synthetic_data" ]]; then
    SRC="$HOME/synthesus-ultra"
  fi
fi

SRC_DATA="$SRC/packages/core/synthetic_data"
DST="$ROOT/packages/core/synthetic_data"

if [[ ! -d "$SRC_DATA" ]]; then
  echo "ERROR: Ultra synthetic_data not found under: $SRC" >&2
  echo "Clone: git clone git@github.com:Str8biddness/synthesus-ultra-.git ~/synthesus-ultra-repo" >&2
  exit 1
fi

mkdir -p "$DST"
echo "Copying $SRC_DATA -> $DST"
cp -a "$SRC_DATA/." "$DST/"
echo "OK: $(find "$DST" -type f | wc -l) files, $(du -sh "$DST" | awk '{print $1}')"
echo "Remember: this directory is gitignored (CLOSED MOAT)."
echo "Smoke fixtures (committed): runtime/tests/fixtures/organ_smoke/"
