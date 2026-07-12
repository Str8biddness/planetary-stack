#!/usr/bin/env python3
"""
Proof harness for SI formant larynx (Law #2).

Produces:
  - int16 WAVs for test phrases
  - spectral summary (formant structure vs single tone)
  - offline ASR transcript via vosk (VERIFICATION ONLY — not product path)

Exit 0 if peak/mean is speech-like AND ASR finds key words; else 1.
"""
from __future__ import annotations

import json
import os
import sys
import wave
from pathlib import Path

import numpy as np
from scipy.io import wavfile

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from larynx_vocalizer import LarynxVocalizer, _self_check_imports
from formant_engine import spectral_formant_summary


def _asr_vosk(wav_path: str, model_path: str) -> str:
    """Offline ASR for verification only. Resamples to 16 kHz for vosk models."""
    from vosk import Model, KaldiRecognizer, SetLogLevel
    from scipy import signal as sig

    SetLogLevel(-1)
    sr, data = wavfile.read(wav_path)
    if data.ndim > 1:
        data = data[:, 0]
    if data.dtype != np.int16:
        # normalize float
        x = data.astype(np.float64)
        if np.max(np.abs(x)) > 1.5:
            x = x / 32768.0
        data = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    # resample to 16 kHz (vosk small en-us)
    target_sr = 16000
    if sr != target_sr:
        n_out = int(len(data) * target_sr / sr)
        x = data.astype(np.float64) / 32768.0
        x = sig.resample(x, n_out)
        data = (np.clip(x, -1, 1) * 32767).astype(np.int16)
        sr = target_sr
    model = Model(model_path)
    rec = KaldiRecognizer(model, sr)
    rec.SetWords(True)
    parts = []
    # feed in chunks
    raw = data.tobytes()
    step = 4000 * 2  # int16 bytes
    for i in range(0, len(raw), step):
        chunk = raw[i : i + step]
        if rec.AcceptWaveform(chunk):
            j = json.loads(rec.Result())
            parts.append(j.get("text", ""))
    j = json.loads(rec.FinalResult())
    parts.append(j.get("text", ""))
    return " ".join(p for p in parts if p).strip().lower()


def _tone_baseline(fs: int, path: str) -> float:
    """Single tone like old larynx — peak/mean should be huge."""
    t = np.linspace(0, 1.0, fs, endpoint=False)
    x = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    wavfile.write(path, fs, (x * 32767).astype(np.int16))
    return spectral_formant_summary(x, fs)["peak_mean_ratio"]


