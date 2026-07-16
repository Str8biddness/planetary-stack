#!/usr/bin/env bash
# ==========================================================================
# Synthesus — enable GPU acceleration for Ollama
#
# Principle: if a GPU is present and the vendor driver works, Ollama /
# llama.cpp offloads layers automatically. This script DETECTS your GPU +
# distro, prints precise driver/CUDA install steps, and VERIFIES Ollama is
# actually using the GPU — it does NOT invent load-balancing code.
#
#   ./tools/enable_gpu.sh
#   ./tools/enable_gpu.sh --verify-only   # skip guidance; only run Ollama check
# ==========================================================================
set -euo pipefail

VERIFY_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --verify-only|-V) VERIFY_ONLY=1 ;;
    -h|--help)
      sed -n '2,14p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
  esac
done

c()    { printf "\033[1;36m%s\033[0m\n" "$*"; }
ok()   { printf "\033[1;32m  ✓ %s\033[0m\n" "$*"; }
warn() { printf "\033[1;33m  ! %s\033[0m\n" "$*"; }
bad()  { printf "\033[1;31m  ✗ %s\033[0m\n" "$*"; }
info() { printf "  %s\n" "$*"; }

c "Synthesus GPU enablement"
echo

# ---- distro --------------------------------------------------------------
detect_distro() {
  DISTRO_ID="unknown"
  DISTRO_LIKE=""
  DISTRO_VERSION=""
  DISTRO_PRETTY="unknown"
  if [ -r /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    DISTRO_ID="${ID:-unknown}"
    DISTRO_LIKE="${ID_LIKE:-}"
    DISTRO_VERSION="${VERSION_ID:-}"
    DISTRO_PRETTY="${PRETTY_NAME:-$DISTRO_ID}"
  fi
  IS_UBUNTU_FAMILY=0
  case "$DISTRO_ID" in
    ubuntu|linuxmint|pop|elementary|zorin) IS_UBUNTU_FAMILY=1 ;;
  esac
  if echo " $DISTRO_LIKE " | grep -q ' ubuntu '; then IS_UBUNTU_FAMILY=1; fi
  if echo " $DISTRO_LIKE " | grep -q ' debian ' && [ "$DISTRO_ID" = "debian" ]; then
    : # Debian proper — similar packages, slightly different driver tooling
  fi
}

# ---- GPU PCI inventory ---------------------------------------------------
detect_gpus() {
  PCI_ALL=""
  PCI_NVIDIA=""
  PCI_AMD=""
  PCI_INTEL=""
  if command -v lspci >/dev/null 2>&1; then
    PCI_ALL="$(lspci 2>/dev/null | grep -Ei 'vga|3d|display' || true)"
    PCI_NVIDIA="$(echo "$PCI_ALL" | grep -i nvidia || true)"
    # Note: do NOT match bare "ati" — it false-positives on "CorporATI on" (Intel).
    PCI_AMD="$(echo "$PCI_ALL" | grep -Ei 'AMD|Radeon|Advanced Micro Devices|\bATI\b' || true)"
    PCI_INTEL="$(echo "$PCI_ALL" | grep -i intel || true)"
  else
    warn "lspci not found — install pciutils for accurate GPU detection"
  fi
}

nvidia_smi_works() {
  command -v nvidia-smi >/dev/null 2>&1 || return 1
  nvidia-smi -L >/dev/null 2>&1
}

print_gpu_inventory() {
  c "1) Detected graphics devices"
  if [ -z "${PCI_ALL:-}" ]; then
    info "(none found via lspci VGA/3D/Display)"
  else
    echo "$PCI_ALL" | sed 's/^/  • /'
  fi
  echo
  info "Distro: $DISTRO_PRETTY ($DISTRO_ID${DISTRO_VERSION:+ $DISTRO_VERSION})"
  echo
}

# ---- Ubuntu/Mint NVIDIA driver steps -------------------------------------
# Prefer ubuntu-drivers recommended package when available.
recommend_nvidia_package() {
  RECOMMENDED_PKG=""
  if command -v ubuntu-drivers >/dev/null 2>&1; then
    # Example line: "driver   : nvidia-driver-550 - distro non-free recommended"
    local rec
    rec="$(ubuntu-drivers devices 2>/dev/null | grep -i 'recommended' | head -1 || true)"
    if [ -n "$rec" ]; then
      RECOMMENDED_PKG="$(echo "$rec" | grep -oE 'nvidia-driver-[0-9]+' | head -1 || true)"
    fi
    if [ -z "$RECOMMENDED_PKG" ]; then
      rec="$(ubuntu-drivers devices 2>/dev/null | grep -oE 'nvidia-driver-[0-9]+' | sort -u | tail -1 || true)"
      RECOMMENDED_PKG="$rec"
    fi
  fi
  # Fallback: common current series on Ubuntu 22.04/24.04 / Mint 21/22
  if [ -z "$RECOMMENDED_PKG" ]; then
    if apt-cache show nvidia-driver-550 >/dev/null 2>&1; then
      RECOMMENDED_PKG="nvidia-driver-550"
    elif apt-cache show nvidia-driver-535 >/dev/null 2>&1; then
      RECOMMENDED_PKG="nvidia-driver-535"
    else
      RECOMMENDED_PKG="nvidia-driver-535"
    fi
  fi
}

