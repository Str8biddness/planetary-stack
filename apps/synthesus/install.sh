#!/usr/bin/env bash
# ==========================================================================
# Synthesus — installer for the local, private AI desktop.
#
# Run this from inside an unpacked Synthesus release (a directory that
# contains ./desktop and ./runtime — see build_release.sh). It sets up
# everything a fresh machine needs and leaves you with a `synthesus` command.
#
#   ./install.sh
#
# What it does (and what needs root — stated up front, no surprises):
#   * system packages (needs sudo): python venv/pip, git, curl, and the
#     pywebview GTK/WebKit backend so the desktop window can render
#   * Ollama + the local model (Ollama's own installer uses sudo)
#   * a private Python venv with the Synthesus deps (no root)
#   * a per-install API key (no root)
#   * a `synthesus` launcher + app menu entry (no root)
# ==========================================================================
set -euo pipefail

# ---- config (override via env) -------------------------------------------
SYNTHESUS_HOME="${SYNTHESUS_HOME:-$HOME/.local/share/synthesus}"
SYNTHESUS_MODEL="${SYNTHESUS_MODEL:-llama3.2:3b}"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

c()  { printf "\033[1;36m%s\033[0m\n" "$*"; }   # cyan step
ok() { printf "\033[1;32m  ✓ %s\033[0m\n" "$*"; }
warn(){ printf "\033[1;33m  ! %s\033[0m\n" "$*"; }
die(){ printf "\033[1;31m  ✗ %s\033[0m\n" "$*" >&2; exit 1; }

c "Synthesus installer"
echo "  install dir: $SYNTHESUS_HOME"
echo "  model:       $SYNTHESUS_MODEL"
echo

# ---- 0. locate the release code ------------------------------------------
[ -d "$SRC_DIR/desktop" ] && [ -d "$SRC_DIR/runtime" ] \
  || die "run this from an unpacked Synthesus release (expected ./desktop and ./runtime next to install.sh)"

# ---- 1. OS / package manager --------------------------------------------
if ! command -v apt-get >/dev/null 2>&1; then
  die "this installer targets Debian/Ubuntu/Mint (apt). For other distros, install the deps in README manually."
fi

# ---- 2. system packages (sudo) ------------------------------------------
c "1/6  System packages (needs sudo)"
# Runtime GTK/WebKit libs for pywebview + the -dev headers pip needs to BUILD
# pygobject/pycairo from source, + zstd (Ollama's installer needs it), + a compiler.
SYS_PKGS="python3 python3-venv python3-pip python3-dev git curl zstd gcc pkg-config zenity util-linux \
python3-gi python3-gi-cairo gir1.2-gtk-3.0 libcairo2-dev libgirepository1.0-dev"
# WebKit GTK: package name differs across releases (4.1 newer, 4.0 older)
if apt-cache show gir1.2-webkit2-4.1 >/dev/null 2>&1; then SYS_PKGS="$SYS_PKGS gir1.2-webkit2-4.1"; else SYS_PKGS="$SYS_PKGS gir1.2-webkit2-4.0"; fi
sudo apt-get update -qq
sudo apt-get install -y -qq $SYS_PKGS
ok "system packages installed"

# ---- 3. Ollama + model ---------------------------------------------------
c "3/6  Ollama + local model"
if ! command -v ollama >/dev/null 2>&1; then
  warn "Ollama not found — installing (uses sudo)"
  curl -fsSL https://ollama.com/install.sh | sh
fi
command -v ollama >/dev/null 2>&1 || die "Ollama install failed — see https://ollama.com/download"
# make sure the daemon is up, then pull the model (idempotent — skips if present)
ollama list >/dev/null 2>&1 || (nohup ollama serve >/dev/null 2>&1 & sleep 3)
if ollama list 2>/dev/null | grep -q "${SYNTHESUS_MODEL%%:*}"; then
  ok "model $SYNTHESUS_MODEL already present"
else
  echo "  pulling $SYNTHESUS_MODEL (~2GB, one time)…"
  ollama pull "$SYNTHESUS_MODEL"
  ok "model pulled"
fi

