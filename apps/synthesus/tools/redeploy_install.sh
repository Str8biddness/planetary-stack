#!/usr/bin/env bash
# Safe sync of git tree → install dir WITHOUT destroying venv/env/user data.
# Usage: ./tools/redeploy_install.sh [SOURCE_DIR] [INSTALL_DIR]
set -euo pipefail
umask 077

SRC="${1:-$HOME/synthesus}"
DEST="${2:-$HOME/.local/share/synthesus}"

c()  { printf "\033[1;36m%s\033[0m\n" "$*"; }
ok() { printf "\033[1;32m  ✓ %s\033[0m\n" "$*"; }
warn(){ printf "\033[1;33m  ! %s\033[0m\n" "$*"; }
die(){ printf "\033[1;31m  ✗ %s\033[0m\n" "$*" >&2; exit 1; }

replace_env_value() {
  local path="$1" key="$2" value="$3" tmp
  tmp="$(mktemp "${path}.tmp.XXXXXX")"
  grep -v "^${key}=" "$path" > "$tmp" || true
  printf '%s=%s\n' "$key" "$value" >> "$tmp"
  chmod 600 "$tmp"
  mv -f "$tmp" "$path"
}

[ -d "$SRC/runtime" ] && [ -d "$SRC/desktop" ] || die "SRC must contain runtime/ and desktop/ ($SRC)"
if [ -L "$DEST" ]; then
  die "refusing symlinked install directory: $DEST"
fi
if [ -e "$DEST" ] && [ ! -d "$DEST" ]; then
  die "install path is not a directory: $DEST"
fi
install -d -m 0700 "$DEST"
if [ "$(stat -c '%u' "$DEST")" != "$(id -u)" ]; then
  die "install directory is not owned by the redeploy user"
fi
chmod 700 "$DEST"

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
if [ -L "$DEST/synthesus.env" ]; then
  die "refusing symlinked secret file: $DEST/synthesus.env"
fi
if [ -e "$DEST/synthesus.env" ] && [ ! -f "$DEST/synthesus.env" ]; then
  die "secret path is not a regular file: $DEST/synthesus.env"
fi
if [ ! -f "$DEST/synthesus.env" ]; then
  warn "no synthesus.env — generating API key + JWT + human session secrets"
  KEY="$(python3 -c 'import secrets; print("syn_"+secrets.token_urlsafe(32))')"
  JWTSEC="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  HSEC="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  ENV_TMP="$(mktemp "$DEST/.synthesus.env.tmp.XXXXXX")"
  trap 'rm -f "$ENV_TMP"' EXIT
  cat > "$ENV_TMP" <<ENV
SYNTHESUS_API_KEY=$KEY
SYNTHESUS_JWT_SECRET=$JWTSEC
SYNTHESUS_MODEL=${SYNTHESUS_MODEL:-llama3.2:3b}
SYNTHESUS_HOST=127.0.0.1
SYNTHESUS_KNOWLEDGE_SYNC_MODE=off
SYNTHESUS_HUMAN_SESSION_SECRET=$HSEC
ENV
  chmod 600 "$ENV_TMP"
  mv -f "$ENV_TMP" "$DEST/synthesus.env"
  trap - EXIT
else
  if [ "$(stat -c '%u' "$DEST/synthesus.env")" != "$(id -u)" ]; then
    die "secret file is not owned by the redeploy user"
  fi
  chmod 600 "$DEST/synthesus.env"
  # Ensure new secrets exist without clobbering established identities.
  CURRENT_KEY="$(sed -n 's/^SYNTHESUS_API_KEY=//p' "$DEST/synthesus.env" | tail -n 1)"
  if [ "$CURRENT_KEY" = "dev-key-change-me" ] || [ "${#CURRENT_KEY}" -lt 24 ]; then
    KEY="$(python3 -c 'import secrets; print("syn_"+secrets.token_urlsafe(32))')"
    replace_env_value "$DEST/synthesus.env" SYNTHESUS_API_KEY "$KEY"
    warn "replaced missing, known-default, or short SYNTHESUS_API_KEY"
  fi
  CURRENT_JWT="$(sed -n 's/^SYNTHESUS_JWT_SECRET=//p' "$DEST/synthesus.env" | tail -n 1)"
  if [ "$CURRENT_JWT" = "dev_secret_change_me" ] || [ "${#CURRENT_JWT}" -lt 32 ]; then
    JWTSEC="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
    replace_env_value "$DEST/synthesus.env" SYNTHESUS_JWT_SECRET "$JWTSEC"
    warn "replaced missing, known-default, or short SYNTHESUS_JWT_SECRET"
  fi
  if ! grep -q '^SYNTHESUS_HUMAN_SESSION_SECRET=' "$DEST/synthesus.env" 2>/dev/null; then
    HSEC="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
    echo "SYNTHESUS_HUMAN_SESSION_SECRET=$HSEC" >> "$DEST/synthesus.env"
    ok "appended SYNTHESUS_HUMAN_SESSION_SECRET to existing synthesus.env"
  else
    ok "synthesus.env preserved (includes JWT and human session secrets)"
  fi
  if ! grep -q '^SYNTHESUS_KNOWLEDGE_SYNC_MODE=' "$DEST/synthesus.env" 2>/dev/null; then
    echo "SYNTHESUS_KNOWLEDGE_SYNC_MODE=off" >> "$DEST/synthesus.env"
    ok "disabled automatic Knowledge Cloud sync until a valid bundle is published"
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
