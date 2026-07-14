#!/usr/bin/env bash
set -euo pipefail

PIPER_VERSION="2023.11.14-2"
PIPER_ARCHIVE_NAME="piper_linux_x86_64.tar.gz"
PIPER_URL="https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz"
PIPER_SHA256="a50cb45f355b7af1f6d758c1b360717877ba0a398cc8cbe6d2a7a3a26e225992"
PIPER_SIZE="26,460,462 bytes"
PIPER_LICENSE="MIT"

VOICE_NAME="en_US-lessac-low"
VOICE_REPO_COMMIT="e21c7de8d4eab79b902f0d61e662b3f21664b8d2"
VOICE_ONNX_NAME="en_US-lessac-low.onnx"
VOICE_JSON_NAME="en_US-lessac-low.onnx.json"
VOICE_ONNX_URL="https://huggingface.co/rhasspy/piper-voices/resolve/${VOICE_REPO_COMMIT}/en/en_US/lessac/low/${VOICE_ONNX_NAME}"
VOICE_JSON_URL="https://huggingface.co/rhasspy/piper-voices/resolve/${VOICE_REPO_COMMIT}/en/en_US/lessac/low/${VOICE_JSON_NAME}"
VOICE_ONNX_SHA256="f7d01dde371555732c4c314111ac79672b1a5ce2fc19266ab42178fd8df7f375"
VOICE_JSON_SHA256="45754dfdebb3b8661c3fc564713772deec6e064feeb5b4e9594857dc7305193a"
VOICE_ONNX_SIZE="63,201,294 bytes"
VOICE_JSON_SIZE="4,882 bytes"
VOICE_LICENSE="MIT model repository metadata; lessac dataset license: https://www.cstr.ed.ac.uk/projects/blizzard/2013/lessac_blizzard2013/license.html"

SYNTH_HOME="${SYNTHESUS_HOME:-$HOME/.local/share/synthesus}"
PIPER_INSTALL_DIR="$SYNTH_HOME/piper/${PIPER_VERSION}-linux-x86_64"
PIPER_BIN_DIR="$SYNTH_HOME/bin"
PIPER_BIN_PATH="$PIPER_BIN_DIR/piper"
VOICE_DIR="$SYNTH_HOME/voices"
VOICE_ONNX_PATH="$VOICE_DIR/$VOICE_ONNX_NAME"
VOICE_JSON_PATH="$VOICE_DIR/$VOICE_JSON_NAME"

YES=0
FORCE=0

usage() {
  cat <<'USAGE'
Usage: scripts/fetch_piper_voice.sh [--yes] [--force]

Opt-in installer for the optional local Piper voice rail.

Options:
  --yes    Skip the interactive confirmation prompt.
  --force  Replace an existing Piper install and voice files.
  -h, --help
           Show this help.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes)
      YES=1
      shift
      ;;
    --force)
      FORCE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "ERROR: missing required command: $1" >&2
    exit 1
  fi
}

download_file() {
  local url="$1"
  local dest="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -L --fail --show-error --progress-bar \
      --proto '=https' --tlsv1.2 \
      -o "$dest" "$url"
  elif command -v wget >/dev/null 2>&1; then
    wget --https-only -O "$dest" "$url"
  else
    echo "ERROR: need curl or wget to download artifacts." >&2
    exit 1
  fi
}

verify_sha256() {
  local expected="$1"
  local file="$2"
  printf '%s  %s\n' "$expected" "$file" | sha256sum -c -
  echo "checksum PASS: $(basename "$file")"
}

confirm() {
  if [[ "$YES" -eq 1 ]]; then
    return 0
  fi
  printf "Continue with this opt-in local install? Type 'yes' to continue: "
  local answer
  read -r answer
  if [[ "$answer" != "yes" ]]; then
    echo "Aborted. Nothing installed."
    exit 1
  fi
}

need_cmd sha256sum
need_cmd tar
need_cmd mkdir
need_cmd mv
need_cmd chmod

case "$(uname -s):$(uname -m)" in
  Linux:x86_64|Linux:amd64)
    ;;
  *)
    echo "ERROR: this pinned fetcher currently supports Linux x86_64 only." >&2
    echo "No files downloaded. Add a pinned official Piper artifact for this platform before using it here." >&2
    exit 1
    ;;
esac

if [[ -e "$PIPER_BIN_PATH" || -e "$VOICE_ONNX_PATH" || -e "$VOICE_JSON_PATH" || -d "$PIPER_INSTALL_DIR" ]]; then
  if [[ "$FORCE" -ne 1 ]]; then
    echo "Piper or voice files already exist:"
    [[ -e "$PIPER_BIN_PATH" ]] && echo "  $PIPER_BIN_PATH"
    [[ -d "$PIPER_INSTALL_DIR" ]] && echo "  $PIPER_INSTALL_DIR"
    [[ -e "$VOICE_ONNX_PATH" ]] && echo "  $VOICE_ONNX_PATH"
    [[ -e "$VOICE_JSON_PATH" ]] && echo "  $VOICE_JSON_PATH"
    echo "Use --force to replace them."
    exit 0
  fi
