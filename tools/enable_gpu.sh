#!/usr/bin/env bash
# GPU Acceleration Pack - Detects GPU and guides user on Ollama acceleration.
# Self-contained guided script.

echo "=== GPU Acceleration Check ==="

HAS_GPU=false
if command -v nvidia-smi &>/dev/null; then
    echo "[+] NVIDIA GPU detected."
    HAS_GPU=true
elif command -v rocminfo &>/dev/null; then
    echo "[+] AMD GPU detected."
    HAS_GPU=true
else
    echo "[-] No NVIDIA/AMD GPU utilities found."
fi

if $HAS_GPU; then
    echo "[*] Checking if Ollama is using GPU..."
    if command -v ollama &>/dev/null; then
        OLLAMA_LOG=$(ollama ps 2>/dev/null || true)
        if echo "$OLLAMA_LOG" | grep -qi "gpu"; then
            echo "[+] Ollama is utilizing the GPU."
        else
            echo "[-] Ollama does not appear to be utilizing the GPU."
            echo "    Installation steps for your OS:"
            echo "    Ubuntu/Debian (NVIDIA): sudo apt install nvidia-driver-535 nvidia-cuda-toolkit"
            echo "    Ubuntu/Debian (AMD): sudo apt install rocm-core"
            echo "    Please restart Ollama after installation."
        fi
        
        echo "[*] Running token-rate check (timed model run)..."
        echo "Please wait..."
        time ollama run llama3 "Hello" 2>/dev/null || echo "Failed to run ollama."
    else
        echo "[-] Ollama not installed or not in PATH."
    fi
fi