# ---- 3b. GPU autodetection (NVIDIA) ------------------------------------
# Principle: if a GPU + driver is present, Ollama/llama.cpp uses it on its own.
# We DETECT + point at driver setup — we do NOT write load-balancing code.
c "3b/6  GPU detection (Ollama acceleration)"
_gpu_detect_ollama() {
  # PCI NVIDIA display/3D devices (same idea as: lspci | grep -Ei 'vga|3d' | grep -i nvidia)
  local pci_nvidia=""
  if command -v lspci >/dev/null 2>&1; then
    pci_nvidia="$(lspci 2>/dev/null | grep -Ei 'vga|3d|display' | grep -i nvidia || true)"
  fi

  local smi_ok=0
  if command -v nvidia-smi >/dev/null 2>&1; then
    if nvidia-smi -L >/dev/null 2>&1; then
      smi_ok=1
    fi
  fi

  if [ -n "$pci_nvidia" ] && [ "$smi_ok" -eq 1 ]; then
    ok "GPU detected and usable — Ollama will use it."
    echo "  nvidia-smi:"
    nvidia-smi -L 2>/dev/null | sed 's/^/    /' || true
    echo "  (llama.cpp offloads layers automatically — no extra config required)"
    return 0
  fi

  if [ -n "$pci_nvidia" ] && [ "$smi_ok" -eq 0 ]; then
    warn "NVIDIA GPU present but drivers are not usable (nvidia-smi failed)."
    echo "$pci_nvidia" | sed 's/^/    PCI: /'
    if command -v nvidia-smi >/dev/null 2>&1; then
      echo "    nvidia-smi: installed but cannot talk to the driver"
    else
      echo "    nvidia-smi: not installed"
    fi
    echo
    echo "  → Chat will run on CPU until GPU drivers are installed."
    echo "  → Enable GPU acceleration (recommended):"
    if [ -x "$SRC_DIR/tools/enable_gpu.sh" ]; then
      echo "      $SRC_DIR/tools/enable_gpu.sh"
    else
      echo "      ./tools/enable_gpu.sh   # from the Synthesus release directory"
    fi
    echo "    That script detects your exact GPU + distro and prints the precise"
    echo "    nvidia-driver / CUDA install steps, then verifies Ollama sees the GPU."
    return 0
  fi

  # No NVIDIA device matching the detect path (other GPUs are not claimed as usable here).
  echo "  No NVIDIA GPU detected — Ollama will run in CPU mode (expected on many machines)."
  echo "  Tip: if you later add an NVIDIA GPU, re-run: ./tools/enable_gpu.sh"
  return 0
}
_gpu_detect_ollama

# ---- 4. copy code + create venv -----------------------------------------
c "4/6  Installing app + Python environment"
mkdir -p "$SYNTHESUS_HOME"
rsync -a --delete --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' \
      --exclude '.venv' --exclude 'venv' --exclude 'node_modules' \
      "$SRC_DIR/desktop/" "$SYNTHESUS_HOME/desktop/"
rsync -a --delete --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' \
      --exclude '.venv' --exclude 'venv' --exclude 'node_modules' \
      "$SRC_DIR/runtime/" "$SYNTHESUS_HOME/runtime/"
mkdir -p "$SYNTHESUS_HOME/tools"
install -m 0755 "$SRC_DIR/launch.sh" "$SYNTHESUS_HOME/launch.sh"
install -m 0755 "$SRC_DIR/tools/sudo_askpass.sh" \
  "$SYNTHESUS_HOME/tools/sudo_askpass.sh"
install -m 0755 "$SRC_DIR/tools/configure_agentic_elevation.sh" \
  "$SYNTHESUS_HOME/tools/configure_agentic_elevation.sh"

python3 -m venv "$SYNTHESUS_HOME/.venv"
VPIP="$SYNTHESUS_HOME/.venv/bin/pip"
"$VPIP" install --quiet --upgrade pip
# Install CPU-only PyTorch FIRST so requirements.txt's unpinned torch>=2.1.0 does NOT
# pull the multi-GB CUDA build (which fills small disks and fails the whole install).
# Inference runs through Ollama, not torch, so the CPU wheel is all that's needed.
"$VPIP" install --quiet torch --index-url https://download.pytorch.org/whl/cpu \
  || warn "CPU torch install failed — some heavy ML features may be degraded (core chat unaffected)"
