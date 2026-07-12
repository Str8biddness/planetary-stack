#!/usr/bin/env python3
"""
Larynx Vocalizer — SI-native formant speech (Synthesus)

HONEST TARGET
=============
This module synthesizes INTELLIGIBLE but ROBOTIC speech via a classical
source-filter formant model (Klatt-style cascade resonators + glottal pulse).

  - Sounds like DECtalk / Hawking-class formant TTS — words should be
    recognizable to a human (and often to offline ASR).
  - Does NOT sound natural. Natural voice requires neural TTS, which is
    rejected on purpose (SI thesis: synthesize from physics/DSP, not weights).
  - If intelligibility fails in verification, report BLOCKED — never ship
    single-tone beeps relabeled as speech.

Synth path imports: numpy, scipy, stdlib only.
NO pyttsx3 / espeak / piper / coqui / Web Speech / torch / tensorflow.

Pipeline
--------
  text → rule G2P (ARPABET) → phone targets (F1/F2/F3) → coarticulated
  formant tracks → glottal+noise source → cascade resonators → int16 WAV

Prosody / SI identity
---------------------
GeometricEngineFallback 5-axis vectors still drive:
  Y (pitch axis) → F0 base
  phase → F2 stretch (wide_vowels — Australian-ish openness)
  scale → amplitude
  rising_inflection → final F0 lift
  legato_bias → coarticulation transition length (wired, not dead)

API surface (stable)
--------------------
  LarynxVocalizer(sample_rate=22050)
  .speak(text, output_path="larynx_vocal.wav") -> path
  .synthesize(text) -> np.ndarray float64 -1..1
  .accent_profile dict
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.io import wavfile

# tools/ on path
_TOOLS = os.path.abspath(os.path.dirname(__file__))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from formant_g2p import text_to_phonemes, phoneme_string  # noqa: E402
from formant_engine import (  # noqa: E402
    phones_to_audio,
    spectral_formant_summary,
    get_phone,
)

try:
    from geometric_refinery import GeometricEngineFallback
except Exception:  # pragma: no cover
    class GeometricEngineFallback:  # type: ignore
        def word_to_vector(self, word):
            h = abs(hash(word.lower())) % 10000
            return [(h % 100) / 100, ((h // 100) % 100) / 100, 0.5, 0.5, 0.8]


class LarynxVocalizer:
    """Formant-based SI larynx. Same entrypoints as the old tone vocalizer."""

    def __init__(self, sample_rate: int = 16000):
        # 16 kHz: covers F1–F3, matches common offline ASR sample rates
        self.fs = int(sample_rate)
        self.engine = GeometricEngineFallback()
        # Australian-tinged accent profile — ALL keys are live in prosody map
        self.accent_profile: Dict[str, float] = {
            "rising_inflection": 1.12,  # final F0 lift factor
            "wide_vowels": 0.10,        # F2 stretch for voiced vowels
            "legato_bias": 0.55,        # coarticulation (0..1 → transition length)
            "f0_base": 155.0,           # Hz center before geometric Y map
            "rate": 0.82,               # slower = more intelligible for formant TTS
        }
        self.last_phonemes: str = ""
        self.last_meta: Dict[str, Any] = {}

    def _prosody_for_text(self, text: str) -> Dict[str, float]:
        words = [w for w in text.replace(".", " ").replace(",", " ").split() if w]
        if not words:
            return {
                "f0_base": self.accent_profile["f0_base"],
                "f0_end": self.accent_profile["f0_base"] * self.accent_profile["rising_inflection"],
                "f2_stretch": 1.0 + self.accent_profile["wide_vowels"],
                "dur_scale": self.accent_profile["rate"],
                "transition": 0.025 + 0.04 * self.accent_profile["legato_bias"],
                "amp": 0.9,
            }
        vecs = [self.engine.word_to_vector(w) for w in words]
        # Y-axis → pitch
        y_mean = float(np.mean([v[1] for v in vecs]))
        y_last = float(vecs[-1][1])
        f0_base = 110.0 + y_mean * 100.0  # ~110–210 Hz
        f0_base = 0.55 * f0_base + 0.45 * self.accent_profile["f0_base"]
        # rising inflection (AU-ish) on last word Y + profile
        f0_end = f0_base * (
            0.92 + 0.08 * y_last
        ) * self.accent_profile["rising_inflection"]
        # phase → wide vowels (F2)
        phase = float(np.mean([v[3] for v in vecs]))
        f2_stretch = 1.0 + self.accent_profile["wide_vowels"] * (0.5 + phase)
        # scale → amp
        amp = float(np.clip(np.mean([v[4] for v in vecs]), 0.35, 1.0))
        # legato → transition length
        transition = 0.02 + 0.05 * self.accent_profile["legato_bias"]
        dur_scale = float(self.accent_profile["rate"]) * (0.92 + 0.16 * (1.0 - y_mean))
        return {
            "f0_base": f0_base,
            "f0_end": f0_end,
            "f2_stretch": f2_stretch,
            "dur_scale": dur_scale,
            "transition": transition,
            "amp": amp,
        }

    def _flatten_phones(self, text: str) -> List[str]:
        phones: List[str] = []
        for word, ph in text_to_phonemes(text):
            if word in (".", ","):
                phones.extend(ph)
            else:
                phones.extend(ph)
                phones.append("SIL_LONG")  # clear word boundary for ASR/humans
        # trim trailing sil
        while phones and phones[-1] in ("SIL", "SIL_LONG"):
            phones.pop()
        return phones

    def synthesize(self, text: str, seed: int = 25) -> np.ndarray:
        """Return mono float64 audio in [-1, 1].

        Word-at-a-time rendering with per-word normalization improves
        multi-word intelligibility for formant TTS (classic DECtalk also
        works phrase-wise with strong boundaries).
        """
        text = (text or "").strip()
        if not text:
            return np.zeros(int(0.1 * self.fs), dtype=np.float64)

        self.last_phonemes = phoneme_string(text)
        parts = text_to_phonemes(text)
        if not parts:
            raise RuntimeError(
                "G2P produced no phonemes — cannot synthesize speech for: "
                + repr(text)
            )

        pros = self._prosody_for_text(text)
        chunks: List[np.ndarray] = []
        gap = np.zeros(int(0.12 * self.fs), dtype=np.float64)
        n_words = sum(1 for w, _ in parts if w not in (".", ","))
        wi = 0
        for word, ph in parts:
            if word in (".", ","):
                chunks.append(np.zeros(int(0.2 * self.fs), dtype=np.float64))
                continue
            wi += 1
            # progressive F0 across sentence
            t = wi / max(n_words, 1)
            f0_b = pros["f0_base"] * (1.0 - 0.05 * t)
            f0_e = f0_b * (1.05 if wi == n_words else 0.98)
            if wi == n_words:
                f0_e = pros["f0_end"]
            word_audio = phones_to_audio(
                ph,
                fs=self.fs,
                f0_base=f0_b,
                f0_end=f0_e,
                dur_scale=pros["dur_scale"] * 1.25,
                f2_stretch=pros["f2_stretch"],
                amp=1.0,
                transition=min(0.05, pros["transition"]),
                seed=seed + wi * 17,
            )
            # per-word peak normalize (prevents one burst dominating phrase)
            peak = np.max(np.abs(word_audio)) + 1e-12
            word_audio = word_audio / peak * 0.85 * pros["amp"]
            chunks.append(word_audio)
            chunks.append(gap.copy())

        if chunks and len(chunks[-1]) == len(gap):
            chunks.pop()
        audio = np.concatenate(chunks) if chunks else np.zeros(int(0.1 * self.fs))
        pad = int(0.06 * self.fs)
        audio = np.concatenate([np.zeros(pad), audio, np.zeros(pad)])
        peak = np.max(np.abs(audio)) + 1e-12
        audio = audio / peak * 0.95
        n_phones = sum(len(ph) for w, ph in parts if w not in (".", ","))
        self.last_meta = {
            "engine": "si_formant_klatt",
            "not_neural_tts": True,
            "honest_target": "intelligible_robotic_formant",
            "fs": self.fs,
            "n_phones": n_phones,
            "phonemes": self.last_phonemes,
            "prosody": pros,
            "render": "word_at_a_time",
            "spectral": spectral_formant_summary(audio, self.fs),
        }
        return audio

    def speak(self, text: str, output_path: str = "larynx_vocal.wav") -> str:
        """Synthesize and write int16 WAV. Returns output path."""
        print(f"🎬 Formant vocalizing: '{text}'...")
        audio = self.synthesize(text)
        # int16 for broad player compatibility (not float32)
        pcm = np.clip(audio, -1.0, 1.0)
        pcm_i16 = (pcm * 32767.0).astype(np.int16)
        out = str(output_path)
        # ensure parent
        parent = os.path.dirname(os.path.abspath(out))
        if parent:
            os.makedirs(parent, exist_ok=True)
        wavfile.write(out, self.fs, pcm_i16)
        # verify int16
        sr, data = wavfile.read(out)
        dtype = str(data.dtype)
        print(f"💾 Larynx formant WAV: {out}  sr={sr} dtype={dtype} samples={len(data)}")
        print(f"   phonemes: {self.last_phonemes}")
        sp = self.last_meta.get("spectral") or {}
        print(f"   spectral peak/mean={sp.get('peak_mean_ratio')} bands={sp.get('band_energy')}")
        if dtype != "int16":
            raise RuntimeError(f"WAV dtype must be int16, got {dtype}")
        return out


def _self_check_imports() -> None:
    """Ensure synth path has no neural/external TTS."""
    banned = (
        "pyttsx3", "espeak", "piper", "coqui", "TTS", "torch", "tensorflow",
        "torchaudio", "gtts", "elevenlabs", "openai", "whisper", "vosk",
    )
    # only check our modules' source text
    base = Path(__file__).resolve().parent
    for name in ("larynx_vocalizer.py", "formant_engine.py", "formant_g2p.py"):
        text = (base / name).read_text(encoding="utf-8")
        for b in banned:
            # allow mentions in comments / docstring about verification
            if f"import {b}" in text or f"from {b}" in text:
                raise RuntimeError(f"Banned import of {b} in {name}")


if __name__ == "__main__":
    _self_check_imports()
    vocalizer = LarynxVocalizer(sample_rate=22050)
    prompt = "Hello world"
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
    out = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "larynx_vocal.wav",
    )
    vocalizer.speak(prompt, out)