print_nvidia_ubuntu_steps() {
  recommend_nvidia_package
  c "2) NVIDIA driver install (Ubuntu / Linux Mint / Pop!_OS)"
  info "Exact GPU (PCI):"
  echo "$PCI_NVIDIA" | sed 's/^/    /'
  echo
  info "Recommended package on this machine: ${RECOMMENDED_PKG}"
  echo
  cat <<STEPS
  Run these commands (needs sudo, then a reboot):

    sudo apt-get update
    # Prefer the auto recommender when available:
    sudo ubuntu-drivers autoinstall
    # Or pin the detected series explicitly:
    sudo apt-get install -y ${RECOMMENDED_PKG}

  Optional CUDA toolkit (only if you need nvcc / extra CUDA tools —
  Ollama itself does not require the full toolkit once the driver works):

    sudo apt-get install -y nvidia-cuda-toolkit

  Then reboot so the kernel module loads:

    sudo reboot

  After reboot, verify the driver:

    nvidia-smi

  Then re-run this script to confirm Ollama uses the GPU:

    $0 --verify-only

STEPS
}

print_nvidia_other_steps() {
  c "2) NVIDIA driver install (non-Ubuntu family)"
  info "PCI:"
  echo "$PCI_NVIDIA" | sed 's/^/    /'
  cat <<'STEPS'

  Install the proprietary NVIDIA driver for your distribution, then reboot.
  Examples:
    Fedora:  sudo dnf install akmod-nvidia
    Arch:    sudo pacman -S nvidia nvidia-utils
    See:     https://ollama.com/download  and your distro's NVIDIA docs

  After reboot: nvidia-smi   then:  ./tools/enable_gpu.sh --verify-only

STEPS
}

print_amd_steps() {
  c "2) AMD GPU detected"
  echo "$PCI_AMD" | sed 's/^/    /'
  cat <<'STEPS'

  Ollama can use AMD GPUs via ROCm on supported cards.
  Ubuntu/Mint (example — package names vary by ROCm release):

    # See https://rocm.docs.amd.com/ for the current install path for your GPU
    sudo apt-get update
    # Install the ROCm stack recommended for your card, then:
    # restart Ollama:  sudo systemctl restart ollama   (or: pkill ollama; ollama serve)

  Then re-run:  ./tools/enable_gpu.sh --verify-only

STEPS
}

print_intel_steps() {
  c "2) Intel GPU detected"
  echo "$PCI_INTEL" | sed 's/^/    /'
  cat <<'STEPS'

  Intel Arc / integrated GPUs: Ollama GPU offload support depends on your
  Ollama build and IPEX/Level Zero stack. For most Synthesus installs today,
  chat will run on CPU unless you follow Ollama's current Intel GPU guide:

    https://github.com/ollama/ollama/blob/main/docs/gpu.md

  No synthetic load-balancing is applied by Synthesus — if the driver stack
  works, Ollama uses it; otherwise CPU mode is expected and correct.

STEPS
}

print_no_gpu_steps() {
  c "2) No discrete GPU detected"
  info "Ollama will use CPU mode. This is expected on machines without a GPU."
  info "If you add an NVIDIA GPU later, re-run this script after installing drivers."
  echo
}

# ---- Ollama GPU verification ---------------------------------------------
ensure_ollama_up() {
  if ! command -v ollama >/dev/null 2>&1; then
    bad "Ollama is not installed (not in PATH)."
    info "Install Ollama first (Synthesus ./install.sh, or https://ollama.com/download)."
    return 1
  fi
  if ! ollama list >/dev/null 2>&1; then
    warn "Ollama daemon not responding — starting ollama serve in background…"
    nohup ollama serve >/dev/null 2>&1 &
    sleep 3
  fi
  if ! ollama list >/dev/null 2>&1; then
    bad "Could not reach Ollama after start attempt."
    return 1
  fi
  return 0
}

