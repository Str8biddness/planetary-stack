# 5-Axis Geometric Engine (SLLM Core) — Technical Specification

## Overview
The Geometric Engine is the native C++ implementation of the **Synthetic Large Language Model (SLLM)** core. It provides a deterministic, non-neural mapping between symbolic language (text) and a 5-dimensional geometric space.

This engine is used by the **Virtual SLLM Device** in the AIOS kernel to predict tokens through **Geometric Resonance**.

## The 5-Axis Logic [CHAL]
Each word or token is mapped to a vector $V = [X, Y, Z, \text{Phase}, \text{Scale}]$ where each component is normalized to the range $[0.0, 1.0]$.

| Axis | Name | Description | Derivation |
| :--- | :--- | :--- | :--- |
| 1 | **X** | Spatial Dimension 1 | Hash Bits 0-15 |
| 2 | **Y** | Spatial Dimension 2 | Hash Bits 16-31 |
| 3 | **Z** | Spatial Dimension 3 | Hash Bits 32-47 |
| 4 | **Phase** | Temporal/Frequency Resonance | Hash Bits 48-63 |
| 5 | **Scale** | Intensity/Importance | Hash Bits 64-95 |

## Deterministic Mapping
The mapping is stateless and deterministic. It uses a dual-hash approach (simulating the behavior of MD5/SHA) to ensure that the same string always projects to the same geometric point.

- **Primary Hash:** djb2 (64-bit) for axes X, Y, Z, and Phase.
- **Secondary Hash:** fnv1a (32-bit) for the Scale axis.

## Geometric Resonance Calculation
To predict the next token in a sequence:

1.  **Constructive Interference Point ($P$):**
    The engine calculates the weighted center of the context vectors $V_i$.
    $$P = \frac{\sum (V_i \times w_i)}{\sum w_i}$$
    where $w_i$ is a combination of the word's inherent **Scale** and its **Recency** in the context.

2.  **Resonance Score:**
    Candidates are ranked by their **Cosine Similarity** to the interference point $P$.
    $$\text{Resonance}(C, P) = \frac{C \cdot P}{\|C\| \|P\|}$$

## Quantum Acoustics (The Larynx)
The **VoiceVCU** (Larynx) translates 5-axis resonance directly into acoustic properties, creating a deterministic synthetic voice.

| Axis | Acoustic Property | Range |
| :--- | :--- | :--- |
| **Y** | pitch | 220Hz - 880Hz |
| **X/Z** | timbre | harmonic distribution |
| **Phase** | resonance | temporal vibration intensity |
| **Scale** | amplitude | 0.0 - 1.0 volume |

### Larynx VCU Process:
1.  **Ingestion:** Receives a string of tokens.
2.  **Projection:** Each token is mapped to a `GeometricVector`.
3.  **Synthesis:** Each vector is rendered into a `VocalProfile` (Pitch, Timbre, Resonance, Amplitude).
4.  **Emission:** The sequence of profiles is streamed to the audio hardware as a 'Harmonic Breath'.

## Integration
- **Kernel:** `packages/kernel/geometric_engine.cpp`, `packages/kernel/voice_vcu.cpp`
- **MMIO:** Integrated into `VirtualSllmDevice` (Base: `0xF6000000`)
- **Python:** Available via `_synthesus_kernel.GeometricEngine` and future `VoiceVCU` bindings.

## Usage (Python Bridge)
```python
import _synthesus_kernel as kernel

ge = kernel.GeometricEngine()
vec = ge.word_to_vector("intelligence")
results = ge.predict_next("artificial", ["intelligence", "garden", "cloud"])
# Results: [{'word': 'intelligence', 'resonance': 0.98...}, ...]
```
