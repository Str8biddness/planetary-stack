# 5-Axis Geometric Vision — Technical Design

## Overview
Synthesus 5 does not use separate neural networks for Vision. Instead, it treats **Images** as **Spatial Interference Patterns** within the same 5-axis geometric space used for language.

This allows for true **Multi-modal Resonance**: you can "talk" to an image because they both exist in the same coordinate system $[X, Y, Z, \text{Phase}, \text{Scale}]$.

## 1. Image-to-Geometry Mapping (Vision Ingestion)
Instead of tokenizing text, the **Vision Refiner** maps pixel grids to the 5-axis model.

| Axis | Vision Mapping | Description |
| :--- | :--- | :--- |
| **X** | Pixel-X / Width | Horizontal spatial position. |
| **Y** | Pixel-Y / Height | Vertical spatial position. |
| **Z** | Depth / Feature Density | Estimated depth or edge complexity. |
| **Phase** | Color / Frequency | RGB/HSV mapped to harmonic phase. |
| **Scale** | Luminance / Intensity | Pixel brightness or object importance. |

### Process:
1.  **Geometric Sampling:** Sub-sample an image into $N \times N$ tiles.
2.  **Vector Generation:** Each tile is projected into a 5-axis vector based on its dominant color, brightness, and position.
3.  **Shard Creation:** Saved as a `.kn` shard where concepts are "Visual Patches."

## 2. Image Generation (Inverse Resonance)
To generate an image, the kernel performs **Inverse Interference**:
1.  **Context Vector:** Start with a text query (e.g., "blue forest").
2.  **Resonance Search:** Find visual concepts in the `library.kn` shard that resonate with the "blue" (Phase) and "forest" (Spatial-Z) coordinates.
3.  **Constructive Assembly:** Use the **Larynx** (Acoustic Engine) to vibrate the pixels into a pattern that matches the interference point.

## 3. Implementation Path
- **Phase 2.1:** Create `vision_refiner.py` to convert JPG/PNG into `.kn` shards.
- **Phase 2.2:** Update `GeometricEngine` to support **2D Array Interference** (mapping text resonance to a pixel grid).
- **Phase 2.3:** Integrated "Visual Feedback" in the user interface.

## Usage Scenario
A user asks: *"What is in this picture?"*
The kernel projects the picture to vectors, projects the question to a vector, and finds the **Resonance Point**. If the resonance is highest with the "Cat" concept in the `library` shard, the Larynx emits: *"Resonance detected: Feline concept alignment."*