# runtime deps (from its requirements) + the desktop shell deps
if [ -f "$SYNTHESUS_HOME/runtime/requirements.txt" ]; then
  "$VPIP" install --quiet -r "$SYNTHESUS_HOME/runtime/requirements.txt" \
    || warn "some ML requirements failed (torch/qiskit/transformers/etc.) — core chat still works; the critical deps are installed explicitly below"
fi
# NOTE: pin pygobject<3.52 — 3.52+ requires girepository-2.0, but Debian 12
# (bookworm) only ships girepository-1.0, so the latest pygobject fails to build
# there. <3.52 builds against 1.0 and works on both bookworm and Ubuntu 24.04.
# flask-cors (shell CORS) and PyJWT (accounts.py) are HARD boot requirements — a fresh
# install without them dies with ModuleNotFoundError before the app can start.
"$VPIP" install --quiet faiss-cpu fastembed fastapi "uvicorn[standard]" flask flask-cors PyJWT requests \
        websockets pywebview "pygobject<3.52" numpy Pillow pydantic sqlalchemy asyncpg httpx onnxruntime \
        "scikit-learn==1.8.0"
ok "environment ready (scikit-learn pinned 1.8.0 for SwarmEmbedder pickle compat)"

# ---- 5. per-install key + human-session secret ---------------------------
c "5/6  Generating private per-install secrets"
KEY="$(python3 -c 'import secrets; print("syn_"+secrets.token_urlsafe(32))')"
# Human attestation boundary: desktop shell injects this as X-Synthesus-Human-Session.
# NEVER expose to frontend JS. Same value must be visible to runtime + shell.
HUMAN_SESSION_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
mkdir -p "$SYNTHESUS_HOME"
# Preserve existing secrets if re-running install over an existing tree.
if [ -f "$SYNTHESUS_HOME/synthesus.env" ]; then
  # shellcheck disable=SC1090
  set -a; . "$SYNTHESUS_HOME/synthesus.env"; set +a
  KEY="${SYNTHESUS_API_KEY:-$KEY}"
  HUMAN_SESSION_SECRET="${SYNTHESUS_HUMAN_SESSION_SECRET:-$HUMAN_SESSION_SECRET}"
  warn "preserving existing synthesus.env secrets (API key / human session)"
fi
cat > "$SYNTHESUS_HOME/synthesus.env" <<ENV
# Auto-generated at install. Do not share. Never ship to the browser.
SYNTHESUS_API_KEY=$KEY
SYNTHESUS_MODEL=$SYNTHESUS_MODEL
SYNTHESUS_HOST=127.0.0.1
# The current published Knowledge Cloud bundle is not release-valid. Keep
# network bootstrap opt-in until a dimension-consistent signed bundle ships.
SYNTHESUS_KNOWLEDGE_SYNC_MODE=off
# Memory-verification human proof (desktop shell → runtime mint). Local only.
SYNTHESUS_HUMAN_SESSION_SECRET=$HUMAN_SESSION_SECRET
# Optional: absolute path to C++ kernel IPC binary (zo_kernel)
# SYNTHESUS_KERNEL_BIN=$SYNTHESUS_HOME/runtime/packages/kernel/build/zo_kernel
ENV
chmod 600 "$SYNTHESUS_HOME/synthesus.env"
ok "unique secrets written to synthesus.env (API key + human session; localhost only)"

# ---- 6. launcher + menu entry -------------------------------------------
c "6/6  Launcher"
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/synthesus" <<LAUNCH
#!/usr/bin/env bash
set -euo pipefail
export SYNTHESUS_HOME="\${SYNTHESUS_HOME:-$SYNTHESUS_HOME}"
exec "\$SYNTHESUS_HOME/launch.sh" "\$@"
LAUNCH
# the runtime boot helper the desktop calls
cat > "$SYNTHESUS_HOME/run_runtime.sh" <<RUNTIME
#!/usr/bin/env bash
cd "$SYNTHESUS_HOME/runtime" || exit 1
set -a; . "$SYNTHESUS_HOME/synthesus.env"; set +a
export PYTHONPATH="packages/reasoning:packages/kernel:packages/knowledge:packages/core:packages:."
export PORT=5010 SYNTHESUS_CGPU_REALIZER=llm SYNTHESUS_EMBEDDER=semantic

