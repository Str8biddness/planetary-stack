#!/usr/bin/env python3
"""Research-paper corpus fetcher backed by OpenAlex.

OpenAlex (https://openalex.org) is a free, open scholarly catalogue with a
generous rate limit (100k requests/day/IP with mailto). Abstracts are stored
as an inverted index per OpenAlex policy and reconstructed locally.

We use OpenAlex as a primary backend because the arXiv export API is rate
limited at the shared egress IP layer in many sandboxed environments. The
entries produced here carry attribution to OpenAlex and the underlying paper
URL (DOI or OpenAlex landing page).
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import yaml

USER_AGENT = "SynthesusKnowledgeCloudBot/0.2 (mailto:dakinellegood@gmail.com)"
OPENALEX_URL = "https://api.openalex.org/works"
LICENSE = "OpenAlex-CC0-metadata"


def reconstruct_abstract(inverted_index: dict | None) -> str:
    if not inverted_index:
        return ""
    positions: list[tuple[int, str]] = []
    for word, positions_list in inverted_index.items():
        for p in positions_list:
            positions.append((p, word))
    positions.sort()
    return " ".join(word for _, word in positions)


def slugify(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    return value[:80]


def fetch_query(query: str, *, per_page: int = 25, retries: int = 3) -> list[dict]:
    params = {
        "search": query,
        "per_page": min(per_page, 200),
        "mailto": "dakinellegood@gmail.com",
    }
    url = OPENALEX_URL + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return payload.get("results", [])
        except Exception as exc:
            last = exc
            time.sleep(1.5 * attempt)
    logging.warning("openalex query failed %s: %s", query, last)
    return []


def to_entry(work: dict, query: str) -> dict | None:
    title = (work.get("title") or "").strip()
    if not title:
        return None
    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
    if not abstract:
        return None
    doi = work.get("doi") or ""
    openalex_id = (work.get("id") or "").rstrip("/").rsplit("/", 1)[-1]
    landing = doi or work.get("id") or ""
    year = work.get("publication_year")
    authors = []
    for ship in work.get("authorships", []) or []:
        name = (ship.get("author") or {}).get("display_name")
        if name:
            authors.append(name)
    return {
        "id": f"oa_{slugify(openalex_id or slugify(title))}",
        "category": "research_paper",
        "title": title,
        "summary": abstract,
        "facts": [
            f"Year: {year}" if year else "Year: unknown",
            f"Authors: {', '.join(authors[:8])}" if authors else "Authors: unknown",
            f"Source query: {query}",
            f"OpenAlex id: {openalex_id}" if openalex_id else "",
        ],
        "authors": authors,
        "year": year,
        "source": {
            "url": landing or f"https://api.openalex.org/works/{openalex_id}",
            "license": LICENSE,
            "attribution": "OpenAlex (CC0 metadata); abstracts via OpenAlex inverted-index reconstruction.",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def load_existing(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    out: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        out[entry["id"]] = entry
    return out


def write_entries(path: Path, entries: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sorted_entries = sorted(entries, key=lambda e: e["id"])
    with path.open("w", encoding="utf-8") as fh:
        for entry in sorted_entries:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch OpenAlex research papers")
    parser.add_argument("--queries", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--per-page", type=int, default=25)
    parser.add_argument("--sleep", type=float, default=0.6)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    cfg = yaml.safe_load(args.queries.read_text(encoding="utf-8"))
    queries: list[str] = cfg.get("queries", [])
    existing = {} if args.refresh else load_existing(args.out)
    combined: dict[str, dict] = dict(existing)
    stats = {"queries": 0, "results": 0, "kept": 0, "duplicates": 0, "skipped_no_abstract": 0}

    for query in queries:
        stats["queries"] += 1
        results = fetch_query(query, per_page=args.per_page)
        for work in results:
            stats["results"] += 1
            entry = to_entry(work, query)
            if entry is None:
                stats["skipped_no_abstract"] += 1
                continue
            if entry["id"] in combined:
                stats["duplicates"] += 1
                continue
            combined[entry["id"]] = entry
            stats["kept"] += 1
        time.sleep(args.sleep)

    write_entries(args.out, combined.values())
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
