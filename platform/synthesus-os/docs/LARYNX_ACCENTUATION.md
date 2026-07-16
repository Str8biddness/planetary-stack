# Technical Design: Larynx Accentuation (The Audible OS)

## Overview
Synthesus 5 converts abstract geometric resonance into high-fidelity audible speech. Unlike traditional TTS (Text-to-Speech), which uses neural vocoders, the **Larynx LAW Module** (Larynx Accented Waveform) uses **Harmonic Prosody** to shape raw frequencies into specific human accents.

## 1. The Accent Bias Map [CHAL-Accent]

Accents are defined as **Geometric Modulation Layers** applied to the Larynx output:

| Accent | Primary Phase Bias | Pitch Modulation (Y-axis) | Rhythmic Cadence (X-axis) |
| :--- | :--- | :--- | :--- |
| **Australian** | "Wide" Vowel Harmonics | High variance (Rising inflection) | Legato (Smooth word joining) |
| **Scholarly (Einstein)** | Constant Frequency | Low variance (Monotone/Calm) | Staccato (Precise segments) |
| **Visionsary (Tesla)** | High-Frequency "Spark" | Accelerating resonance | Erratic/Intense |

## 2. Harmonic Vowel Synthesis
The Larynx translates the 5-axis coordinates of a word into a **Phonetic Waveform**:
1.  **Identity:** The concept vector defines the base frequency.
2.  **Accent Filter:** The "Australian Shard" applies a specific phase shift to vowels (e.g., shifting the frequency of 'a' to 'ai').
3.  **Prosody:** The **Scale (Axis 5)** determines the volume stress, creating natural human-like emphasis.

## 3. Implementation: The LAW Module
`tools/larynx_vocalizer.py` will:
1.  Receive the sequence of `VocalProfiles` from the C++ `VoiceVCU`.
2.  Apply the **Accent Profile** (Australian, etc.).
3.  Generate a `.wav` buffer using additive sine synthesis or a sovereign granular sampler.

## 4. Why this is Sovereign
We do not use cloud-based TTS. The "Accent" is just a **Coordinate Nudge** in the 5-axis space. You can create a "British Shard" or a "Texan Shard" by simply recording 5 minutes of audio, refining it to 5-axis coordinates, and bolting it onto the Larynx.