fi

cat <<INFO
Synthesus optional local voice rail installer

This script is opt-in. It is not called by install, boot, or runtime.

What will be downloaded over HTTPS:
  Name:    $PIPER_ARCHIVE_NAME
  Source:  $PIPER_URL
  Size:    $PIPER_SIZE
  License: $PIPER_LICENSE
  SHA256:  $PIPER_SHA256

  Name:    $VOICE_ONNX_NAME
  Source:  $VOICE_ONNX_URL
  Size:    $VOICE_ONNX_SIZE
  License: $VOICE_LICENSE
  SHA256:  $VOICE_ONNX_SHA256

  Name:    $VOICE_JSON_NAME
  Source:  $VOICE_JSON_URL
  Size:    $VOICE_JSON_SIZE
  License: $VOICE_LICENSE
  SHA256:  $VOICE_JSON_SHA256

Install targets:
  Piper binary wrapper: $PIPER_BIN_PATH
  Piper payload:        $PIPER_INSTALL_DIR
  Voice ONNX:           $VOICE_ONNX_PATH
  Voice JSON:           $VOICE_JSON_PATH
INFO

confirm

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

ARCHIVE_TMP="$TMP_DIR/$PIPER_ARCHIVE_NAME"
VOICE_ONNX_TMP="$TMP_DIR/$VOICE_ONNX_NAME"
VOICE_JSON_TMP="$TMP_DIR/$VOICE_JSON_NAME"
EXTRACT_DIR="$TMP_DIR/extract"
INSTALL_TMP="$TMP_DIR/piper-install"

echo "Downloading $PIPER_ARCHIVE_NAME..."
download_file "$PIPER_URL" "$ARCHIVE_TMP"
verify_sha256 "$PIPER_SHA256" "$ARCHIVE_TMP"

echo "Downloading $VOICE_ONNX_NAME..."
download_file "$VOICE_ONNX_URL" "$VOICE_ONNX_TMP"
verify_sha256 "$VOICE_ONNX_SHA256" "$VOICE_ONNX_TMP"

echo "Downloading $VOICE_JSON_NAME..."
download_file "$VOICE_JSON_URL" "$VOICE_JSON_TMP"
verify_sha256 "$VOICE_JSON_SHA256" "$VOICE_JSON_TMP"

mkdir -p "$EXTRACT_DIR" "$INSTALL_TMP"
tar -xzf "$ARCHIVE_TMP" -C "$EXTRACT_DIR"
if [[ ! -x "$EXTRACT_DIR/piper/piper" ]]; then
  echo "ERROR: extracted archive did not contain executable piper/piper." >&2
  exit 1
fi

cp -R "$EXTRACT_DIR/piper" "$INSTALL_TMP/piper"
mkdir -p "$PIPER_BIN_DIR" "$VOICE_DIR" "$(dirname "$PIPER_INSTALL_DIR")"

if [[ "$FORCE" -eq 1 ]]; then
  rm -rf "$PIPER_INSTALL_DIR"
fi
mv "$INSTALL_TMP" "$PIPER_INSTALL_DIR"

WRAPPER_TMP="$TMP_DIR/piper-wrapper"
cat > "$WRAPPER_TMP" <<WRAPPER
#!/usr/bin/env bash
set -euo pipefail
PIPER_HOME="$PIPER_INSTALL_DIR/piper"
export LD_LIBRARY_PATH="\$PIPER_HOME:\${LD_LIBRARY_PATH:-}"
exec "\$PIPER_HOME/piper" "\$@"
WRAPPER
chmod 0755 "$WRAPPER_TMP"
mv "$WRAPPER_TMP" "$PIPER_BIN_PATH"

VOICE_ONNX_INSTALL_TMP="$VOICE_ONNX_PATH.tmp.$$"
VOICE_JSON_INSTALL_TMP="$VOICE_JSON_PATH.tmp.$$"
cp "$VOICE_ONNX_TMP" "$VOICE_ONNX_INSTALL_TMP"
cp "$VOICE_JSON_TMP" "$VOICE_JSON_INSTALL_TMP"
mv "$VOICE_ONNX_INSTALL_TMP" "$VOICE_ONNX_PATH"
mv "$VOICE_JSON_INSTALL_TMP" "$VOICE_JSON_PATH"

echo "Installed Piper CLI and voice:"
ls -lh "$PIPER_BIN_PATH" "$VOICE_ONNX_PATH" "$VOICE_JSON_PATH"
echo "Use these exports for shells/services that do not use the default search paths:"
echo "  export SYNTHESUS_PIPER_BIN=\"$PIPER_BIN_PATH\""
echo "  export SYNTHESUS_PIPER_MODEL=\"$VOICE_ONNX_PATH\""
