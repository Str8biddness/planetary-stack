"""Shared ingestion engine for the agnostic expansion drive.

Every connector's job is identical once its source is on disk: walk the tree,
chunk the readable files, and append (never wipe) into the user's local index
with provenance. That common part lives here so each connector is a thin
"fetch" front (GitHub clone, folder path, cloud download) that ends in one call
to ``ingest_local_tree``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

# Source + doc file types worth grounding on.
SOURCE_EXTS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".rb", ".php",
    ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".swift", ".kt", ".scala", ".sh",
    ".md", ".markdown", ".rst", ".txt", ".json", ".yaml", ".yml", ".toml",
    ".cfg", ".ini", ".html", ".css", ".sql",
}
SKIP_DIRS = {
    ".git", "node_modules", "dist", "build", "__pycache__", ".venv", "venv",
    "vendor", ".next", "target", ".mypy_cache", ".pytest_cache",
}


def chunk_text(text: str, size: int = 500) -> list[str]:
    words, chunks, cur, cur_len = text.split(), [], [], 0
    for w in words:
        if cur_len + len(w) > size and cur:
            chunks.append(" ".join(cur)); cur, cur_len = [w], len(w)
        else:
            cur.append(w); cur_len += len(w) + 1
    if cur:
        chunks.append(" ".join(cur))
    return chunks


def ingest_local_tree(
    rag,
    root,
    *,
    label: str,
    namespace: str,
    domain: str = "file",
    max_file_kb: int = 256,
) -> Tuple[int, int]:
    """Walk ``root``, chunk readable files, append into ``rag``. Returns
    (chunks_added, files_ingested). Appends + saves; never wipes existing data.

    Each chunk's indexed text is prefixed ``[relpath]`` so filename queries
    retrieve well, and carries a structured ``source`` = ``label/relpath`` for
    provenance.
    """
    root = Path(root)
    patterns: list[dict] = []
    files = 0
    for f in root.rglob("*"):
        if not f.is_file() or f.suffix.lower() not in SOURCE_EXTS:
            continue
        if any(part in SKIP_DIRS for part in f.parts):
            continue
        try:
            if f.stat().st_size > max_file_kb * 1024:
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        rel = str(f.relative_to(root))
        for chunk in chunk_text(text):
            if chunk.strip():
                patterns.append({
                    "pattern": f"[{rel}] {chunk}",
                    "response": chunk,
                    "namespace": namespace,
                    "domain": domain,
                    "source": f"{label}/{rel}",
                })
        files += 1

    added = rag.append_patterns(patterns)
    if added:
        rag.save_index()
    return added, files
