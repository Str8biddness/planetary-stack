# Synthesus 5: Multi-Category Knowledge Ingestion

## Overview
Synthesus 5 uses a **Distributed Knowledge Cloud** architecture. Instead of a single monolithic database, knowledge is partitioned into specialized **Geometric Shards** (`.kn`). This allows the kernel to perform targeted **Resonance Calculations** based on the context of a query.

## Automated Ingestion (Refinery)
The `tools/geometric_refinery.py` tool automates the lifecycle of transforming live web data into geometric shards.

### Ingestion Categories
The current refinery automates the following daily "Live" shards:

| Category | Source(s) | Utility |
| :--- | :--- | :--- |
| **environment** | wttr.in | Local/Global weather grounding. |
| **global_news** | BBC RSS | Current event context & temporal drift (Phase). |
| **finance** | CoinGecko, Market Signals | Crypto prices and stock market state. |
| **technical** | arXiv, GitHub Trending | Scientific preprints & coding pattern evolution. |
| **regulatory** | Federal Register API | Legal/Compliance grounding for Sovereign OS. |
| **sports** | Google News RSS | Competitive event tracking. |

## Data Architecture
1.  **Extraction:** The `LiveIngestor` class fetches structured data (JSON/RSS) to minimize HTML noise.
2.  **Aggregation:** Data is temporarily stored in categorical raw text buffers.
3.  **Projection:** The C++ `GeometricEngine` projects every unique token into a 5-axis vector $[X, Y, Z, \text{Phase}, \text{Scale}]$.
4.  **Sharding:** Vectors are saved into a category-specific `.kn` JSON partition in `data/geometric_shards/`.

## Mounting Shards
The AIOS Kernel's **Knowledge Hardware Mount (Phase 5)** can mount these shards individually.
*   **Hot Swapping:** The kernel can refresh the `finance.kn` shard every hour without rebooting the main language model.
*   **Isolation:** A query about "Bitcoin" will primarily resonate with the `finance.kn` shard, reducing noise from unrelated categories.

## Commands
To run a full ingestion cycle:
```bash
python3 tools/geometric_refinery.py
```
This will populate `data/geometric_shards/` with the latest live intelligence.