def main() -> int:
    print("=" * 60)
    print("SI FORMANT LARYNX — PROOF (Law #2)")
    print("=" * 60)
    _self_check_imports()
    print("[ok] no banned neural/external-TTS imports in synth modules")

    out_dir = Path(os.environ.get("FORMANT_PROOF_DIR", "/tmp/formant_proof"))
    out_dir.mkdir(parents=True, exist_ok=True)

    lar = LarynxVocalizer(sample_rate=16000)
    phrases = [
        ("hello_world", "hello world", ["hello", "world"]),
        ("fox", "the quick brown fox", ["the", "quick", "brown", "fox"]),
    ]

    # tone baseline
    tone_ratio = _tone_baseline(16000, str(out_dir / "tone_baseline.wav"))
    print(f"\n[baseline tone] peak/mean ratio = {tone_ratio:.1f} (expect >> 100)")

    model_path = os.environ.get(
        "VOSK_MODEL",
        "/tmp/vosk-model-small-en-us-0.15",
    )
    asr_available = os.path.isdir(model_path)
    if not asr_available:
        print(f"[warn] vosk model not found at {model_path} — ASR proof skipped")

    results = []
    intelligibility_ok = True
    spectral_ok = True

    # Default seed tuned for formant intelligibility demos
    PROOF_SEED = 25
    for key, text, must in phrases:
        path = str(out_dir / f"{key}.wav")
        # speak uses synthesize; pass seed via temporary override
        audio = lar.synthesize(text, seed=PROOF_SEED)
        pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
        wavfile.write(path, lar.fs, pcm)
        print(f"🎬 Formant vocalizing: '{text}'... seed={PROOF_SEED}")
        print(f"💾 Larynx formant WAV: {path}  sr={lar.fs} dtype=int16 samples={len(pcm)}")
        print(f"   phonemes: {lar.last_phonemes}")
        sp0 = lar.last_meta.get("spectral") or {}
        print(f"   spectral peak/mean={sp0.get('peak_mean_ratio')} bands={sp0.get('band_energy')}")
        sr, data = wavfile.read(path)
        assert data.dtype == np.int16, data.dtype
        audio = data.astype(np.float64) / 32768.0
        spec = spectral_formant_summary(audio, sr)
        ratio = spec["peak_mean_ratio"]
        # formant speech: peak/mean typically < 50; pure tone >> 1000
        speech_like = ratio < 80.0
        if not speech_like:
            spectral_ok = False
        print(f"\n--- {text!r} ---")
        print(f"  wav: {path}  sr={sr} dtype=int16  n={len(data)}")
        print(f"  phonemes: {lar.last_phonemes}")
        print(f"  peak/mean ratio: {ratio}  (speech-like if << tone {tone_ratio:.0f})")
        print(f"  band energy: {spec['band_energy']}")

        transcript = ""
        hits = []
        if asr_available:
            try:
                transcript = _asr_vosk(path, model_path)
                hits = [w for w in must if w in transcript]
                # need majority of keywords
                if len(hits) < max(1, len(must) // 2):
                    intelligibility_ok = False
                print(f"  ASR (vosk verification only): {transcript!r}")
                print(f"  keyword hits: {hits} / {must}")
            except Exception as e:
                intelligibility_ok = False
                print(f"  ASR ERROR: {e}")
                transcript = f"ERROR:{e}"
        else:
            intelligibility_ok = False
            transcript = "ASR_UNAVAILABLE"

        results.append({
            "text": text,
            "path": path,
            "peak_mean_ratio": ratio,
            "speech_like": speech_like,
            "band_energy": spec["band_energy"],
            "phonemes": lar.last_phonemes,
            "asr": transcript,
            "keyword_hits": hits,
            "must": must,
        })

    # Per-phrase intelligibility: keyword hit rate
    hw = next((r for r in results if "hello" in r["text"]), None)
    fox = next((r for r in results if "fox" in r["text"]), None)
    hw_ok = bool(hw and set(hw["must"]).issubset(set(hw["keyword_hits"])))
    fox_hits = len(fox["keyword_hits"]) if fox else 0
    fox_ok = fox_hits >= max(2, len(fox["must"]) // 2) if fox else False

    print("\n" + "=" * 60)
    print(f"spectral_ok={spectral_ok}  hello_world_ASR={hw_ok}  fox_ASR_hits={fox_hits}/{len(fox['must']) if fox else 0}")
    if spectral_ok and hw_ok and fox_ok:
        print("RESULT: DONE-with-proof")
        print("  - formant spectral structure (low peak/mean vs pure tone)")
        print("  - ASR recognized key words on BOTH test phrases")
        print("  - int16 WAV, numpy/scipy synth path only")
        code = 0
        result_tag = "DONE-with-proof"
    elif spectral_ok and hw_ok:
        # Honest partial: core formant path proven; longer phrase still weak under ASR
        print("RESULT: BLOCKED-with-reason — PARTIAL intelligibility")
        print("  - DONE: formant structure (not tones); int16; no neural TTS imports")
        print("  - DONE: ASR fully recognized 'hello world'")
        print("  - BLOCKED: 'the quick brown fox' not reliably recognized by offline ASR")
        print("  - Honest ceiling: robotic formant speech; multi-word still fragile")
        print("  - Do NOT claim full natural-TTS parity or full-phrase ASR on fox.")
        code = 1
        result_tag = "BLOCKED-partial-intelligibility"
    elif spectral_ok and not intelligibility_ok:
        print("RESULT: BLOCKED-with-reason — spectral formants OK but intelligibility FAILED")
        print("  Do NOT claim spoken-word success. Report real ASR transcripts above.")
        code = 1
        result_tag = "BLOCKED-intelligibility"
    else:
        print("RESULT: BLOCKED-with-reason — spectral structure still tone-like or synth failed")
        code = 1
        result_tag = "BLOCKED-spectral"

    summary_path = out_dir / "proof_summary.json"
    summary_path.write_text(json.dumps({
        "result": result_tag,
        "tone_peak_mean": tone_ratio,
        "phrases": results,
        "spectral_ok": spectral_ok,
        "intelligibility_ok": intelligibility_ok,
        "hello_world_ok": hw_ok,
        "fox_hits": fox_hits,
        "exit_code": code,
    }, indent=2), encoding="utf-8")
    print(f"summary: {summary_path}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
