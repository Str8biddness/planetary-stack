#!/usr/bin/env python3
"""
Voice backends for Synthesus — formant SI default + optional local neural.

HONEST CONTRACT
===============
- ``formant`` (default): SI Klatt larynx — intelligible-but-robotic, no neural weights.
- ``piper``: optional local Piper CLI/ONNX — natural voice, STILL offline, no cloud.
  LOUD 503-style errors if binary/model missing — never silent fallback to cloud.

Framing: Klatt = raw/retro/deterministic SI; Piper = "SI Voice Standard" opt-in
that preserves privacy moat but breaks pure-formant claim.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

BACKENDS = ("formant", "piper")


def _piper_bin() -> Optional[str]:
    env = os.environ.get("SYNTHESUS_PIPER_BIN", "").strip()
    if env and os.path.isfile(env) and os.access(env, os.X_OK):
        return env
    which = shutil.which("piper")
    if which:
        return which
    for p in (
        Path.home() / ".local" / "bin" / "piper",
        Path("/usr/local/bin/piper"),
        Path.home() / ".local" / "share" / "synthesus" / "bin" / "piper",
    ):
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return None


def _piper_model() -> Optional[str]:
    env = os.environ.get("SYNTHESUS_PIPER_MODEL", "").strip()
    if env and os.path.isfile(env):
        return env
    roots = [
        Path.home() / ".local" / "share" / "piper" / "voices",
        Path.home() / ".local" / "share" / "synthesus" / "voices",
        Path(__file__).resolve().parents[1] / "data" / "voices",
    ]
    for root in roots:
        if not root.is_dir():
            continue
        # Prefer en_US onnx
        hits = sorted(root.rglob("*.onnx"))
        for h in hits:
            if "en" in h.name.lower() or "en_" in str(h).lower():
                return str(h)
        if hits:
            return str(hits[0])
    return None


def piper_status() -> Dict[str, Any]:
    b = _piper_bin()
    m = _piper_model()
    return {
        "backend": "piper",
        "available": bool(b and m),
        "binary": b,
        "model": m,
        "neural": True,
        "offline": True,
        "not_cloud": True,
        "note": (
            "Local Piper VITS/ONNX — natural prosody. Opt-in; breaks pure-formant claim."
            if b and m
            else "Install piper CLI + an en_US .onnx voice (set SYNTHESUS_PIPER_BIN / "
            "SYNTHESUS_PIPER_MODEL). Formant SI remains the default."
        ),
    }


def formant_status() -> Dict[str, Any]:
    return {
        "backend": "formant",
        "available": True,
        "neural": False,
        "offline": True,
        "honest_target": "intelligible_robotic_formant",
        "note": "SI Klatt formant — default. No neural weights.",
    }


def list_backends() -> Dict[str, Any]:
    return {
        "default": "formant",
        "backends": {
            "formant": formant_status(),
            "piper": piper_status(),
        },
        "honest": (
            "Formant stays SI-native. Piper is optional local neural for naturalness. "
            "No cloud TTS. No silent fallback."
        ),
    }


def synthesize_formant(
    text: str,
    *,
    knobs: Optional[dict] = None,
    seed: int = 25,
    sample_rate: int = 16000,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    from larynx_vocalizer import LarynxVocalizer
    try:
        from formant_plan import apply_pass_knobs, public_plan_view
    except Exception:
        apply_pass_knobs = None  # type: ignore
        public_plan_view = None  # type: ignore

    knobs = knobs or {}
    lar = LarynxVocalizer(sample_rate=sample_rate)
    plan = lar.compile_plan(text, use_llm=False)
    if knobs and apply_pass_knobs is not None:
        plan = apply_pass_knobs(plan, knobs)
    audio = lar.synthesize_plan(plan, seed=seed, keep_session=True)
    meta = dict(lar.last_meta or {})
    meta.update({
        "backend": "formant",
        "engine": "si_formant_klatt",
        "not_neural_tts": True,
        "honest_target": "intelligible_robotic_formant",
        "phonemes": lar.last_phonemes,
        "utterance_id": lar.last_utterance_id,
        "sample_rate": lar.fs,
        "utterance_plan": public_plan_view(plan) if public_plan_view else {},
        "knobs": knobs,
        "outer_voice": meta.get("outer_voice")
        or "SI formant speech — not a neural TTS model.",
    })
    return np.asarray(audio, dtype=np.float64), meta


def synthesize_piper(
    text: str,
    *,
    sample_rate: int = 16000,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    st = piper_status()
    if not st["available"]:
        raise RuntimeError("piper_unavailable: " + st["note"])

    bin_path = st["binary"]
    model = st["model"]
    with tempfile.TemporaryDirectory(prefix="synth_piper_") as td:
        out_wav = os.path.join(td, "out.wav")
        # piper reads text from stdin, writes wav
        cmd = [bin_path, "--model", model, "--output_file", out_wav]
        try:
            proc = subprocess.run(
                cmd,
                input=text.encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
                check=False,
            )
        except FileNotFoundError as e:
            raise RuntimeError(f"piper_unavailable: binary missing ({e})") from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError("piper_timeout") from e
        if proc.returncode != 0 or not os.path.isfile(out_wav):
            err = (proc.stderr or b"").decode("utf-8", errors="replace")[:400]
            raise RuntimeError(f"piper_failed: rc={proc.returncode} {err}")

        from scipy.io import wavfile
        fs, pcm = wavfile.read(out_wav)
        if pcm.ndim > 1:
            pcm = pcm.mean(axis=1)
        audio = pcm.astype(np.float64)
        if pcm.dtype == np.int16:
            audio = audio / 32768.0
        elif pcm.dtype == np.int32:
            audio = audio / 2147483648.0
        elif audio.max() > 1.5:
            audio = audio / (np.max(np.abs(audio)) + 1e-12)
        # resample if needed
        if int(fs) != int(sample_rate) and len(audio) > 1:
            try:
                from scipy import signal
                n_out = int(round(len(audio) * float(sample_rate) / float(fs)))
                audio = signal.resample(audio, max(1, n_out))
                fs = sample_rate
            except Exception:
                pass
        peak = np.max(np.abs(audio)) + 1e-12
        audio = audio / peak * 0.95
        meta = {
            "backend": "piper",
            "engine": "piper_local_vits",
            "not_neural_tts": False,
            "neural_local": True,
            "not_cloud": True,
            "honest_target": "near_natural_local_neural",
            "phonemes": None,
            "utterance_id": None,
            "sample_rate": int(fs),
            "model": model,
            "binary": bin_path,
            "outer_voice": (
                "Local Piper neural voice (opt-in) — offline, not cloud TTS. "
                "SI formant remains available as backend=formant."
            ),
        }
        return audio.astype(np.float64), meta


def synthesize(
    text: str,
    *,
    backend: str = "formant",
    knobs: Optional[dict] = None,
    seed: int = 25,
    sample_rate: int = 16000,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    backend = (backend or "formant").lower().strip()
    if backend not in BACKENDS:
        raise RuntimeError(f"unknown_voice_backend: {backend} (want formant|piper)")
    if backend == "formant":
        return synthesize_formant(text, knobs=knobs, seed=seed, sample_rate=sample_rate)
    return synthesize_piper(text, sample_rate=sample_rate)
