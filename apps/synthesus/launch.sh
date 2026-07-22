#!/usr/bin/env bash
# Launch Synthesus in standard mode or with explicitly authorized, session-scoped
# agentic sudo elevation.
set -euo pipefail

SOURCE_HOME="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SYNTHESUS_HOME="${SYNTHESUS_HOME:-$SOURCE_HOME}"
AGENTIC_ELEVATION="${SYNTHESUS_AGENTIC_ELEVATION:-0}"
APP_PID=""
KEEPALIVE_PID=""
ELEVATION_ACTIVE=0

usage() {
  cat <<'EOF'
Usage: synthesus [--agentic|--standard]

  --standard  Launch the normal unprivileged desktop (default).
  --agentic   Ask for the account password once, keep the sudo timestamp valid
              only while Synthesus is running, and revoke it on exit.
EOF
}

while (($#)); do
  case "$1" in
    --agentic|--agentic-elevation)
      AGENTIC_ELEVATION=1
      ;;
    --standard)
      AGENTIC_ELEVATION=0
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown Synthesus launch option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

ENV_FILE="${SYNTHESUS_ENV_FILE:-$SYNTHESUS_HOME/synthesus.env}"
if [[ ! -f "$ENV_FILE" && -f "$HOME/.local/share/synthesus/synthesus.env" ]]; then
  ENV_FILE="$HOME/.local/share/synthesus/synthesus.env"
fi
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

PYTHON_BIN="${SYNTHESUS_PYTHON:-$SYNTHESUS_HOME/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" && -x "$HOME/.local/share/synthesus/.venv/bin/python" ]]; then
  PYTHON_BIN="$HOME/.local/share/synthesus/.venv/bin/python"
fi
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3 || true)"
fi
if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  printf 'Synthesus could not find Python; set SYNTHESUS_PYTHON.\n' >&2
  exit 1
fi

export SYNTHESUS_HOME
export SYNTHESUS_RUNTIME_URL="${SYNTHESUS_RUNTIME_URL:-http://127.0.0.1:5010}"
runtime_command="$SYNTHESUS_HOME/runtime/run_runtime.sh"
if [[ -x "$SYNTHESUS_HOME/run_runtime.sh" ]]; then
  runtime_command="$SYNTHESUS_HOME/run_runtime.sh"
fi
export SYNTHESUS_RUNTIME_CMD="${SYNTHESUS_RUNTIME_CMD:-$runtime_command}"
export SYNTHESUS_PYTHON="$PYTHON_BIN"

askpass_helper="$SYNTHESUS_HOME/tools/sudo_askpass.sh"
if [[ ! -x "$askpass_helper" ]]; then
  askpass_helper="$SOURCE_HOME/tools/sudo_askpass.sh"
fi

sudo_with_prompt() {
  if [[ "${SYNTHESUS_FORCE_GUI_ASKPASS:-0}" != "1" && -t 0 ]]; then
    sudo "$@"
    return
  fi
  if [[ ! -x "$askpass_helper" ]]; then
    printf 'Agentic elevation needs a TTY or the Synthesus askpass helper.\n' >&2
    return 1
  fi
  SUDO_ASKPASS="$askpass_helper" sudo -A "$@"
}

cleanup() {
  local status=$?
  trap - EXIT INT TERM HUP
  if [[ -n "$KEEPALIVE_PID" ]]; then
    kill "$KEEPALIVE_PID" 2>/dev/null || true
    wait "$KEEPALIVE_PID" 2>/dev/null || true
  fi
  if ((ELEVATION_ACTIVE)); then
    sudo -k 2>/dev/null || true
  fi
  if [[ -n "$APP_PID" ]] && kill -0 "$APP_PID" 2>/dev/null; then
    kill "$APP_PID" 2>/dev/null || true
  fi
  exit "$status"
}
trap cleanup EXIT INT TERM HUP

if [[ "$AGENTIC_ELEVATION" == "1" ]]; then
  policy="$(sudo -n -l 2>&1 || true)"
  if ! grep -q 'timestamp_type=global' <<<"$policy" \
      || ! grep -q 'timestamp_timeout=1' <<<"$policy"; then
    cat >&2 <<EOF
Agentic elevation has not been configured for this account.

Run this one-time setup first:
  sudo "$SYNTHESUS_HOME/tools/configure_agentic_elevation.sh" --install "$USER"

This policy does not grant NOPASSWD. It shares a short sudo timestamp across
Synthesus terminal PTYs and expires one minute after refresh stops.
EOF
    exit 1
  fi

  # Always require a fresh password for this launch rather than inheriting an
  # unrelated sudo timestamp.
  sudo -k
  printf 'Synthesus agentic elevation requires one authorization for this session.\n'
  sudo_with_prompt -v

  # Prove the ticket is visible from a different PTY before starting the UI.
  if ! command -v script >/dev/null 2>&1 \
      || ! script -qefc 'sudo -n true' /dev/null >/dev/null 2>&1; then
    sudo -k 2>/dev/null || true
    printf 'Agentic elevation did not propagate to a separate terminal PTY.\n' >&2
    exit 1
  fi

  ELEVATION_ACTIVE=1
  export SYNTHESUS_AGENTIC_ELEVATION=1
  launcher_pid=$$
  (
    while kill -0 "$launcher_pid" 2>/dev/null; do
      sleep 30
      if ! sudo -n -v; then
        printf 'Synthesus agentic authorization expired; closing the session.\n' >&2
        kill -TERM "$launcher_pid" 2>/dev/null || true
        exit 1
      fi
    done
  ) &
  KEEPALIVE_PID=$!
  printf 'Synthesus agentic elevation ACTIVE; authorization is revoked on exit.\n'
else
  export SYNTHESUS_AGENTIC_ELEVATION=0
fi

# Report native acceleration state at startup. The failure mode this prevents:
# a missing compiled core is swallowed by a try/except somewhere, the app runs
# on a pure-Python fallback for months, and nobody knows why it is slow.
FORGE_SO=""
for c in "$SYNTHESUS_HOME/services/forge_render/native/libforge_core.so" \
         "$SYNTHESUS_HOME/../../services/forge_render/native/libforge_core.so"; do
  [ -f "$c" ] && FORGE_SO="$c" && break
done
if [ -n "$FORGE_SO" ]; then
  printf '[native] forge core: enabled\n'
else
  printf '[native] forge core: MISSING — rendering will be ~90x slower (build: make -C services/forge_render/native)\n'
fi
if [ -n "${SYNTHESUS_KERNEL_BIN:-}" ] && [ -x "${SYNTHESUS_KERNEL_BIN}" ]; then
  printf '[native] C++ kernel: %s\n' "$SYNTHESUS_KERNEL_BIN"
else
  printf '[native] C++ kernel: MISSING — runtime will use its Python fallback\n'
fi

cd "$SYNTHESUS_HOME/desktop"
"$PYTHON_BIN" synthesus_native_shell.py &
APP_PID=$!
wait "$APP_PID"
