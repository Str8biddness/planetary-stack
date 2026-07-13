#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_OUTPUT="$ROOT_DIR/runtime/data/models/realesrgan-x4.onnx"
OUTPUT_PATH="${SYNTHESUS_ESRGAN_MODEL:-$DEFAULT_OUTPUT}"

WEIGHTS_NAME="RealESRGAN_x4plus.pth"
WEIGHTS_URL="https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth"
WEIGHTS_SHA256="4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1"
WEIGHTS_SIZE="67,040,989 bytes"
WEIGHTS_LICENSE="BSD-3-Clause"

YES=0
FORCE=0

usage() {
  cat <<'USAGE'
Usage: scripts/fetch_realesrgan.sh [--yes] [--force]

Opt-in installer for the optional local Real-ESRGAN image rail.

Options:
  --yes    Skip the interactive confirmation prompt.
  --force  Replace an existing target ONNX file.
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

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="${PYTHON:-$ROOT_DIR/.venv/bin/python}"
else
  PYTHON_BIN="${PYTHON:-python3}"
fi

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "ERROR: missing required command: $1" >&2
    exit 1
  fi
}

check_python_module() {
  local module="$1"
  local hint="$2"
  if ! "$PYTHON_BIN" -c "import ${module}" >/dev/null 2>&1; then
    echo "ERROR: Python module '${module}' is not importable with: $PYTHON_BIN" >&2
    echo "Install it explicitly, for example:" >&2
    echo "  $PYTHON_BIN -m pip install ${hint}" >&2
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
need_cmd mkdir
need_cmd mv

if [[ -e "$OUTPUT_PATH" && "$FORCE" -ne 1 ]]; then
  echo "Already installed: $OUTPUT_PATH"
  echo "Use --force to replace it."
  exit 0
fi

check_python_module "onnxruntime" "onnxruntime"
check_python_module "torch" "torch"
check_python_module "onnx" "onnx"
check_python_module "onnxscript" "onnxscript"

cat <<INFO
Synthesus optional local image rail installer

This script is opt-in. It is not called by install, boot, or runtime.

What will be downloaded over HTTPS:
  Name:    $WEIGHTS_NAME
  Source:  $WEIGHTS_URL
  Size:    $WEIGHTS_SIZE
  License: $WEIGHTS_LICENSE
  SHA256:  $WEIGHTS_SHA256

Install target:
  $OUTPUT_PATH

Honest source note:
  The upstream Real-ESRGAN project publishes official x4 PyTorch weights, but
  does not publish an official prebuilt x4 ONNX asset. This installer refuses
  third-party ONNX mirrors. It downloads the verified official weights and
  exports the ONNX file locally.
INFO

confirm

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

WEIGHTS_TMP="$TMP_DIR/$WEIGHTS_NAME"
ONNX_TMP="$TMP_DIR/realesrgan-x4.onnx"

echo "Downloading $WEIGHTS_NAME..."
download_file "$WEIGHTS_URL" "$WEIGHTS_TMP"
verify_sha256 "$WEIGHTS_SHA256" "$WEIGHTS_TMP"

echo "Exporting ONNX locally..."
"$PYTHON_BIN" - "$WEIGHTS_TMP" "$ONNX_TMP" <<'PY'
from pathlib import Path
import sys

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.onnx


def make_layer(block, num_blocks, **kwargs):
    return nn.Sequential(*(block(**kwargs) for _ in range(num_blocks)))


class ResidualDenseBlock(nn.Module):
    def __init__(self, num_feat=64, num_grow_ch=32):
        super().__init__()
        self.conv1 = nn.Conv2d(num_feat, num_grow_ch, 3, 1, 1)
        self.conv2 = nn.Conv2d(num_feat + num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv3 = nn.Conv2d(num_feat + 2 * num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv4 = nn.Conv2d(num_feat + 3 * num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv5 = nn.Conv2d(num_feat + 4 * num_grow_ch, num_feat, 3, 1, 1)
        self.lrelu = nn.LeakyReLU(negative_slope=0.2, inplace=True)

    def forward(self, x):
        x1 = self.lrelu(self.conv1(x))
        x2 = self.lrelu(self.conv2(torch.cat((x, x1), 1)))
        x3 = self.lrelu(self.conv3(torch.cat((x, x1, x2), 1)))
        x4 = self.lrelu(self.conv4(torch.cat((x, x1, x2, x3), 1)))
        x5 = self.conv5(torch.cat((x, x1, x2, x3, x4), 1))
        return x5 * 0.2 + x


class RRDB(nn.Module):
    def __init__(self, num_feat, num_grow_ch=32):
        super().__init__()
        self.rdb1 = ResidualDenseBlock(num_feat, num_grow_ch)
        self.rdb2 = ResidualDenseBlock(num_feat, num_grow_ch)
        self.rdb3 = ResidualDenseBlock(num_feat, num_grow_ch)

    def forward(self, x):
        out = self.rdb1(x)
        out = self.rdb2(out)
        out = self.rdb3(out)
        return out * 0.2 + x


class RRDBNet(nn.Module):
    def __init__(self, num_in_ch, num_out_ch, num_feat=64, num_block=23, num_grow_ch=32, scale=4):
        super().__init__()
        self.scale = scale
        self.conv_first = nn.Conv2d(num_in_ch, num_feat, 3, 1, 1)
        self.body = make_layer(RRDB, num_block, num_feat=num_feat, num_grow_ch=num_grow_ch)
        self.conv_body = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        self.conv_up1 = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        self.conv_up2 = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        self.conv_hr = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        self.conv_last = nn.Conv2d(num_feat, num_out_ch, 3, 1, 1)
        self.lrelu = nn.LeakyReLU(negative_slope=0.2, inplace=True)

    def forward(self, x):
        feat = self.conv_first(x)
        body_feat = self.conv_body(self.body(feat))
        feat = feat + body_feat
        feat = self.lrelu(self.conv_up1(F.interpolate(feat, scale_factor=2, mode="nearest")))
        feat = self.lrelu(self.conv_up2(F.interpolate(feat, scale_factor=2, mode="nearest")))
        return self.conv_last(self.lrelu(self.conv_hr(feat)))

weights_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])

model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
checkpoint = torch.load(str(weights_path), map_location="cpu")
state = checkpoint.get("params_ema") or checkpoint.get("params") or checkpoint
model.load_state_dict(state, strict=True)
model.eval()

sample = torch.rand(1, 3, 64, 64)
with torch.no_grad():
    torch.onnx.export(
        model,
        sample,
        str(output_path),
        opset_version=18,
        export_params=True,
        external_data=False,
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={
            "input": {2: "height", 3: "width"},
            "output": {2: "height_x4", 3: "width_x4"},
        },
    )

print(f"ONNX export wrote {output_path} ({output_path.stat().st_size} bytes)")
PY

if [[ ! -s "$ONNX_TMP" ]]; then
  echo "ERROR: ONNX export did not produce a file." >&2
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT_PATH")"
INSTALL_TMP="$OUTPUT_PATH.tmp.$$"
cp "$ONNX_TMP" "$INSTALL_TMP"
mv "$INSTALL_TMP" "$OUTPUT_PATH"

"$PYTHON_BIN" - "$OUTPUT_PATH" <<'PY'
from pathlib import Path
import sys

import onnxruntime as ort

model_path = Path(sys.argv[1])
try:
    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
except Exception:
    model_path.unlink(missing_ok=True)
    raise
inputs = session.get_inputs()
outputs = session.get_outputs()
print(f"onnxruntime load PASS: inputs={len(inputs)} outputs={len(outputs)}")
PY

echo "Installed Real-ESRGAN ONNX:"
ls -lh "$OUTPUT_PATH"
echo "Set this only if you installed somewhere non-default:"
echo "  export SYNTHESUS_ESRGAN_MODEL=\"$OUTPUT_PATH\""
