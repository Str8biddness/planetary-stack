# Optional Local Neural Rails

Synthesus stays local-first and SI-native by default. The default install does not
download neural image or voice models, does not call cloud services, and keeps the
optional neural rails unavailable until you explicitly install them.

Two opt-in scripts are available:

- `scripts/fetch_realesrgan.sh`: installs `runtime/data/models/realesrgan-x4.onnx`
  for `enhance=realesrgan`.
- `scripts/fetch_piper_voice.sh`: installs a local Piper CLI wrapper and the
  `en_US-lessac-low` voice for `backend=piper`.

## What These Add

`enhance=realesrgan` adds a local Real-ESRGAN x4 neural upscale after the SI image
scene graph is rendered. It can add learned texture and sharpness to a generated
raster, but it is not diffusion and it does not change the underlying scene plan.

`backend=piper` adds a local Piper VITS/ONNX neural voice. It sounds more natural
than the default formant voice, but it is still offline and local after install.

These are the only non-SI rails described here. The tradeoff is honest: they break
the pure-SI pixel/formant claim, but they do not add cloud inference or telemetry.

## Install

The scripts print every artifact before downloading it: name, source URL, size,
license, and pinned SHA-256. They require either an interactive `yes` or `--yes`.
They verify checksums before install and fail loudly on any mismatch.

```bash
scripts/fetch_realesrgan.sh
scripts/fetch_piper_voice.sh
```

For non-interactive automation:

```bash
scripts/fetch_realesrgan.sh --yes
scripts/fetch_piper_voice.sh --yes
```

The Real-ESRGAN script uses official upstream Real-ESRGAN x4 PyTorch weights and
exports the ONNX locally because the upstream project does not publish an official
prebuilt x4 ONNX release asset. It refuses third-party ONNX mirrors. Required
Python modules are checked first; if missing, install them explicitly:

```bash
python3 -m pip install onnxruntime torch onnx onnxscript
```

## Enable

Default paths are already scanned by the runtime. If you run services from a shell
that needs explicit paths, use the exports printed by the scripts:

```bash
export SYNTHESUS_ESRGAN_MODEL="/path/to/synthesus/runtime/data/models/realesrgan-x4.onnx"
export SYNTHESUS_PIPER_BIN="$HOME/.local/share/synthesus/bin/piper"
export SYNTHESUS_PIPER_MODEL="$HOME/.local/share/synthesus/voices/en_US-lessac-low.onnx"
```

Then request the rails explicitly:

```bash
curl -s http://127.0.0.1:5010/api/v1/image/capabilities
curl -s http://127.0.0.1:5010/api/v1/voice/capabilities
```

Use `enhance=realesrgan` on `POST /api/v1/image` and `backend=piper` on
`POST /api/v1/voice`.

## Disable Or Remove

Disable for a single shell by unsetting the overrides:

```bash
unset SYNTHESUS_ESRGAN_MODEL SYNTHESUS_PIPER_BIN SYNTHESUS_PIPER_MODEL
```

Remove the installed local artifacts:

```bash
rm -f runtime/data/models/realesrgan-x4.onnx
rm -f "$HOME/.local/share/synthesus/bin/piper"
rm -rf "$HOME/.local/share/synthesus/piper/2023.11.14-2-linux-x86_64"
rm -f "$HOME/.local/share/synthesus/voices/en_US-lessac-low.onnx"
rm -f "$HOME/.local/share/synthesus/voices/en_US-lessac-low.onnx.json"
```

After removal, the runtime returns to the loud degraded behavior for the optional
rails: `enhance=realesrgan` and `backend=piper` return 503 until installed again.
