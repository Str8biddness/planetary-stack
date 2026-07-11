#!/usr/bin/env bash
# Safe sync of git tree → install dir WITHOUT destroying venv/env/user data.
# Usage: ./tools/redeploy_install.sh [SOURCE_DIR] [INSTALL_DIR]
set -euo pipefail

SRC="${1:-$HOME/synthesus}"
DEST="${2:-$HOME/.local/share/synthesus}"

c()  { printf "\033[1;36m%s\033[0m\n" "$*"; }
ok() { printf "\033[1;32m  ✓ %s\033[0m\n" "$*"; }
warn(){ printf "\033[1;33m  ! %s\033[0m\n" "$*"; }
die(){ printf "\033[1;31m  ✗ %s\033[0m\n" "$*" >&2; exit 1; }

[ -d "$SRC/runtime" ] && [ -d "$SRC/desktop" ] || die "SRC must contain runtime/ and desktop/ ($SRC)"
mkdir -p "$DEST"

c "Redeploy Synthesus code → install dir"
echo "  source:  $SRC"
echo "  dest:    $DEST"
echo "  preserves: .venv, synthesus.env, settings.json, data/"
echo

# Stop runtime if running (ok if not)
pkill -f "production_server.py" 2>/dev/null || true
sleep 1

EXCLUDES=(--exclude '.venv' --exclude 'venv' --exclude '__pycache__' --exclude '*.pyc'
          --exclude '.git' --exclude 'node_modules' --exclude 'synthesus.env'
          --exclude 'settings.json' --exclude 'data/' --exclude 'build/')

rsync -a --delete "${EXCLUDES[@]}" "$SRC/runtime/" "$DEST/runtime/"
ok "runtime/ synced"
rsync -a --delete "${EXCLUDES[@]}" "$SRC/desktop/" "$DEST/desktop/"
ok "desktop/ synced"

# Optional: copy tools (enable_gpu, smoke, redeploy)
mkdir -p "$DEST/tools"
rsync -a "$SRC/tools/" "$DEST/tools/" 2>/dev/null || true

# Preserve / create env secrets
if [ ! -f "$DEST/synthesus.env" ]; then
  warn "no synthesus.env — generating API key + human session secret"
  KEY="$(python3 -c 'import secrets; print("syn_"+secrets.token_urlsafe(32))')"
  HSEC="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  cat > "$DEST/synthesus.env" <<ENV
SYNTHESUS_API_KEY=$KEY
SYNTHESUS_MODEL=${SYNTHESUS_MODEL:-llama3.2:3b}
SYNTHESUS_HOST=127.0.0.1
SYNTHESUS_HUMAN_SESSION_SECRET=$HSEC
ENV
  chmod 600 "$DEST/synthesus.env"
else
  # Ensure human session secret exists without clobbering API key
  if ! grep -q '^SYNTHESUS_HUMAN_SESSION_SECRET=' "$DEST/synthesus.env" 2>/dev/null; then
    HSEC="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
    echo "SYNTHESUS_HUMAN_SESSION_SECRET=$HSEC" >> "$DEST/synthesus.env"
    ok "appended SYNTHESUS_HUMAN_SESSION_SECRET to existing synthesus.env"
  else
    ok "synthesus.env preserved (includes human session secret)"
  fi
fi

# Point kernel bin if built in source tree
if [ -x "$SRC/runtime/packages/kernel/build/zo_kernel" ]; then
  mkdir -p "$DEST/runtime/packages/kernel/build"
  cp -a "$SRC/runtime/packages/kernel/build/zo_kernel" "$DEST/runtime/packages/kernel/build/zo_kernel"
  ok "copied zo_kernel IPC binary"
  if ! grep -q '^SYNTHESUS_KERNEL_BIN=' "$DEST/synthesus.env" 2>/dev/null; then
    echo "SYNTHESUS_KERNEL_BIN=$DEST/runtime/packages/kernel/build/zo_kernel" >> "$DEST/synthesus.env"
  fi
fi

c "Done. Restart with: synthesus   OR   $DEST/run_runtime.sh"
echo "  Do NOT re-run install.sh unless you want a full venv rebuild."
