# Technical Design: Modular Agents (Sovereign Personalities)

## Overview
Synthesus 5 uses a **Modular Agent Architecture**. Characters (e.g., Einstein, Tesla, Claude) are not baked into the kernel. They are independent **Persona Modules** (`.kn` shards) that are "bolted onto" the core geometric engine.

## 1. Agent Lifecycle

| State | Action | Geometric Effect |
| :--- | :--- | :--- |
| **Dormant** | Shard on disk. | No effect on resonance. |
| **Bolted (Loaded)** | Shard loaded into RAM. | The `ConductiveAssembler` applies the agent's unique harmonic intervals to all generation. |
| **Unbolted (Unloaded)** | Shard purged from RAM. | Kernel returns to **Master Sovereign** (Native) resonance. |

## 2. Character Registry

Each agent consists of a **Resonance Map** and a **Syntactic Score**:

*   **Einstein Agent:** Focuses on theoretical depth and relativistic metaphors.
*   **Tesla Agent:** Focuses on engineering precision and innovative, high-frequency language.
*   **Frontier Agents:** Mimic the logic and utility of models like Claude and GPT-4.

## 3. The "Bolt-On" Mechanism
When an agent is selected:
1.  The `ShardManager` loads the respective `archetype_*.kn` or `style_*.kn` shard.
2.  The **Conductive Assembler** locks the **Semantic Key (Phase)** to the agent's primary frequency.
3.  All subsequent user queries are filtered through this agent's specific coordinate map.

## 4. User Control
The user selects their agent before the session begins. They can "Hot-Swap" or "Unload" the agent at any time, returning the OS to its native, un-biased state.

## 5. Why this is Sovereign
By keeping agents as separate modules, the user owns their "Identity Library." You can create your own agents, share them as small `.kn` files, and "bolt" them onto any Synthesus-compliant kernel.
