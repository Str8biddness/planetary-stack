# models/

This directory holds optional model files for Synthesus 2.0.
These are NOT committed to the repo due to file size.

**Note:** Synthesus does NOT require any large language models.
The ML Swarm (~458 KB total) is built into the `ml/` directory and runs at <1ms on CPU.
The files below are for **optional** features only.

## Optional model files

| File | Size | Purpose | Download |
|------|------|---------|----------|
| `en_US-ryan-high.onnx` | ~116 MB | Piper TTS voice | [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/ryan/high) |
| `en_US-ryan-high.onnx.json` | ~4 KB | Piper TTS config | Same as above |

## Quick download

```bash
# Piper TTS voice (optional)
wget -P models/ https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/en_US-ryan-high.onnx
wget -P models/ https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/en_US-ryan-high.onnx.json
```

Or use the downloader script:

```bash
bash download_models.sh
```

## Running without models

All core Synthesus features work without any model downloads:
- **Left Hemisphere**: Pattern matching, confidence scoring, fallback cascades
- **Right Hemisphere**: All 9 cognitive modules (emotion, relationships, personality, etc.)
- **ML Swarm**: All 7 micro-models built-in (~458 KB)
- **RAG Pipeline**: FAISS semantic retrieval (78K+ patterns)

Only **text-to-speech** (Piper TTS) and **speech-to-text** (Whisper) require external models.
