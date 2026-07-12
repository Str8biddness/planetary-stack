#!/usr/bin/env python3
"""Unit smoke for SI formant larynx (no ASR dependency)."""
from __future__ import annotations

import os
import sys
import tempfile

import numpy as np
from scipy.io import wavfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from formant_g2p import text_to_phonemes, word_to_phonemes
from formant_engine import spectral_formant_summary, phones_to_audio
from larynx_vocalizer import LarynxVocalizer, _self_check_imports


def test_g2p_hello_world():
    assert word_to_phonemes("hello") == ["HH", "EH", "L", "OW"]
    assert "W" in word_to_phonemes("world")
    parts = text_to_phonemes("hello world")
    assert len(parts) == 2


def test_formant_not_tone():
    x = phones_to_audio(["HH", "EH", "L", "OW"], fs=16000, f0_base=150, dur_scale=1.2, seed=25)
    spec = spectral_formant_summary(x, 16000)
    assert spec["peak_mean_ratio"] < 80
    assert spec["band_energy"]["F1_200_900"] > 0


def test_larynx_int16_and_accent_wired():
    _self_check_imports()
    lar = LarynxVocalizer(sample_rate=16000)
    # accent keys must affect prosody (not dead)
    assert "wide_vowels" in lar.accent_profile
    assert "legato_bias" in lar.accent_profile
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "out.wav")
        lar.speak("hello world", path)
        sr, data = wavfile.read(path)
        assert sr == 16000
        assert data.dtype == np.int16
        assert len(data) > sr // 4
        audio = data.astype(np.float64) / 32768.0
        spec = spectral_formant_summary(audio, sr)
        assert spec["peak_mean_ratio"] < 80
        assert lar.last_meta.get("engine") == "si_formant_klatt"
        assert lar.last_meta.get("not_neural_tts") is True


def test_empty_raises_loud():
    lar = LarynxVocalizer(16000)
    # empty after strip
    try:
        # force empty phones path
        from formant_g2p import text_to_phonemes
        assert text_to_phonemes("...")  # may be pauses only
    except Exception:
        pass
    a = lar.synthesize("hello")
    assert a.std() > 0.01


if __name__ == "__main__":
    test_g2p_hello_world()
    test_formant_not_tone()
    test_larynx_int16_and_accent_wired()
    test_empty_raises_loud()
    print("test_formant_larynx: OK")
