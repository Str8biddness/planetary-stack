#!/usr/bin/env python3
"""Wikipedia corpus fetcher for the Knowledge Cloud.

Uses the public MediaWiki API to fetch plaintext extracts and persist them as
JSONL entries grouped by category. All content is CC-BY-SA 4.0 with attribution
recorded per entry.

Usage:
    python -m pipelines.ingest_corpus.wikipedia_fetcher \\
        --seeds corpus/hardware_blueprints/seeds/wikipedia_seeds.yaml \\
        --out corpus/hardware_blueprints/entries

The fetcher is idempotent and resumable: existing entries with the same id and
source URL are kept unless --refresh is provided.
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
from typing import Any, Iterable

import yaml

USER_AGENT = "SynthesusKnowledgeCloudBot/0.2 (+https://github.com/Str8biddness/synthesus-knowledge-cloud)"
MW_API = "https://en.wikipedia.org/w/api.php"
LICENSE = "CC-BY-SA-4.0"
ATTRIBUTION = "Wikipedia contributors (https://en.wikipedia.org); released under CC-BY-SA 4.0."


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def mw_extract(title: str, *, sentences: int = 12, retries: int = 3) -> dict[str, Any] | None:
    params = {
        "action": "query",
        "format": "json",
        "prop": "extracts|info",
        "explaintext": "true",
        "exsectionformat": "plain",
        "redirects": "1",
        "inprop": "url",
        "titles": title,
    }
    url = MW_API + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
            pages = data.get("query", {}).get("pages", {})
            if not pages:
                return None
            page = next(iter(pages.values()))
            if "missing" in page:
                return None
            extract = page.get("extract") or ""
            if sentences and extract:
                parts = re.split(r"(?<=[.!?])\s+", extract.strip())
                extract = " ".join(parts[: sentences * 4])
            return {
                "title": page.get("title", title),
                "url": page.get("fullurl") or f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}",
                "extract": extract.strip(),
                "pageid": page.get("pageid"),
            }
        except Exception as exc:
            last = exc
            time.sleep(0.5 * attempt)
    logging.warning("wikipedia fetch failed for %s: %s", title, last)
    return None


def make_entry(category: str, title: str, payload: dict[str, Any]) -> dict[str, Any]:
    summary_lines = [line for line in payload["extract"].splitlines() if line.strip()]
    summary = " ".join(summary_lines[:8])
    facts = [line for line in summary_lines if 20 <= len(line) <= 220][:12]
    return {
        "id": slugify(title),
        "category": category,
        "title": payload["title"],
        "summary": summary,
        "facts": facts,
        "source": {
            "url": payload["url"],
            "license": LICENSE,
            "attribution": ATTRIBUTION,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def load_existing(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    out: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        out[entry["id"]] = entry
    return out


def write_entries(path: Path, entries: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sorted_entries = sorted(entries, key=lambda e: e["id"])
    with path.open("w", encoding="utf-8") as fh:
        for entry in sorted_entries:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Wikipedia corpus entries")
    parser.add_argument("--seeds", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--sentences", type=int, default=12)
    parser.add_argument("--refresh", action="store_true", help="Refetch all entries even if cached")
    parser.add_argument("--sleep", type=float, default=0.15, help="Polite delay between API calls")
    parser.add_argument("--limit", type=int, default=0, help="Cap titles per category (0 = unlimited)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    seeds = yaml.safe_load(args.seeds.read_text(encoding="utf-8"))
    if not isinstance(seeds, dict):
        print("ERROR: seed file must be a dict of category -> titles", file=sys.stderr)
        return 1

    stats = {"categories": 0, "fetched": 0, "kept": 0, "skipped": 0, "missing": 0}
    for category, titles in seeds.items():
        if category in {"version", "description", "max_results_per_query", "sort_by", "queries"}:
            continue
        if not isinstance(titles, list):
            continue
        stats["categories"] += 1
        path = args.out / f"{category}.jsonl"
        existing = {} if args.refresh else load_existing(path)
        new_entries: dict[str, dict[str, Any]] = dict(existing)
        capped = titles if args.limit <= 0 else titles[: args.limit]
        for title in capped:
            entry_id = slugify(title)
            if entry_id in existing and not args.refresh:
                stats["skipped"] += 1
                continue
            payload = mw_extract(title, sentences=args.sentences)
            if payload is None:
                stats["missing"] += 1
                continue
            entry = make_entry(category, title, payload)
            new_entries[entry["id"]] = entry
            stats["fetched"] += 1
            stats["kept"] += 1
            time.sleep(args.sleep)
        write_entries(path, new_entries.values())
        logging.info("category=%s entries=%d", category, len(new_entries))

    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
