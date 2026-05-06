#!/bin/bash
# download_models.sh - Download optional model files for Synthesus 2.0
# Usage: bash download_models.sh
#
# NOTE: Synthesus 2.0 does NOT require any large model downloads.
# The ML Swarm (~458 KB) is built-in. These are OPTIONAL extras.

set -e

MODELS_DIR="models"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}Synthesus 2.0 — Optional Model Downloader${NC}"
echo "============================================"
echo ""
echo -e "The ML Swarm (intent, sentiment, embeddings, etc.) is built-in."
echo -e "These downloads are for OPTIONAL features only."
echo ""

mkdir -p "$MODELS_DIR"

if command -v wget &> /dev/null; then
    DOWNLOADER="wget -O"
elif command -v curl &> /dev/null; then
    DOWNLOADER="curl -L -o"
else
    echo -e "${RED}Error: Neither wget nor curl found.${NC}"
    exit 1
fi

echo -e "${YELLOW}[1/2] Downloading Piper TTS voice (~116 MB)...${NC}"
PIPER_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high"
PIPER_ONNX="$MODELS_DIR/en_US-ryan-high.onnx"
PIPER_JSON="$MODELS_DIR/en_US-ryan-high.onnx.json"

if [ -f "$PIPER_ONNX" ] && [ -f "$PIPER_JSON" ]; then
    echo -e "${GREEN}[SKIP] Piper voice files already exist${NC}"
else
    $DOWNLOADER "$PIPER_ONNX" "$PIPER_BASE/en_US-ryan-high.onnx"
    $DOWNLOADER "$PIPER_JSON" "$PIPER_BASE/en_US-ryan-high.onnx.json"
    echo -e "${GREEN}[DONE] Piper voice files downloaded${NC}"
fi

echo ""
echo -e "${GREEN}Done!${NC}"
echo "  Piper ONNX: $PIPER_ONNX"
echo ""
echo -e "${YELLOW}Note: Whisper tiny.en (~75MB) auto-downloads via pywhispercpp on first use.${NC}"
echo ""
echo -e "${GREEN}Ready! Run: uvicorn api.production_server:app --port 5000${NC}"
