#!/bin/bash
# run_ghostkey.sh - Start the Ghostkey AI Quadbrain Backend (v3 Hardened)

# Find the synthesus venv
SYNTH_VENV="../../synthesus/.venv/bin/python3"

if [ ! -f "$SYNTH_VENV" ]; then
    echo "Warning: Synthesus venv not found at $SYNTH_VENV"
    PYTHON_CMD="python3"
else
    PYTHON_CMD="$SYNTH_VENV"
fi

echo "--- Ghostkey Quadbrain (Hardened Fortress Edition) ---"
echo "✅ AES-256 Encrypted IPC & Memory active."
echo "✅ Level 3 Autonomous Self-Defense active."
echo "✅ Normalcy Baselining active."
echo ""
echo "💡 OPTIONAL: For high-quality dialogue, run a local LLM server."
echo "   Example: llama-server -m models/phi-3-mini.gguf -c 2048 --port 8080"
echo ""

echo "Starting Ghostkey Backend..."
$PYTHON_CMD backend.py
