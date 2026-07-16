#!/usr/bin/env python3
"""Adapter that yields Knowledge-Cloud KnowledgeEntry-compatible objects from
corpus JSONL files (hardware_blueprints + emulation).

The Synthesus populator (`pipelines/build/kn_populator.py`) consumes objects
with: key, question, answer, category, value, source, slots, metadata. We map
the corpus schema into that shape so a single profile can ingest Jeopardy,
ConceptNet, and these public-source corpora through one pipeline.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator, Iterable

CORPUS_ROOTS = [
    Path("corpus/hardware_blueprints/entries"),
    Path("corpus/emulation/entries"),
]


@dataclass
class CorpusKnowledgeEntry:
    key: str
    question: str
    answer: str
    category: str
    value: int = 0
    source: str = ""
    slots: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "question": self.question,
            "answer": self.answer,
            "category": self.category,
            "value": self.value,
            "source": self.source,
            "slots": self.slots,
            "metadata": self.metadata,
        }


def _entry_question(entry: dict) -> str:
    title = entry.get("title") or entry.get("id") or "entity"
    category = entry.get("category", "")
    if category.startswith("research_paper"):
        return f"What does the paper '{title}' describe?"
    if category.startswith("cpu") or category.startswith("gpu") or category in {"npu", "tpu", "qpu", "fpga"}:
        return f"What are the key facts about {title}?"
    if category.startswith("memory") or category.startswith("storage"):
        return f"What is {title} and how does it work?"
    if category.startswith("hypervisor") or category.startswith("emulator") or category.startswith("container_runtime"):
        return f"What is {title} and what is it used for?"
    if category.startswith("concept_"):
        return f"What is {title} in the context of virtualization/emulation?"
    return f"What is {title}?"


def _entry_answer(entry: dict) -> str:
    summary = (entry.get("summary") or "").strip()
    facts = entry.get("facts") or []
    fact_str = "\n- ".join([str(f) for f in facts if f]) if facts else ""
    if fact_str:
        return f"{summary}\n\nKey facts:\n- {fact_str}".strip()
    return summary


def load_corpus_entries(roots: Iterable[Path] | None = None) -> Generator[CorpusKnowledgeEntry, None, None]:
    for root in (roots or CORPUS_ROOTS):
        root = Path(root)
        if not root.exists():
            continue
        for path in sorted(root.glob("*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                yield CorpusKnowledgeEntry(
                    key=f"corpus_{entry['id']}",
                    question=_entry_question(entry),
                    answer=_entry_answer(entry),
                    category=entry.get("category", "corpus"),
                    value=10,
                    source=(entry.get("source") or {}).get("url", "corpus"),
                    slots={
                        "title": entry.get("title", ""),
                        "manufacturer": entry.get("manufacturer", ""),
                        "isa": entry.get("isa", ""),
                        "year": entry.get("year") or 0,
                    },
                    metadata={
                        "license": (entry.get("source") or {}).get("license"),
                        "attribution": (entry.get("source") or {}).get("attribution"),
                        "authors": entry.get("authors", []),
                        "corpus_path": str(path),
                    },
                )


def main() -> int:
    parser = argparse.ArgumentParser(description="Dump corpus entries as JSONL (for piping into the populator)")
    parser.add_argument("--root", action="append", default=[], help="Override default corpus roots (repeatable)")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    roots = [Path(r) for r in args.root] if args.root else None
    count = 0
    for entry in load_corpus_entries(roots):
        sys.stdout.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        count += 1
        if args.limit and count >= args.limit:
            break
    sys.stderr.write(f"dumped {count} corpus entries\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
