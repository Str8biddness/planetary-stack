#!/usr/bin/env python3
"""arXiv corpus fetcher for the emulation research plane.

Uses the public arXiv export API (Atom feed) per their usage guidelines: at
most one request every 3 seconds, batched results, identifier persisted to
allow incremental updates.
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
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import yaml

USER_AGENT = "SynthesusKnowledgeCloudBot/0.2 (+https://github.com/Str8biddness/synthesus-knowledge-cloud)"
ARXIV_API = "http://export.arxiv.org/api/query"
ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}
DEFAULT_LICENSE = "arxiv.org-default"


def fetch_query(query: str, *, max_results: int = 40, sort_by: str = "relevance") -> list[dict]:
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "relevance" if sort_by == "relevance" else "submittedDate",
        "sortOrder": "descending",
    }
    url = ARXIV_API + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=45) as response:
        raw = response.read().decode("utf-8")
    root = ET.fromstring(raw)
    items: list[dict] = []
    for entry in root.findall("a:entry", ATOM_NS):
        arxiv_id_full = (entry.findtext("a:id", default="", namespaces=ATOM_NS) or "").strip()
        arxiv_id = arxiv_id_full.rsplit("/", 1)[-1].split("v")[0]
        title = re.sub(r"\s+", " ", (entry.findtext("a:title", default="", namespaces=ATOM_NS) or "")).strip()
        summary = re.sub(r"\s+", " ", (entry.findtext("a:summary", default="", namespaces=ATOM_NS) or "")).strip()
        published = (entry.findtext("a:published", default="", namespaces=ATOM_NS) or "").strip()
        year: int | None = None
        if len(published) >= 4 and published[:4].isdigit():
            year = int(published[:4])
        authors = [
            (author.findtext("a:name", default="", namespaces=ATOM_NS) or "").strip()
            for author in entry.findall("a:author", ATOM_NS)
        ]
        if not arxiv_id or not title or not summary:
            continue
        items.append(
            {
                "arxiv_id": arxiv_id,
                "title": title,
                "summary": summary,
                "authors": [a for a in authors if a],
                "year": year,
                "published": published,
                "abs_url": f"https://arxiv.org/abs/{arxiv_id}",
            }
        )
    return items


def to_entry(item: dict, query: str) -> dict:
    return {
        "id": f"arxiv_{item['arxiv_id'].replace('.', '_')}",
        "category": "research_paper",
        "title": item["title"],
        "summary": item["summary"],
        "facts": [
            f"arXiv id {item['arxiv_id']}",
            f"Discovered via query: {query}",
            f"Authors: {', '.join(item['authors'][:6])}" if item["authors"] else "Authors: unknown",
        ],
        "authors": item["authors"],
        "year": item["year"],
        "source": {
            "url": item["abs_url"],
            "license": DEFAULT_LICENSE,
            "attribution": "arXiv.org; abstracts redistributable per arXiv.org policy.",
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
    parser = argparse.ArgumentParser(description="Fetch arXiv emulation research papers")
    parser.add_argument("--queries", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path, help="Output JSONL file")
    parser.add_argument("--sleep", type=float, default=3.0, help="Seconds between API requests")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    cfg = yaml.safe_load(args.queries.read_text(encoding="utf-8"))
    queries: list[str] = cfg.get("queries", [])
    max_results = int(cfg.get("max_results_per_query", 40))
    sort_by = cfg.get("sort_by", "relevance")

    existing = {} if args.refresh else load_existing(args.out)
    combined: dict[str, dict] = dict(existing)
    stats = {"queries": 0, "fetched": 0, "new": 0, "duplicates": 0}
    for query in queries:
        stats["queries"] += 1
        try:
            items = fetch_query(query, max_results=max_results, sort_by=sort_by)
        except Exception as exc:
            logging.warning("query failed %s: %s", query, exc)
            time.sleep(args.sleep)
            continue
        for item in items:
            entry = to_entry(item, query)
            stats["fetched"] += 1
            if entry["id"] in combined:
                stats["duplicates"] += 1
                continue
            combined[entry["id"]] = entry
            stats["new"] += 1
        time.sleep(args.sleep)

    write_entries(args.out, combined.values())
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
