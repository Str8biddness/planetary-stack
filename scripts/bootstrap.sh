#!/usr/bin/env bash
#
# bootstrap.sh — reproducible developer bootstrap for the Planetary Stack.
#
# Checklist gate F-010 (reproducible bootstrap + pinned versions).
#
# What it does, idempotently, on a supported Linux host:
#   1. Verifies required host tooling exists (fails closed if any is missing).
#   2. Verifies the Python interpreter meets the pinned minimum (>=3.12).
#   3. Creates or reuses a project virtual environment.
#   4. Installs the exact Python dependency pins from versions.lock.
#   5. Runs `make doctor` so the environment self-reports readiness.
#
# Safe to re-run: an existing venv is reused, pip installs are idempotent, and
# nothing outside the venv / repo is mutated. Any missing required tool aborts
# with a clear message before changes are made.
#
# Environment overrides:
#   PYTHON     interpreter used to create the venv (default: python3)
#   VENV_DIR   virtual environment location (default: <repo>/.venv)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOCK_FILE="$REPO_ROOT/versions.lock"

PYTHON="${PYTHON:-python3}"
VENV_DIR="${VENV_DIR:-$REPO_ROOT/.venv}"

PYTHON_MIN_MAJOR=3
PYTHON_MIN_MINOR=12

log()  { printf '[bootstrap] %s\n' "$*"; }
fail() { printf '[bootstrap] ERROR: %s\n' "$*" >&2; exit 1; }

# --- 1. Required host tooling -------------------------------------------------
# These must exist before we touch anything. Fail closed with a clear message.
require_tool() {
    local tool="$1"
    if ! command -v "$tool" >/dev/null 2>&1; then
        fail "required tool '$tool' is not installed or not on PATH. Install it and re-run."
    fi
    log "found required tool: $tool ($(command -v "$tool"))"
}

log "repository root: $REPO_ROOT"

[[ -f "$LOCK_FILE" ]] || fail "versions.lock not found at $LOCK_FILE"

require_tool git
require_tool make
require_tool g++
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    fail "required Python interpreter '$PYTHON' not found. Set PYTHON=/path/to/python3 and re-run."
fi
log "found required Python: $PYTHON ($(command -v "$PYTHON"))"

# --- 2. Python version floor --------------------------------------------------
if ! "$PYTHON" -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= ($PYTHON_MIN_MAJOR, $PYTHON_MIN_MINOR) else 1)"; then
    detected="$("$PYTHON" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null || echo unknown)"
    fail "Python >= ${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR} required (pyproject requires-python >=3.12); '$PYTHON' is $detected."
fi
log "Python version OK: $("$PYTHON" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])')"

# --- 3. Virtual environment (create or reuse) ---------------------------------
VENV_PY="$VENV_DIR/bin/python"
if [[ -x "$VENV_PY" ]]; then
    log "reusing existing virtual environment: $VENV_DIR"
else
    log "creating virtual environment: $VENV_DIR"
    "$PYTHON" -m venv "$VENV_DIR"
fi
[[ -x "$VENV_PY" ]] || fail "virtual environment python not found at $VENV_PY after setup."

# --- 4. Install pinned dependencies from versions.lock ------------------------
# Extract exactly the lines between the BEGIN/END pip-requirements markers.
REQ_TMP="$(mktemp "${TMPDIR:-/tmp}/planetary-bootstrap-reqs.XXXXXX")"
trap 'rm -f "$REQ_TMP"' EXIT

awk '
    /^# BEGIN pip-requirements$/ { grab = 1; next }
    /^# END pip-requirements$/   { grab = 0 }
    grab && $0 !~ /^[[:space:]]*#/ && $0 !~ /^[[:space:]]*$/ { print }
' "$LOCK_FILE" > "$REQ_TMP"

[[ -s "$REQ_TMP" ]] || fail "no pinned requirements found between the pip-requirements markers in versions.lock."

log "pinned dependencies to install:"
while IFS= read -r line; do log "  - $line"; done < "$REQ_TMP"

log "upgrading pip inside the venv"
"$VENV_PY" -m pip install --upgrade pip >/dev/null

log "installing pinned dependencies (idempotent)"
"$VENV_PY" -m pip install -r "$REQ_TMP"

# --- 5. Environment self-check ------------------------------------------------
log "running 'make doctor'"
make -C "$REPO_ROOT" doctor PYTHON="$VENV_PY"

log "bootstrap complete. Activate with: source \"$VENV_DIR/bin/activate\""