# --- Ollama readiness: chat needs a live model at :11434 or it silently
#     falls back to canned responses. Ensure it is up and the model is pulled.
SYNTHESUS_MODEL="\${SYNTHESUS_MODEL:-llama3.2:3b}"
if ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "Ollama not reachable at http://localhost:11434 — starting it..."
  ollama serve >/dev/null 2>&1 &
  for _ in \$(seq 1 15); do
    curl -s http://localhost:11434/api/tags >/dev/null 2>&1 && break
    sleep 1
  done
  if ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "Warning: Ollama still not responding after 15s; chat may use canned responses."
  fi
fi
if ! ollama list 2>/dev/null | grep -q "\$SYNTHESUS_MODEL"; then
  echo "Pulling \$SYNTHESUS_MODEL (first-time, ~2GB)…"
  ollama pull "\$SYNTHESUS_MODEL"
fi

exec "$SYNTHESUS_HOME/.venv/bin/python" packages/api/production_server.py "\$@"
RUNTIME
chmod +x "$BIN_DIR/synthesus" "$SYNTHESUS_HOME/run_runtime.sh"

# app menu entry
APPS="$HOME/.local/share/applications"; mkdir -p "$APPS"
cat > "$APPS/synthesus.desktop" <<DESK
[Desktop Entry]
Name=Synthesus
Comment=Local, private AI desktop
Exec=$BIN_DIR/synthesus --standard
Terminal=false
Type=Application
Categories=Utility;
DESK
cat > "$APPS/synthesus-agentic.desktop" <<DESK
[Desktop Entry]
Name=Synthesus Agentic
Comment=Local AI desktop with one-time, session-scoped sudo authorization
Exec=$BIN_DIR/synthesus --agentic
Terminal=false
Type=Application
Categories=Development;
DESK
ok "installed"

# ---- 7. self-check: does the REAL path work, or will it degrade to fallbacks? ----
# Fallbacks (canned replies, seed text) exist ONLY to prevent a crash — they are not the
# product. This check tells you BEFORE you launch whether you'll get the real thing.
c "Self-check — verifying the real (non-fallback) path"
SELFTEST_FAIL=0
"$SYNTHESUS_HOME/.venv/bin/python" - <<'PYCHECK' || SELFTEST_FAIL=1
import importlib.util, sys
critical = ["fastapi","flask","flask_cors","jwt","requests","numpy","pydantic",
            "sqlalchemy","httpx","faiss","fastembed","onnxruntime"]
missing = [m for m in critical if importlib.util.find_spec(m) is None]
if missing:
    print("  MISSING deps (chat/grounding WILL degrade): " + ", ".join(missing))
    print("  fix: ~/.local/share/synthesus/.venv/bin/pip install " + " ".join(missing))
    sys.exit(1)
print("  all critical Python deps import cleanly")
PYCHECK
[ "$SELFTEST_FAIL" = 1 ] && warn "critical deps missing (see above) — the app would fall back instead of working properly"

if curl -s http://localhost:11434/api/tags 2>/dev/null | grep -q "$SYNTHESUS_MODEL"; then
  ok "Ollama reachable + $SYNTHESUS_MODEL present — real LLM path ready"
else
  warn "Ollama/model not ready — chat will use the canned fallback until 'ollama pull $SYNTHESUS_MODEL' succeeds"
  SELFTEST_FAIL=1
fi

if [ "$SELFTEST_FAIL" = 0 ]; then
  ok "SELF-CHECK PASSED — you'll get the real product, not fallbacks"
else
  warn "SELF-CHECK found gaps above — resolve them, then re-run, so you're not stuck on fallbacks"
fi

echo
c "Done."
echo "  Launch:   $BIN_DIR/synthesus   (or find 'Synthesus' in your app menu)"
case ":$PATH:" in *":$BIN_DIR:"*) : ;; *) warn "add $BIN_DIR to PATH, or run it by full path";; esac
echo "  Your data + key live in: $SYNTHESUS_HOME"
