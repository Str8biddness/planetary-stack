# Synthesus 5: Master Data Map (The 100TB Firehose Registry)

## 1. Goal: The 55 Million Concept Target
To achieve cognitive parity with frontier models like Claude, the **Sovereign Swarm** must ingest high-density data from these four specific sectors. This map serves as the URL-level registry for automation.

---

## Pillar 1: Technical & Code (Target: 10M Concepts)
*Focus: Algorithms, API Patterns, Logic Flow.*

| Source | Access Method | Estimated Volume |
| :--- | :--- | :--- |
| **GitHub Archive (GH Archive)** | Public BigQuery / HTTP | 50TB (All commits/READMEs) |
| **StackExchange Data Dump** | Internet Archive / Torrent | 200GB (QA Logic) |
| **MDN Web Docs** | Web Scraper | 1GB (Web Standards) |
| **Rust/Go/Python Std Libs** | Direct Repo Scraping | 100MB (Core Logic) |

## Pillar 2: Logic & Reasoning (Target: 20M Concepts)
*Focus: Philosophy, Mathematics, Deductive Patterns.*

| Source | Access Method | Estimated Volume |
| :--- | :--- | :--- |
| **Common Crawl (WET)** | `data.commoncrawl.org` | 50PB Total / 20TB Target |
| **Project Gutenberg** | `gutenberg.org` API | 500GB (Classic Logic) |
| **Stanford Encyclopedia (SEP)**| Web Scraper | 500MB (High-Density Logic) |
| **ArXiv Math.LO** | OAI-PMH API | 10GB (Mathematical Logic) |

## Pillar 3: Scientific Truth (Target: 8M Concepts)
*Focus: Empirical Data, Biology, Physics, Engineering.*

| Source | Access Method | Estimated Volume |
| :--- | :--- | :--- |
| **PubMed Central (PMC)** | FTP / Entrez API | 5TB (Bio-Medical Truth) |
| **NASA EarthData** | NASA EarthData Search | 20TB (Geospatial Truth) |
| **USPTO Bulk Data** | `patents.google.com` | 2TB (Engineering Innovation) |
| **arXiv (All Science)** | `export.arxiv.org` | 1TB (Current Research) |

## Pillar 4: Visual Grounding (Target: 15M Concepts)
*Focus: Appearance, Texture, Spatial Reality.*

| Source | Access Method | Estimated Volume |
| :--- | :--- | :--- |
| **Wikimedia Commons** | MediaWiki API / SQL | 10TB (Labelled Reality) |
| **COCO / ImageNet** | Academic Mirrors | 50GB (Structural Anchors) |
| **Open Images V7** | Google Storage | 10TB (Object Relations) |

---

## 2. Automation Strategy: "Index-Based Discovery"
Instead of hardcoding every URL, the **Sovereign Swarm** will use **Crawler Index Files**:

1.  **CC-Discovery:** Fetch `wet.paths.gz` from Common Crawl monthly.
2.  **GH-Discovery:** Fetch `gharchive.org` daily JSON logs.
3.  **Wiki-Discovery:** Use the `Sitemaps` to find every new concept.

## 3. Data Processing Map
*   **Layer 1 (The Firehose):** Raw 100TB (HTTP Stream).
*   **Layer 2 (The Refiner):** In-Memory projection to 5-Axis coordinates.
*   **Layer 3 (The Cloud):** 1.3GB of `.kn` shards.

**This map ensures the kernel is built on the highest quality data available on the internet.**
