#!/usr/bin/env python3
"""Retrieval-quality evaluation harness (Synthesus grounding dial).

Repeatable, NO-MOCK measurement of the RAG grounded-hit rate:

  1. Writes a small known corpus (one distinct fact per short doc).
  2. Ingests it through the REAL folder connector (ingest_folder ->
     ingest_local_tree -> rag.append_patterns), using real MiniLM-384
     embeddings and a real FAISS index.
  3. Runs a fixed set of natural-language questions through the REAL
     RAGPipeline.retrieve() and checks, per question:
        - did the TOP result cite the correct source doc?  (grounded hit)
        - was the top score above the retrieval threshold?
        - did the correct source appear anywhere in top_k?  (recall@k)
  4. Prints a per-question table + overall grounded-hit rate.

It is ISOLATED: it builds its own FAISS index in a scratch directory and
never reads or writes the runtime's data/user_faiss.index, so it is safe to
run against the shared runtime.

Nothing here is faked. The score printed is computed from real retrieve()
output; there is no hardcoded pass/score anywhere.

Usage:
    SYNTHESUS_EMBEDDER=semantic \
        /home/dakin/synthesus-ultra/.venv/bin/python tools/retrieval_eval.py \
        [--top-k 5] [--threshold 0.2] [--keep]

The pipeline dials come from the RAGPipeline defaults unless overridden on the
command line, so this same harness measures BOTH baseline and tuned params.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

# --- import paths (mirror production_server's layout) ---------------------
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))                       # top-level
sys.path.insert(0, str(ROOT / "packages"))          # packages.*
sys.path.insert(0, str(ROOT / "packages" / "core")) # ml.semantic_embedder / ml.swarm_embedder
sys.path.insert(0, str(ROOT / "packages" / "knowledge"))  # connectors.*, knowledge.rag_pipeline

# Default to the production embedder (MiniLM-384) unless the caller set one.
os.environ.setdefault("SYNTHESUS_EMBEDDER", "semantic")

import asyncio  # noqa: E402

from knowledge.rag_pipeline import RAGPipeline           # noqa: E402
from connectors.folder_connector import ingest_folder    # noqa: E402  (REAL connector)


# --- known corpus: distinct facts, but grouped into DISTRACTOR CLUSTERS ---
# Filenames are the ground-truth source labels. Several docs are siblings on
# the same topic (two pancreatic hormones, three planets, two vector-search
# libraries, two mountains, two oceans). That makes top-1 attribution a real
# semantic test: the pipeline must pick the RIGHT sibling, not just the right
# topic. Questions are phrased to avoid heavy keyword overlap.
CORPUS: dict[str, str] = {
    # -- planets (3 siblings) --
    "mercury.md": (
        "# Mercury\n\n"
        "Mercury is the planet nearest to the Sun and completes a full orbit "
        "in only 88 Earth days, giving it the shortest year of any planet."
    ),
    "jupiter.md": (
        "# Jupiter\n\n"
        "Jupiter is the largest planet in the solar system, a gas giant with "
        "more than twice the mass of all the other planets combined."
    ),
    "neptune.md": (
        "# Neptune\n\n"
        "Neptune is the most distant planet from the Sun and has the fiercest "
        "winds in the solar system, with storms exceeding 2,000 kilometres per hour."
    ),
    # -- mountains (2 siblings) --
    "everest.md": (
        "# Everest\n\n"
        "Mount Everest has the highest summit above sea level, its peak reaching "
        "8,849 metres in the Himalayas on the border of Nepal and Tibet."
    ),
    "mauna_kea.md": (
        "# Mauna Kea\n\n"
        "Measured from its base on the ocean floor to its top, Mauna Kea in "
        "Hawaii is the tallest mountain on Earth at over 10,000 metres, though "
        "most of it lies underwater."
    ),
    # -- oceans (2 siblings) --
    "pacific.md": (
        "# The Pacific\n\n"
        "The Pacific Ocean is the largest and deepest body of water on Earth, "
        "covering more surface area than all the planet's land combined."
    ),
    "arctic.md": (
        "# The Arctic\n\n"
        "The Arctic Ocean is the smallest and shallowest of the world's oceans, "
        "and also the coldest, covered by sea ice for much of the year."
    ),
    # -- pancreatic hormones (2 siblings, opposite effects) --
    "insulin.md": (
        "# Insulin\n\n"
        "Insulin is a hormone from the pancreas that LOWERS blood sugar by "
        "signalling cells to take in glucose from the bloodstream."
    ),
    "glucagon.md": (
        "# Glucagon\n\n"
        "Glucagon is a hormone from the pancreas that RAISES blood sugar by "
        "telling the liver to release stored glucose into the bloodstream."
    ),
    # -- vector-search libraries (2 siblings) --
    "faiss.md": (
        "# FAISS\n\n"
        "FAISS is an open-source library from Facebook AI Research for efficient "
        "similarity search over dense vectors using approximate nearest neighbours."
    ),
    "annoy.md": (
        "# Annoy\n\n"
        "Annoy is an open-source approximate nearest-neighbour library built by "
        "Spotify, using random projection trees to search dense vectors quickly."
    ),
    # -- standalone singletons --
    "photosynthesis.md": (
        "# Photosynthesis\n\n"
        "Green plants make their own food through photosynthesis, converting "
        "sunlight, water, and carbon dioxide into glucose and releasing oxygen."
    ),
    "bees.md": (
        "# Honeybee communication\n\n"
        "Honeybees tell nestmates where to find nectar by performing the waggle "
        "dance, whose angle and duration encode the direction and distance to food."
    ),
    "eiffel.md": (
        "# Eiffel Tower\n\n"
        "The Eiffel Tower in Paris was completed in 1889 for the World's Fair "
        "and was the tallest man-made structure on Earth until 1930."
    ),
}

# (question, expected source filename). Sibling clusters force the pipeline to
# distinguish near-neighbours (insulin vs glucagon, everest vs mauna_kea, ...).
QUESTIONS: list[tuple[str, str]] = [
    ("Which planet is nearest to the Sun?", "mercury.md"),
    ("What is the biggest planet in our solar system?", "jupiter.md"),
    ("Which planet has the strongest winds?", "neptune.md"),
    ("Which mountain has the highest point above sea level?", "everest.md"),
    ("Which mountain is tallest when measured from its base?", "mauna_kea.md"),
    ("What is the largest and deepest ocean?", "pacific.md"),
    ("Which ocean is the smallest and coldest?", "arctic.md"),
    ("Which pancreatic hormone lowers blood sugar?", "insulin.md"),
    ("Which pancreatic hormone raises blood sugar?", "glucagon.md"),
    ("What vector similarity search library did Facebook create?", "faiss.md"),
    ("What nearest-neighbour library did Spotify build?", "annoy.md"),
    ("How do bees tell each other where food is?", "bees.md"),
]

# UNANSWERABLE queries: none of these facts are in the corpus. The CORRECT
# behaviour is to ground on NOTHING (top score below threshold -> empty
# retrieval). If a chunk is returned above threshold, that is FALSE grounding:
# the pipeline hands the LLM an irrelevant "source" it will happily cite. This
# is the precision failure a too-low threshold causes, and the real dial we can
# improve without hurting the answerable queries (already at 100%).
NEGATIVES: list[str] = [
    "What is the boiling point of water at sea level?",
    "Who wrote the play Romeo and Juliet?",
    "How do I bake a loaf of sourdough bread?",
    "What is the current exchange rate of the US dollar to the euro?",
    "What programming language was used to write the Linux kernel?",
    "How many players are on a soccer team?",
]


def _src_basename(source: str) -> str:
    """Connector writes source as 'label/relpath'; compare on the filename."""
    return Path(source or "").name


def build_index(corpus_dir: Path, index_dir: Path, top_k: int, threshold: float) -> RAGPipeline:
    """Write corpus to disk and ingest via the REAL folder connector."""
    corpus_dir.mkdir(parents=True, exist_ok=True)
    for name, text in CORPUS.items():
        (corpus_dir / name).write_text(text, encoding="utf-8")

    index_dir.mkdir(parents=True, exist_ok=True)
    rag = RAGPipeline(
        index_path=str(index_dir / "eval_faiss.index"),
        metadata_path=str(index_dir / "eval_meta.json"),
        top_k=top_k,
        score_threshold=threshold,
    )
    added, files, label = ingest_folder(rag, str(corpus_dir), namespace="eval_corpus")
    if added == 0:
        raise SystemExit("DEGRADE LOUDLY: folder connector ingested 0 chunks — aborting.")
    return rag


async def run_eval(rag: RAGPipeline, top_k: int, threshold: float) -> dict:
    rows = []
    hits = 0
    recall_k = 0
    for q, expected in QUESTIONS:
        # Retrieve WITHOUT the threshold gate so we always see the true top
        # result + its score, then apply the threshold ourselves. This makes
        # the effect of the threshold visible in the table.
        res = await rag.retrieve(q, top_k=top_k, score_threshold=-1.0)
        sources = res.get("sources", [])
        if sources:
            top = sources[0]
            top_src = _src_basename(top.get("source", ""))
            top_score = top.get("score", 0.0)
        else:
            top_src, top_score = "(none)", 0.0

        in_topk = any(_src_basename(s.get("source", "")) == expected for s in sources[:top_k])
        top_correct = top_src == expected
        passed = top_correct and top_score >= threshold

        if passed:
            hits += 1
        if in_topk:
            recall_k += 1

        rows.append({
            "q": q, "expected": expected, "top_src": top_src,
            "top_score": top_score, "top_correct": top_correct,
            "in_topk": in_topk, "passed": passed,
        })

    # --- unanswerable queries: correct behaviour is to ground on NOTHING ---
    neg_rows = []
    false_grounding = 0
    for q in NEGATIVES:
        res = await rag.retrieve(q, top_k=top_k, score_threshold=-1.0)
        sources = res.get("sources", [])
        top_score = sources[0].get("score", 0.0) if sources else 0.0
        top_src = _src_basename(sources[0].get("source", "")) if sources else "(none)"
        # Above threshold => the pipeline WOULD hand this junk to the LLM.
        grounded = bool(sources) and top_score >= threshold
        if grounded:
            false_grounding += 1
        neg_rows.append({
            "q": q, "top_src": top_src, "top_score": top_score,
            "false_grounding": grounded,
        })

    n = len(QUESTIONS)
    n_neg = len(NEGATIVES)
    correct_rejections = n_neg - false_grounding
    # Combined precision-aware score: reward true grounded hits AND correct
    # rejections of unanswerable queries, over the whole query set.
    overall = (hits + correct_rejections) / (n + n_neg)
    return {
        "rows": rows,
        "neg_rows": neg_rows,
        "n": n,
        "n_neg": n_neg,
        "hits": hits,
        "recall_k": recall_k,
        "false_grounding": false_grounding,
        "correct_rejections": correct_rejections,
        "grounded_hit_rate": hits / n,
        "recall_at_k": recall_k / n,
        "false_grounding_rate": false_grounding / n_neg if n_neg else 0.0,
        "overall_quality": overall,
    }


# --- REAL-INDEX calibration probe ----------------------------------------
# The synthetic corpus above is clean prose and scores high (0.6+). REAL
# ingested content (code, notes) embeds LOWER, so a threshold tuned only on
# the toy corpus would over-filter production. This mode reads the ACTUAL
# runtime index READ-ONLY and reports the empirical safe-threshold window:
# the ceiling of off-topic (junk) scores must sit BELOW the floor of true
# on-topic hits; any threshold strictly between them is safe.
#
# On-topic probes are (query, expected source substring). They are only
# scored as "hits" if the top source actually matches — if the runtime index
# no longer contains these files the mode degrades LOUDLY (misses), it never
# fabricates a window.
REAL_ONTOPIC: list[tuple[str, str]] = [
    ("how does the folder connector ingest a directory", "folder_connector.py"),
    ("how are text chunks created from a file", "base.py"),
    ("how does the rclone connector mount a remote", "rclone_connector.py"),
    ("what does the connector registry expose", "registry.py"),
]
REAL_OFFTOPIC: list[str] = [
    "What is the boiling point of water at sea level?",
    "Who wrote the play Romeo and Juliet?",
    "How do I bake a loaf of sourdough bread?",
    "What is the capital of Japan?",
    "How many players are on a soccer team?",
    "What is the speed of light in a vacuum?",
]


async def run_real_index_probe(index_path: str, metadata_path: str, threshold: float) -> int:
    """READ-ONLY probe of the live runtime index. Prints on-topic hit scores,
    off-topic junk scores, and the empirical safe-threshold window. Never saves."""
    if not Path(index_path).exists():
        print(f"DEGRADE LOUDLY: real index not found at {index_path}")
        return 1
    rag = RAGPipeline(index_path=index_path, metadata_path=metadata_path,
                      top_k=5, score_threshold=-1.0)
    print("=" * 100)
    print(f"REAL-INDEX CALIBRATION PROBE (read-only)  |  vectors={rag.total_vectors}  "
          f"index={index_path}")
    print("=" * 100)

    on_scores = []
    print("ON-TOPIC probes (expected source must match; score is the recall floor):")
    print(f"{'':>2}  {'HIT':<5} {'score':>6}  {'expected~':<22} {'got':<22} query")
    for q, expect in REAL_ONTOPIC:
        res = await rag.retrieve(q, top_k=1, score_threshold=-1.0)
        s = res.get("sources", [])
        src = s[0].get("source", "") if s else ""
        score = s[0].get("score", 0.0) if s else 0.0
        hit = expect in (src or "")
        if hit:
            on_scores.append(score)
        print(f"{'':>2}  {'Y' if hit else 'n':<5} {score:>6.3f}  "
              f"{expect:<22} {_src_basename(src):<22} {q[:30]}")

    off_scores = []
    print("\nOFF-TOPIC probes (should ground on NOTHING; score is the junk ceiling):")
    print(f"{'':>2}  {'score':>6}  {'would-cite':<22} query")
    for q in REAL_OFFTOPIC:
        res = await rag.retrieve(q, top_k=1, score_threshold=-1.0)
        s = res.get("sources", [])
        src = s[0].get("source", "") if s else ""
        score = s[0].get("score", 0.0) if s else 0.0
        off_scores.append(score)
        print(f"{'':>2}  {score:>6.3f}  {_src_basename(src):<22} {q[:40]}")

    print("-" * 100)
    if not on_scores:
        print("DEGRADE LOUDLY: no on-topic probe matched its expected source — "
              "the runtime index does not contain the expected files; cannot "
              "compute a safe window.")
        return 1
    on_floor = min(on_scores)
    off_ceiling = max(off_scores) if off_scores else 0.0
    print(f"ON-TOPIC score FLOOR  (lowest true hit) : {on_floor:.3f}")
    print(f"OFF-TOPIC score CEILING (highest junk)  : {off_ceiling:.3f}")
    if off_ceiling < on_floor:
        print(f"SAFE THRESHOLD WINDOW: ({off_ceiling:.3f}, {on_floor:.3f})  "
              f"-> any value here rejects all probed junk and keeps all probed hits.")
        mid = (off_ceiling + on_floor) / 2
        print(f"  midpoint (max margin) : {mid:.3f}")
    else:
        print("NO CLEAN WINDOW: junk ceiling >= hit floor on this index; "
              "a global threshold cannot separate — needs a reranker / per-namespace gate.")
    inside = off_ceiling < threshold < on_floor
    print(f"CONFIGURED threshold={threshold}: "
          f"{'INSIDE safe window (blocks probed junk, keeps probed hits)' if inside else 'OUTSIDE safe window'}")
    print("=" * 100)
    return 0


def print_report(result: dict, top_k: int, threshold: float, vectors: int) -> None:
    print("=" * 100)
    print(f"RETRIEVAL EVAL  |  embedder={os.environ.get('SYNTHESUS_EMBEDDER')}  "
          f"top_k={top_k}  threshold={threshold}  index_vectors={vectors}")
    print("=" * 100)
    print(f"{'#':>2}  {'PASS':<5} {'top1':<5} {'inK':<4} {'score':>6}  "
          f"{'expected':<18} {'got':<18} question")
    print("-" * 100)
    for i, r in enumerate(result["rows"], 1):
        print(f"{i:>2}  "
              f"{'HIT' if r['passed'] else 'miss':<5} "
              f"{'Y' if r['top_correct'] else 'n':<5} "
              f"{'Y' if r['in_topk'] else 'n':<4} "
              f"{r['top_score']:>6.3f}  "
              f"{r['expected']:<18} {r['top_src']:<18} {r['q'][:34]}")
    print("-" * 100)
    # --- unanswerable-query section ---
    print("UNANSWERABLE queries (correct = ground on NOTHING; a hit here is FALSE grounding):")
    print(f"{'':>2}  {'RESULT':<16} {'score':>6}  {'would-cite':<18} question")
    for r in result["neg_rows"]:
        verdict = "FALSE-GROUND" if r["false_grounding"] else "ok-rejected"
        print(f"{'':>2}  {verdict:<16} {r['top_score']:>6.3f}  "
              f"{r['top_src']:<18} {r['q'][:40]}")
    print("-" * 100)
    print(f"GROUNDED-HIT RATE (answerable: top-1 correct AND score>=threshold): "
          f"{result['hits']}/{result['n']} = {result['grounded_hit_rate']*100:.1f}%")
    print(f"RECALL@{top_k} (correct source anywhere in top_k):                   "
          f"{result['recall_k']}/{result['n']} = {result['recall_at_k']*100:.1f}%")
    print(f"FALSE-GROUNDING RATE (unanswerable wrongly grounded, lower=better):  "
          f"{result['false_grounding']}/{result['n_neg']} = {result['false_grounding_rate']*100:.1f}%")
    print(f"OVERALL QUALITY (true hits + correct rejections)/(all queries):      "
          f"{result['hits'] + result['correct_rejections']}/{result['n'] + result['n_neg']} "
          f"= {result['overall_quality']*100:.1f}%")
    print("=" * 100)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Synthesus retrieval-quality harness")
    ap.add_argument("--top-k", type=int, default=None,
                    help="override RAGPipeline top_k (default: pipeline default)")
    ap.add_argument("--threshold", type=float, default=None,
                    help="override score_threshold (default: pipeline default)")
    ap.add_argument("--keep", action="store_true", help="keep the scratch index dir")
    ap.add_argument("--real-index", action="store_true",
                    help="READ-ONLY calibration probe of the live runtime index "
                         "(reports the empirical safe-threshold window)")
    ap.add_argument("--real-index-path", default=str(ROOT / "data" / "user_faiss.index"))
    ap.add_argument("--real-meta-path", default=str(ROOT / "data" / "user_meta.json"))
    args = ap.parse_args(argv)

    # Resolve dials: fall back to the RAGPipeline signature defaults so this
    # harness measures whatever the CURRENT code ships as the default.
    import inspect
    sig = inspect.signature(RAGPipeline.__init__).parameters
    top_k = args.top_k if args.top_k is not None else sig["top_k"].default
    threshold = args.threshold if args.threshold is not None else sig["score_threshold"].default

    if args.real_index:
        return asyncio.run(run_real_index_probe(
            args.real_index_path, args.real_meta_path, threshold))

    scratch = Path(tempfile.mkdtemp(prefix="synthesus_reteval_"))
    corpus_dir = scratch / "corpus"
    index_dir = scratch / "index"
    try:
        rag = build_index(corpus_dir, index_dir, top_k, threshold)
        result = asyncio.run(run_eval(rag, top_k, threshold))
        print_report(result, top_k, threshold, rag.total_vectors)
    finally:
        if args.keep:
            print(f"[kept scratch index at {scratch}]")
        else:
            shutil.rmtree(scratch, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