pick_tiny_model() {
  # Prefer a tiny model already present; else use env or a small default name.
  TINY_MODEL="${SYNTHESUS_GPU_PROBE_MODEL:-}"
  if [ -z "$TINY_MODEL" ]; then
    # Use first tag from ollama list if any
    TINY_MODEL="$(ollama list 2>/dev/null | awk 'NR==2 {print $1}' || true)"
  fi
  if [ -z "$TINY_MODEL" ]; then
    TINY_MODEL="${SYNTHESUS_MODEL:-llama3.2:3b}"
  fi
}

verify_ollama_gpu() {
  c "3) Verify Ollama GPU offload"
  ensure_ollama_up || return 1
  pick_tiny_model
  info "Probe model: $TINY_MODEL"
  info "Running a tiny generation (ollama run)…"

  # Short, deterministic prompt; discard model text — we care about backend.
  set +e
  OLLAMA_RUN_OUT="$(ollama run "$TINY_MODEL" "Reply with exactly: ok" 2>&1)"
  RUN_EC=$?
  set -e
  if [ "$RUN_EC" -ne 0 ]; then
    bad "ollama run failed (exit $RUN_EC)"
    echo "$OLLAMA_RUN_OUT" | tail -20 | sed 's/^/    /'
    return 1
  fi
  ok "ollama run completed"

  info "Checking ollama ps for processor (GPU vs CPU)…"
  set +e
  PS_OUT="$(ollama ps 2>&1)"
  PS_EC=$?
  set -e
  if [ "$PS_EC" -ne 0 ]; then
    warn "ollama ps failed — cannot confirm GPU offload from process table"
    echo "$PS_OUT" | sed 's/^/    /'
    return 1
  fi
  echo "$PS_OUT" | sed 's/^/    /'

  # ollama ps columns typically include PROCESSOR with "100% GPU" or "100% CPU"
  # or mixed "48%/52% CPU/GPU". Treat any GPU percentage > 0 as success.
  if echo "$PS_OUT" | grep -qiE '([1-9][0-9]*%[[:space:]]*GPU|[0-9]+%/[0-9]+%[[:space:]]*CPU/GPU|PROCESSOR.*GPU)'; then
    if echo "$PS_OUT" | grep -qiE '100%[[:space:]]*CPU' && ! echo "$PS_OUT" | grep -qiE '[1-9][0-9]*%[[:space:]]*GPU|[0-9]+%/[1-9][0-9]*%'; then
      bad "Ollama reports 100% CPU — GPU is NOT being used."
      info "Install/fix drivers (see steps above), reboot, restart Ollama, re-run --verify-only."
      return 1
    fi
    ok "Ollama is using the GPU (not 100% CPU)."
    return 0
  fi

  # Fallback: if nvidia-smi shows process activity during/after run
  if nvidia_smi_works; then
    if nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | grep -q '[0-9]'; then
      ok "nvidia-smi shows compute apps — GPU is active."
      return 0
    fi
  fi

  bad "Could not confirm GPU offload (ollama ps shows no GPU share)."
  info "If you just installed drivers, reboot and run: $0 --verify-only"
  info "CPU mode is fine for chat — only slower."
  return 1
}

# ---- main ----------------------------------------------------------------
detect_distro
detect_gpus
print_gpu_inventory

if [ "$VERIFY_ONLY" -eq 0 ]; then
  if [ -n "$PCI_NVIDIA" ]; then
    if nvidia_smi_works; then
      ok "NVIDIA driver already usable (nvidia-smi works)."
      nvidia-smi -L 2>/dev/null | sed 's/^/    /' || true
      echo
      info "No driver install needed — verifying Ollama offload next."
      echo
    else
      warn "NVIDIA GPU present but nvidia-smi is not usable (driver missing/broken)."
      if [ "$IS_UBUNTU_FAMILY" -eq 1 ] || [ "$DISTRO_ID" = "debian" ]; then
        print_nvidia_ubuntu_steps
      else
        print_nvidia_other_steps
      fi
    fi
  elif [ -n "$PCI_AMD" ]; then
    print_amd_steps
  elif [ -n "$PCI_INTEL" ]; then
    print_intel_steps
  else
    print_no_gpu_steps
  fi
else
  info "--verify-only: skipping install guidance"
  echo
fi

# Always attempt verification when Ollama exists (loud outcome either way)
if command -v ollama >/dev/null 2>&1; then
  if verify_ollama_gpu; then
    echo
    ok "Done — GPU path looks good. Synthesus chat will use hardware acceleration."
    exit 0
  else
    echo
    warn "Done — GPU not confirmed. Chat still works on CPU."
    exit 0
  fi
else
  warn "Ollama not installed yet — install Synthesus (./install.sh) then re-run this script."
  exit 0
fi
