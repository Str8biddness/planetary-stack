"""
Kaggle Dataset Loader for Synthesus Knowledge Index Population.

Datasets:
1. Jeopardy Questions (jwolle1/jeopardy_clue_dataset) — 538k clues, TSV
   Source: https://github.com/jwolle1/jeopardy_clue_dataset
2. ConceptNet Assertions — commonsense knowledge graph (~2M edges)
   Source: https://github.com/commonsense/conceptnet5/wiki/Downloads

No Kaggle credentials needed — all data downloaded via HTTP.
"""

from __future__ import annotations

import csv
import gzip
import logging
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Dict, Generator, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class KnowledgeEntry:
    """A single knowledge node from any dataset."""
    key: str
    question: str      # the "fact" or query side
    answer: str        # the answer / response side
    category: str
    value: str = ""
    source: str = ""
    row_index: int = 0


# ---------------------------------------------------------------------------
# Shared sampling helpers
# ---------------------------------------------------------------------------


def _reservoir_sample(entries, sample_size: int, seed: int) -> List[KnowledgeEntry]:
    """Sample a stream without knowing its total size in advance."""
    if sample_size <= 0:
        return []

    rng = random.Random(seed)
    reservoir: List[KnowledgeEntry] = []
    seen = 0
    for entry in entries:
        seen += 1
        if len(reservoir) < sample_size:
            reservoir.append(entry)
            continue
        idx = rng.randrange(seen)
        if idx < sample_size:
            reservoir[idx] = entry
    reservoir.sort(key=lambda entry: entry.row_index)
    return reservoir


# ---------------------------------------------------------------------------
# Jeopardy loader — 538k clues, TSV (jwolle1/jeopardy_clue_dataset)
# ---------------------------------------------------------------------------

JEOPARDY_TSV_URL = (
    "https://raw.githubusercontent.com/jwolle1/jeopardy_clue_dataset/"
    "main/combined_season1-41.tsv"
)
JEOPARDY_EXTRA_URL = (
    "https://raw.githubusercontent.com/jwolle1/jeopardy_clue_dataset/"
    "main/extra_matches.tsv"
)


