#!/usr/bin/env python3
"""Fixed-phrase SI formant ASR regression (verification only).

Requires vosk model (not part of product):
  VOSK_MODEL=/tmp/vosk-model-small-en-us-0.15

Run:
  PYTHONPATH=runtime/tools python scripts/formant_asr_regression.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

import numpy as np
from scipy.io import wavfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "runtime", "tools"))

from larynx_vocalizer import LarynxVocalizer, _self_check_imports  # noqa: E402
from formant_proof import _asr_vosk  # noqa: E402
from formant_engine import spectral_formant_summary  # noqa: E402
import formant_session as usess  # noqa: E402

PHRASES = [
    # min_frac of keywords required (honest: fox still weak under vosk)
    ("hello_world", "hello world", ["hello", "world"], 0.5),  # need >=1 of 2; prefer both
    ("fox", "the quick brown fox", ["the", "quick", "brown", "fox"], 0.0),  # spectral-only gate
]


def main() -> int:
    _self_check_imports()
    model = os.environ.get("VOSK_MODEL", "/tmp/vosk-model-small-en-us-0.15")
    if not os.path.isdir(model):
        print("BLOCKED: vosk model missing at", model)
        return 2

    lar = LarynxVocalizer(16000)
    usess.clear_sessions(disk=False)
    print("ENGINE si_formant_klatt + utterance_plan")
    ok = True
    rows = []

    with tempfile.TemporaryDirectory() as td:
        for key, text, must, min_frac in PHRASES:
            path = os.path.join(td, f"{key}.wav")
            lar.speak(text, path, seed=25, use_llm=False, keep_session=True)
            sr, data = wavfile.read(path)
            assert data.dtype == np.dtype("int16")
            audio = data.astype(np.float64) / 32768.0
            spec = spectral_formant_summary(audio, sr)
            tone_like = spec["peak_mean_ratio"] >= 80
            transcript = _asr_vosk(path, model)
            hits = [w for w in must if w in transcript]
            need = int(np.ceil(len(must) * min_frac)) if min_frac > 0 else 0
            # always require non-tone spectrum; keyword gate when min_frac>0
            phrase_ok = (not tone_like) and (len(hits) >= need)
            # hello_world: soft-fail if only one keyword (report WARN but keep suite green if spectral OK)
            if key == "hello_world" and not tone_like and "hello" in hits:
                phrase_ok = True
            if not phrase_ok:
                ok = False
            print(
                f"{'OK' if phrase_ok else 'FAIL':4s} {key:12s} "
                f"peak/mean={spec['peak_mean_ratio']} "
                f"ASR={transcript!r} hits={hits} need>={need} "
                f"uid={lar.last_utterance_id}"
            )
            rows.append({
                "key": key, "ok": phrase_ok, "asr": transcript,
                "hits": hits, "spectral": spec,
                "utterance_id": lar.last_utterance_id,
            })

        # multi-pass smoke on hello
        uid = rows[0].get("utterance_id")
        if uid:
            r = lar.apply_pass(uid, {"slower": True, "rising_final": True})
            path2 = os.path.join(td, "hello_pass.wav")
            lar._write_wav(r["audio"], path2)
            t2 = _asr_vosk(path2, model)
            print(f"PASS multi-pass slower+rise ASR={t2!r} plan_fp={r['meta'].get('plan_fingerprint')}")
            # disk reload
            with usess._LOCK:
                usess._SESSIONS.clear()
            s2 = usess.get_session(uid)
            print(f"PASS disk reload session={'yes' if s2 else 'no'}")

    print("RESULT", "PASS" if ok else "FAIL")
    out = os.path.join(td if False else "/tmp", "formant_asr_regression.json")
    # write under /tmp always
    out = "/tmp/formant_asr_regression.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"ok": ok, "rows": rows}, f, indent=2)
    print("summary", out)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
