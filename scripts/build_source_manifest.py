#!/usr/bin/env python3
"""Build a SHA-256 manifest for non-runtime Knowledge Cloud source planes."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_ROOTS = [
    "sources",
    "pipelines",
    "patterns",
    "synthetic",
    "grounding_corpus",
    "support_models",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def iter_files(root: Path, roots: list[str], exclude: set[str] | None = None):
    exclude = exclude or set()
    for rel_root in roots:
        base = root / rel_root
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file():
                rel = path.relative_to(root).as_posix()
                if rel in exclude:
                    continue
                yield path


def build_manifest(root: Path, roots: list[str], output: str = "manifests/source_manifest.json") -> dict:
    artifacts = []
    for path in iter_files(root, roots, exclude={output}):
        rel = path.relative_to(root).as_posix()
        artifacts.append({
            "path": rel,
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    return {
        "version": "1",
        "kind": "synthesus-knowledge-source-plane",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "roots": roots,
        "artifacts": artifacts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--output", default="manifests/source_manifest.json")
    parser.add_argument("--include-root", action="append", dest="roots", help="Additional/replacement root to include; may be repeated")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    roots = args.roots or DEFAULT_ROOTS
    manifest = build_manifest(root, roots, args.output)
    out = root / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(manifest['artifacts'])} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