def _iter_jeopardy_entries(files: List[Path]) -> Generator[KnowledgeEntry, None, None]:
    row_idx = 0
    for f in files:
        with open(f, newline="", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            for row in reader:
                question = row.get("question", "").strip()
                answer = row.get("answer", "").strip()
                category = row.get("category", "general").strip().lower()
                round_ = row.get("round", "")
                value = row.get("clue_value", "")
                air_date = row.get("air_date", "")

                if not question or not answer:
                    row_idx += 1
                    continue
                if answer.endswith("."):
                    answer = answer[:-1]
                if len(question) < 5:
                    row_idx += 1
                    continue

                meta = f"round={round_}"
                if value and value not in ("", "None"):
                    meta += f" value={value}"
                if air_date:
                    meta += f" date={air_date}"

                yield KnowledgeEntry(
                    key=f"jeopardy_{row_idx:08d}",
                    question=question,
                    answer=answer,
                    category=category,
                    value=meta,
                    source="jeopardy_github",
                    row_index=row_idx,
                )
                row_idx += 1


def load_jeopardy(
    cache_dir: str = "./data",
    sample_size: Optional[int] = None,
    seed: int = 42,
    include_extra: bool = True,
) -> Generator[KnowledgeEntry, None, None]:
    """
    Load Jeopardy clues from the jwolle1/jeopardy_clue_dataset GitHub repo.

    TSV fields: round, clue_value, daily_double_value, category,
                comments, answer, question, air_date, notes
    """
    data_dir = Path(cache_dir) / "jeopardy"
    data_dir.mkdir(parents=True, exist_ok=True)
    main_tsv = data_dir / "combined_season1-41.tsv"

    if not main_tsv.exists():
        logger.info("Downloading Jeopardy main TSV (73 MB) ...")
        _download_file(JEOPARDY_TSV_URL, main_tsv, desc="Jeopardy main")
    else:
        logger.info(f"Using cached: {main_tsv}")

    extra_tsv = data_dir / "extra_matches.tsv"
    if include_extra and not extra_tsv.exists():
        logger.info("Downloading extra_matches.tsv (2 MB) ...")
        try:
            _download_file(JEOPARDY_EXTRA_URL, extra_tsv, desc="Jeopardy extra")
        except RuntimeError as exc:
            logger.warning("Skipping optional extra_matches.tsv after download failure: %s", exc)
    elif include_extra:
        logger.info(f"Using cached: {extra_tsv}")

    files = [main_tsv]
    if include_extra and extra_tsv.exists():
        files.append(extra_tsv)

    if sample_size is None:
        count = 0
        for entry in _iter_jeopardy_entries(files):
            yield entry
            count += 1
        logger.info(f"Jeopardy: {count} entries")
        return

    logger.info(f"Sampling {sample_size} Jeopardy entries via reservoir sampling")
    sampled = _reservoir_sample(_iter_jeopardy_entries(files), sample_size, seed)
    logger.info(f"Jeopardy: {len(sampled)} sampled entries")
    for entry in sampled:
        yield entry


# ---------------------------------------------------------------------------
# ConceptNet loader — commonsense knowledge graph (~2M edges)
# ---------------------------------------------------------------------------

CONCEPTNET_URL = (
    "https://s3.amazonaws.com/conceptnet/downloads/2019/edges/"
    "conceptnet-assertions-5.7.0.csv.gz"
)


def _iter_conceptnet_entries(
    gz_path: Path,
    relations: List[str],
) -> Generator[KnowledgeEntry, None, None]:
    included_relations = {f"/r/{r}" for r in relations}
    row_idx = 0

    with gzip.open(gz_path, "rt", encoding="utf-8") as fh:
        for line in fh:
            row_idx += 1

            parts = line.rstrip("\n").split("\t")
            if len(parts) < 5:
                continue

            try:
                uri, rel, start, end, meta_json = parts[:5]
            except ValueError:
                continue

            if rel not in included_relations:
                continue

            # Extract English text from /c/en/... nodes
            if not start.startswith("/c/en/") or not end.startswith("/c/en/"):
                continue

            start_text = start[6:].replace("_", " ")
            end_text = end[6:].replace("_", " ")

            if not start_text or not end_text:
                continue

            # Parse weight from meta
            weight = 1.0
            try:
                if meta_json.startswith("{"):
                    import json
                    meta = json.loads(meta_json)
                    weight = float(meta.get("weight", 1.0))
            except Exception:
                pass

            # Build natural-language question-style fact
            rel_label = rel[3:]
            question_templates = {
                "RelatedTo":    f"What is related to {start_text}?",
                "IsA":          f"What is {start_text}?",
                "UsedFor":      f"What is {start_text} used for?",
                "CapableOf":    f"What can {start_text} do?",
                "AtLocation":   f"Where is {start_text} located?",
                "HasA":         f"What does {start_text} have?",
                "PartOf":       f"What is {start_text} part of?",
                "Causes":       f"What does {start_text} cause?",
                "Synonym":      f"What is a synonym for {start_text}?",
                "Antonym":      f"What is an antonym for {start_text}?",
                "DerivedFrom":  f"What is {start_text} derived from?",
                "HasContext":   f"What context is {start_text} used in?",
                "Desires":      f"What does {start_text} desire?",
            }
            question = question_templates.get(rel_label, f"How is {start_text} related to {end_text}?")
            answer = end_text

            yield KnowledgeEntry(
                key=f"conceptnet_{row_idx:08d}",
                question=question,
                answer=answer,
                category=f"conceptnet:{rel_label.lower()}",
                value=f"weight={weight:.3f}",
                source="conceptnet5",
                row_index=row_idx,
            )


def load_conceptnet(
    cache_dir: str = "./data",
    sample_size: Optional[int] = None,
    seed: int = 42,
    relations: Optional[List[str]] = None,
) -> Generator[KnowledgeEntry, None, None]:
    """
    Load ConceptNet assertions as KnowledgeEntry objects.

    The raw file is ~67 MB gzipped (CSV, ~2.8M assertions).
    Only yields English, high-quality relations by default.

    Relations to include (configurable):
      /r/RelatedTo, /r/IsA, /r/PartOf, /r/HasA, /r/UsedFor,
      /r/CapableOf, /r/AtLocation, /r/Synonym, /r/Antonym,
      /r/DerivedFrom, /r/HasContext
    """
    if relations is None:
        relations = [
            "RelatedTo", "IsA", "PartOf", "HasA", "UsedFor",
            "CapableOf", "AtLocation", "Synonym", "Antonym",
            "DerivedFrom", "HasContext", "Causes", "Desires",
        ]

    data_dir = Path(cache_dir) / "conceptnet"
    data_dir.mkdir(parents=True, exist_ok=True)
    gz_path = data_dir / "conceptnet-assertions-5.7.0.csv.gz"

    if not gz_path.exists():
        logger.info("Downloading ConceptNet assertions (~67 MB gzipped) ...")
        _download_file(CONCEPTNET_URL, gz_path, desc="ConceptNet", timeout=600)
    else:
        logger.info(f"Using cached ConceptNet: {gz_path}")

    if sample_size is None:
        count = 0
        for entry in _iter_conceptnet_entries(gz_path, relations):
            yield entry
            count += 1
        logger.info(f"ConceptNet: {count} entries")
        return

    logger.info(f"Sampling {sample_size} ConceptNet entries via reservoir sampling")
    sampled = _reservoir_sample(_iter_conceptnet_entries(gz_path, relations), sample_size, seed)
    logger.info(f"ConceptNet: {len(sampled)} sampled entries")
    for entry in sampled:
        yield entry


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _download_file(url: str, dest: Path, desc: str = "",
                    timeout: int = 300, retries: int = 3, backoff_s: float = 1.5) -> None:
    """Download via streaming requests with a small retry loop."""
    logger.info(f"  Downloading {desc or url} ...")
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, timeout=timeout, stream=True)
            resp.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
            size_mb = dest.stat().st_size / 1024**2
            logger.info(f"  → {dest} ({size_mb:.1f} MB)")
            return
        except Exception as e:
            last_error = e
            if dest.exists():
                dest.unlink()
            if attempt < retries:
                delay = backoff_s * attempt
                logger.warning(
                    "  Download attempt %d/%d failed for %s: %s; retrying in %.1fs",
                    attempt,
                    retries,
                    desc or url,
                    e,
                    delay,
                )
                time.sleep(delay)
                continue
            raise RuntimeError(f"Failed to download {url}: {e}") from e


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def load_all_datasets(
    cache_dir: str = "./data",
    sample_jeopardy: Optional[int] = None,
    sample_conceptnet: Optional[int] = None,
    seed: int = 42,
) -> Generator[KnowledgeEntry, None, None]:
    """
    Load Jeopardy + ConceptNet.

    Args:
        cache_dir: Where to cache downloaded files.
        sample_jeopardy: Limit Jeopardy to N entries (None = all 538k).
        sample_conceptnet: Limit ConceptNet to N entries (None = all ~2M).
        seed: Random seed for reproducibility.
    """
    logger.info("=" * 60)
    logger.info("Loading knowledge datasets into Synthesus ...")

    count_j = 0
    for entry in load_jeopardy(cache_dir=cache_dir, sample_size=sample_jeopardy, seed=seed):
        yield entry
        count_j += 1
        if count_j % 100_000 == 0:
            logger.info(f"  Jeopardy: streamed {count_j} ...")
    logger.info(f"Jeopardy: {count_j} entries")

    count_c = 0
    for entry in load_conceptnet(cache_dir=cache_dir, sample_size=sample_conceptnet, seed=seed):
        yield entry
        count_c += 1
        if count_c % 100_000 == 0:
            logger.info(f"  ConceptNet: streamed {count_c} ...")
    logger.info(f"ConceptNet: {count_c} entries")

    logger.info(f"TOTAL: {count_j + count_c} knowledge entries")


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s",
                        stream=sys.stdout)
    for i, e in enumerate(load_all_datasets(sample_jeopardy=5, sample_conceptnet=5)):
        print(f"[{e.source}] Cat: {e.category} | Q: {e.question[:55]}... | A: {e.answer[:35]}")