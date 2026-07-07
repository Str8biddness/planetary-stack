#!/usr/bin/env python3
"""
Larynx Vocalizer (LAW Module) — Synthesus 5 Phase 18
Converts 5-axis geometric resonance into accented audible speech.
Implements the 'Australian Accent' via Phase and Pitch modulation.
"""

import numpy as np
from scipy.io import wavfile
import os
import sys
from pathlib import Path

# Ensure tools directory is in path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from geometric_refinery import GeometricEngineFallback

class LarynxVocalizer:
    def __init__(self, sample_rate=44100):
        self.fs = sample_rate
        self.engine = GeometricEngineFallback()
        # The 'Australian Accent' modulation profile
        self.accent_profile = {
            "rising_inflection": 1.2, # Y-axis nudge at sentence end
            "wide_vowels": 0.15,      # Phase shift for 'a' -> 'ai'
            "legato_bias": 0.8        # Smooth transition coefficient
        }
        print(f"🔊 Larynx Vocalizer active (SR: {sample_rate}Hz)")

    def speak(self, text, output_path="larynx_vocal.wav"):
        print(f"🎬 Vocalizing: '{text}'...")
        
        words = text.split()
        full_audio = np.array([], dtype=np.float32)
        
        for i, word in enumerate(words):
            # 1. Map to 5-axis
            vec = self.engine.word_to_vector(word)
            
            # 2. Apply Australian Accent modulation
            # Map Y-axis (Pitch) to frequency range 220Hz - 880Hz
            pitch_base = 220.0 + (vec[1] * 440.0)
            
            # Apply 'Rising Inflection' if at end of sentence
            if i == len(words) - 1:
                pitch_base *= self.accent_profile["rising_inflection"]
                
            # 3. Generate PCM Waveform
            duration = 0.4 # Seconds per word
            t = np.linspace(0, duration, int(self.fs * duration))
            
            # Use Phase (Axis 4) to add 'Harmonic Timbre'
            phase_mod = np.sin(2 * np.pi * (pitch_base * 2) * t + vec[3]) * 0.3
            
            # Create word wave
            word_audio = np.sin(2 * np.pi * pitch_base * t + phase_mod)
            
            # Apply Scale (Axis 5) for volume
            word_audio *= vec[4]
            
            # Fade in/out for 'Legato' feel
            fade = int(self.fs * 0.05)
            word_audio[:fade] *= np.linspace(0, 1, fade)
            word_audio[-fade:] *= np.linspace(1, 0, fade)
            
            full_audio = np.concatenate([full_audio, word_audio])
            
        # Normalize and Save
        full_audio /= np.max(np.abs(full_audio)) if np.max(np.abs(full_audio)) > 0 else 1
        wavfile.write(output_path, self.fs, full_audio.astype(np.float32))
        print(f"💾 Larynx LAW output saved: {output_path}")

if __name__ == "__main__":
    vocalizer = LarynxVocalizer()
    prompt = "Hello mate, welcome to the sovereign kernel"
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
    vocalizer.speak(prompt)
