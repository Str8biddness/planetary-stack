#!/usr/bin/env python3
"""
Larynx Vocalizer — SI-native formant speech (Synthesus)

HONEST TARGET
=============
INTELLIGIBLE but ROBOTIC formant speech (Klatt / DECtalk class).
Not natural. Neural TTS rejected on purpose.

Pipeline
--------
  text → utterance_plan (rules + optional sparse LLM phone enrich)
      → word-at-a-time formant render → int16 WAV
  multi-pass: utterance_id stock + pass knobs (rate/F0/F2) without re-G2P

Synth path: numpy/scipy/stdlib only (+ optional Ollama for *plan* JSON only).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from scipy.io import wavfile

_TOOLS = os.path.abspath(os.path.dirname(__file__))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from formant_g2p import phoneme_string  # noqa: E402
from formant_engine import phones_to_audio, spectral_formant_summary  # noqa: E402
from formant_plan import (  # noqa: E402
    compile_utterance_plan,
    apply_pass_knobs,
    public_plan_view,
    plan_fingerprint,
    plan_to_render_words,
    classify_speech_pass,
)
import formant_session as usess  # noqa: E402

try:
    from geometric_refinery import GeometricEngineFallback
except Exception:  # pragma: no cover
    class GeometricEngineFallback:  # type: ignore
        def word_to_vector(self, word):
            h = abs(hash(word.lower())) % 10000
            return [(h % 100) / 100, ((h // 100) % 100) / 100, 0.5, 0.5, 0.8]


class LarynxVocalizer:
    """Formant-based SI larynx with utterance plans + multi-pass stock."""

    def __init__(self, sample_rate: int = 16000):
        self.fs = int(sample_rate)
        self.engine = GeometricEngineFallback()
        self.accent_profile: Dict[str, float] = {
            "rising_inflection": 1.12,
            "wide_vowels": 0.10,
            "legato_bias": 0.55,
            "f0_base": 155.0,
            "rate": 0.82,
        }
        self.last_phonemes: str = ""
        self.last_meta: Dict[str, Any] = {}
        self.last_plan: Optional[dict] = None
        self.last_utterance_id: Optional[str] = None

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
        y_mean = float(np.mean([v[1] for v in vecs]))
        y_last = float(vecs[-1][1])
        f0_base = 110.0 + y_mean * 100.0
        f0_base = 0.55 * f0_base + 0.45 * self.accent_profile["f0_base"]
        f0_end = f0_base * (0.92 + 0.08 * y_last) * self.accent_profile["rising_inflection"]
        phase = float(np.mean([v[3] for v in vecs]))
        f2_stretch = 1.0 + self.accent_profile["wide_vowels"] * (0.5 + phase)
        amp = float(np.clip(np.mean([v[4] for v in vecs]), 0.35, 1.0))
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

    def compile_plan(
        self,
        text: str,
        *,
        use_llm: Optional[bool] = None,
    ) -> dict:
        """Build utterance plan (rules + optional sparse LLM phone enrich)."""
        pros = self._prosody_for_text(text)
        plan = compile_utterance_plan(
            text,
            accent=self.accent_profile,
            geometric_prosody=pros,
            use_llm=use_llm,
        )
        self.last_plan = plan
        self.last_phonemes = " | ".join(
            f"{w.get('orth')}:{ ' '.join(w.get('phones') or [])}"
            for w in plan.get("words") or []
        )
        return plan

    def synthesize_plan(
        self,
        plan: dict,
        *,
        seed: int = 25,
        keep_session: bool = True,
        utterance_id: Optional[str] = None,
    ) -> np.ndarray:
        """Render a (possibly multi-pass mutated) utterance plan to audio."""
        words = plan_to_render_words(plan)
        if not words:
            raise RuntimeError(
                "Utterance plan has no valid phones — cannot synthesize: "
                + repr(plan.get("source_text"))
            )

        f0_base = float(plan.get("f0_base_hz") or 150.0)
        f0_end = float(plan.get("f0_end_hz") or f0_base * 1.1)
        f2 = float(plan.get("f2_stretch") or 1.0)
        transition = float(plan.get("transition_s") or 0.04)
        amp = float(plan.get("amp") or 0.9)
        pauses = plan.get("pauses_ms") or []
        n_words = len(words)
        chunks: List[np.ndarray] = []

        for wi, w in enumerate(words):
            t = (wi + 1) / max(n_words, 1)
            f0_b = f0_base * (1.0 - 0.05 * t)
            f0_e = f0_end if wi == n_words - 1 else f0_b * 0.98
            # stress → slightly longer already in dur_scale
            word_audio = phones_to_audio(
                w["phones"],
                fs=self.fs,
                f0_base=f0_b,
                f0_end=f0_e,
                # extra margin for formant intelligibility (plan already has rate)
                dur_scale=float(w["dur_scale"]) * 1.2,
                f2_stretch=f2,
                amp=1.0,
                transition=min(0.05, transition),
                seed=seed + (wi + 1) * 17,
            )
            peak = np.max(np.abs(word_audio)) + 1e-12
            word_audio = word_audio / peak * 0.85 * amp
            chunks.append(word_audio)
            # pause after word (except last)
            if wi < n_words - 1:
                p_ms = 160
                if wi + 1 < len(pauses):
                    p_ms = int(pauses[wi + 1] or p_ms)
                elif wi < len(pauses):
                    p_ms = int(pauses[wi] or p_ms)
                # stressed words get a bit more space after
                if w.get("stress"):
                    p_ms = int(p_ms * 1.15)
                chunks.append(np.zeros(max(1, int(self.fs * p_ms / 1000.0)), dtype=np.float64))

        audio = np.concatenate(chunks) if chunks else np.zeros(int(0.1 * self.fs))
        pad = int(0.06 * self.fs)
        audio = np.concatenate([np.zeros(pad), audio, np.zeros(pad)])
        peak = np.max(np.abs(audio)) + 1e-12
        audio = audio / peak * 0.95

        self.last_plan = plan
        self.last_phonemes = " | ".join(
            f"{w.get('orth')}:{ ' '.join(w.get('phones') or [])}"
            for w in plan.get("words") or []
        )
        self.last_meta = {
            "engine": "si_formant_klatt",
            "not_neural_tts": True,
            "honest_target": "intelligible_robotic_formant",
            "fs": self.fs,
            "n_phones": sum(len(w["phones"]) for w in words),
            "phonemes": self.last_phonemes,
            "render": "utterance_plan_word_at_a_time",
            "plan_fingerprint": plan_fingerprint(plan),
            "utterance_plan": public_plan_view(plan),
            "spectral": spectral_formant_summary(audio, self.fs),
            "outer_voice": plan.get("outer_voice"),
            "monologue": plan.get("monologue"),
        }

        if keep_session:
            if utterance_id and usess.get_session(utterance_id):
                usess.update_session(
                    utterance_id,
                    plan=plan,
                    text=plan.get("source_text") or "",
                    seed=seed,
                    fs=self.fs,
                    pass_record={"kind": "render", "fingerprint": plan_fingerprint(plan)},
                )
                self.last_utterance_id = utterance_id
            else:
                uid = usess.create_session(
                    plan=plan,
                    text=plan.get("source_text") or "",
                    seed=seed,
                    fs=self.fs,
                )
                self.last_utterance_id = uid
            self.last_meta["utterance_id"] = self.last_utterance_id
            self.last_meta["stock"] = "utterance_plan"

        return audio

    def synthesize(
        self,
        text: str,
        seed: int = 25,
        *,
        use_llm: Optional[bool] = None,
        keep_session: bool = True,
        plan: Optional[dict] = None,
    ) -> np.ndarray:
        """Return mono float64 audio in [-1, 1]. Compiles plan then renders."""
        text = (text or "").strip()
        if not text and plan is None:
            return np.zeros(int(0.1 * self.fs), dtype=np.float64)
        if plan is None:
            plan = self.compile_plan(text, use_llm=use_llm)
        else:
            self.last_plan = plan
        return self.synthesize_plan(plan, seed=seed, keep_session=keep_session)

    def apply_pass(
        self,
        utterance_id: str,
        knobs: Optional[dict] = None,
        *,
        seed: Optional[int] = None,
        output_path: Optional[str] = None,
    ) -> dict[str, Any]:
        """Multi-pass: re-render stock plan with prosody knobs (no re-G2P)."""
        s = usess.get_session(utterance_id)
        if not s or not s.get("plan"):
            raise ValueError(f"unknown or empty utterance_id: {utterance_id}")
        plan = apply_pass_knobs(s["plan"], knobs or {})
        seed_i = int(seed if seed is not None else s.get("seed") or 25)
        audio = self.synthesize_plan(
            plan, seed=seed_i, keep_session=True, utterance_id=utterance_id,
        )
        out: dict[str, Any] = {
            "utterance_id": utterance_id,
            "audio": audio,
            "meta": dict(self.last_meta),
            "plan": public_plan_view(plan),
            "knobs": knobs or {},
        }
        if output_path:
            out["path"] = self._write_wav(audio, output_path)
        return out

    def apply_pass_message(
        self,
        utterance_id: str,
        message: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Parse chat-like pass language into knobs then apply_pass."""
        knobs = classify_speech_pass(message) or {}
        if not knobs:
            raise ValueError(f"no speech pass knobs in message: {message!r}")
        return self.apply_pass(utterance_id, knobs, **kwargs)

    def run_playlist(
        self,
        utterance_id: str,
        playlist: str = "clear",
        *,
        seed: int = 25,
    ) -> List[dict[str, Any]]:
        steps = usess.PLAYLISTS.get(playlist) or usess.PLAYLISTS["clear"]
        results = []
        for step in steps:
            r = self.apply_pass(utterance_id, step.get("knobs") or {}, seed=seed)
            r["playlist_step"] = step.get("label")
            # drop huge audio arrays from list copies for API-ish use optional
            results.append(r)
        return results

    def _write_wav(self, audio: np.ndarray, output_path: str) -> str:
        pcm = np.clip(audio, -1.0, 1.0)
        pcm_i16 = (pcm * 32767.0).astype(np.int16)
        out = str(output_path)
        parent = os.path.dirname(os.path.abspath(out))
        if parent:
            os.makedirs(parent, exist_ok=True)
        wavfile.write(out, self.fs, pcm_i16)
        sr, data = wavfile.read(out)
        if str(data.dtype) != "int16":
            raise RuntimeError(f"WAV dtype must be int16, got {data.dtype}")
        return out

    def speak(
        self,
        text: str,
        output_path: str = "larynx_vocal.wav",
        *,
        seed: int = 25,
        use_llm: Optional[bool] = None,
        keep_session: bool = True,
    ) -> str:
        """Synthesize and write int16 WAV. Returns output path."""
        print(f"🎬 Formant vocalizing: '{text}'...")
        audio = self.synthesize(
            text, seed=seed, use_llm=use_llm, keep_session=keep_session,
        )
        out = self._write_wav(audio, output_path)
        print(f"💾 Larynx formant WAV: {out}  sr={self.fs} dtype=int16 samples={len(audio)}")
        print(f"   phonemes: {self.last_phonemes}")
        if self.last_utterance_id:
            print(f"   utterance_id: {self.last_utterance_id} (stock=utterance_plan)")
        sp = self.last_meta.get("spectral") or {}
        print(f"   spectral peak/mean={sp.get('peak_mean_ratio')} bands={sp.get('band_energy')}")
        return out


def _self_check_imports() -> None:
    banned = (
        "pyttsx3", "espeak", "piper", "coqui", "TTS", "torch", "tensorflow",
        "torchaudio", "gtts", "elevenlabs", "openai", "whisper", "vosk",
    )
    base = Path(__file__).resolve().parent
    for name in (
        "larynx_vocalizer.py", "formant_engine.py", "formant_g2p.py",
        "formant_plan.py", "formant_session.py",
    ):
        path = base / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for b in banned:
            if f"import {b}" in text or f"from {b}" in text:
                raise RuntimeError(f"Banned import of {b} in {name}")


if __name__ == "__main__":
    _self_check_imports()
    vocalizer = LarynxVocalizer(sample_rate=16000)
    prompt = "Hello world"
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
    out = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "larynx_vocal.wav",
    )
    vocalizer.speak(prompt, out)
    uid = vocalizer.last_utterance_id
    if uid:
        vocalizer.apply_pass(uid, {"slower": True, "rising_final": True},
                             output_path=out.replace(".wav", "_pass.wav"))
        print("multi-pass wrote", out.replace(".wav", "_pass.wav"))
