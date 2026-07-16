# Technical Design: Action Sharding (Vibrational Task Execution)

## Overview
Synthesus 5 performs system tasks without using separate "Tool-Calling" models. Instead, it uses **Action Sharding**, where OS operations (Shell commands, File I/O, Network calls) are grounded as high-resonance **Control Frequencies** in the 5-axis geometric space.

## 1. The Action Coordinate Map [CHAL-Action]

We map common Linux operations to specific geometric "Command Peaks":

| Operation | Concept Anchor | Geometric Resonance [X, Y, Z, Φ, Σ] | Action Trigger |
| :--- | :--- | :--- | :--- |
| **Discovery** | "list", "show" | [0.5, 0.2, 0.1, 0.4, 0.9] | `ls -lh` |
| **Ingestion** | "read", "load" | [0.5, 0.3, 0.5, 0.2, 0.8] | `cat` / `read_file` |
| **Crystallization** | "save", "create" | [0.5, 0.5, 0.9, 0.1, 0.9] | `write_file` / `mkdir` |
| **Navigation** | "go", "move" | [0.8, 0.5, 0.2, 0.6, 0.7] | `cd` / `mv` |

## 2. Resonance-Based Execution
The kernel monitors the **Global Interference Point** of the user's conversation. 

1.  **Vibrational Threshold:** When a user's query (e.g., *"Einstein, show me the science shards"*) creates a constructive peak that aligns with the **Discovery** coordinate, the `ActionRouter` is activated.
2.  **Harmonic Verification:** The kernel checks if the active agent's **Scale (Axis 5)** supports the action. A "High Scale" agent (like a system administrator shard) can execute destructive commands, while a "Low Scale" agent (like a scholarly shard) is restricted to read-only discovery.
3.  **Physical Instruction:** The kernel triggers the standard POSIX instruction directly from the 5-axis resonance peak.

## 3. Implementation: The Action Shard (`action_system.kn`)
This shard acts as the **"Motor Cortex"** of the OS. It is always loaded in high-priority RAM.

1.  **Grounding:** Maps every standard `bin/` utility to its geometric "Intent."
2.  **Safety:** Defines "Dissonant Coordinates"—regions of the geometric map that are restricted (e.g., root-level deletions) unless specific harmonic keys are provided.

## 4. Why this is Sovereign
Traditional AIs use "Function Definitions" in JSON. Action Sharding uses **Pure Geometry**. This means the AI doesn't "decide" to call a tool; it **physically resonates** into the action. It is a faster, more secure, and mathematically transparent way to bridge intelligence to the hardware.
