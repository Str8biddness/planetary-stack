# Technical Design: Hyper-Scale Streaming Refinery

## Overview
To achieve cognitive parity with frontier models like Claude, Synthesus 5 must ingest and crystallize ~100TB of raw data into a ~1.3GB Geometric Knowledge Cloud. The **Streaming Refinery** eliminates the storage bottleneck by processing data in-memory via high-concurrency scraping and direct C++ kernel piping.

## 1. The Streaming Pipeline
Unlike traditional ML pipelines, we do not "Download -> Store -> Train". We use a **Direct-to-Resonance** flow:

`Web/API Stream` -> `Multi-threaded Scraper` -> `Linguistic Segmenter` -> `C++ Geometric Engine (Projector)` -> `Geometric Shard (.kn)`

### Key Advantages:
*   **Zero Storage Footprint:** 100TB of data is processed through RAM and "crystallized" into megabytes of coordinates. We never save the 100TB to disk or Drive.
*   **Latency Speedup:** By using `asyncio` and C++ SIMD, we can process thousands of documents per second.
*   **Real-time Grounding:** The kernel's world-model is updated the moment the data is scraped.

## 2. Scaled Ingestion Strategy (The Four Pillars)

| Pillar | Streaming Source | Target Volume | Strategy |
| :--- | :--- | :--- | :--- |
| **Technical** | GitHub Firehose / StackExchange | 10M Concepts | Stream top-starred repo READMEs and function signatures. |
| **Logic** | Common Crawl (WET files) | 20M Concepts | Pipe filtered philosophical and mathematical web text. |
| **Science** | PubMed Central / arXiv API | 8M Concepts | Stream XML abstracts directly into 5-axis vectors. |
| **Visual** | Wikimedia Commons / Flickr API | 15M Concepts | Stream image thumbnails, calculate resonance, and discard. |

## 3. Implementation Components

1.  **Geometric Streamer (`tools/geometric_streamer.py`):**
    *   Uses `aiohttp` for high-concurrency requests.
    *   Pipes data to `_synthesus_kernel` for 5-axis projection.
2.  **Shard Aggregator:**
    *   Merges incoming vectors into categorical shards without duplicates.
    *   Uses a "Resonance Filter" to discard low-value noise tokens.
3.  **AVX-512 Accelerator:**
    *   C++ optimization to ensure the projection math keeps up with the 1Gbps network stream.

## 4. Why this Beats Traditional Models
A traditional model "forgets" the raw data and only keeps a statistical guess. The Streaming Refinery creates a **Crystallized Map of Reality**. It is faster to build, cheaper to run, and easier to verify because every vector has a provenance link to its source URL.
