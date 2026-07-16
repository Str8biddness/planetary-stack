"""Shared ingestion engine for the agnostic expansion drive.

Every connector's job is identical once its source is on disk: walk the tree,
chunk the readable files, and append (never wipe) into the user's local index
with provenance. That common part lives here so each connector is a thin
"fetch" front (GitHub clone, folder path, cloud download) that ends in one call
to ``ingest_local_tree``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Tuple
from dataclasses import dataclass, field
from collections import Counter

@dataclass
class IngestResult:
    chunks_added: int
    files_ingested: int
    by_ext: dict[str, int] = field(default_factory=Counter)
    skipped_by_ext: dict[str, int] = field(default_factory=Counter)
    skipped_reasons: dict[str, int] = field(default_factory=Counter)

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
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
) -> IngestResult:
    """Walk ``root``, chunk readable files, append into ``rag``. Returns
    (chunks_added, files_ingested). Appends + saves; never wipes existing data.

    Each chunk's indexed text is prefixed ``[relpath]`` so filename queries
    retrieve well, and carries a structured ``source`` = ``label/relpath`` for
    provenance.
    """
    root = Path(root)
    
    total_eligible = 0
    for f in root.rglob("*"):
        if f.is_file() and f.suffix.lower() in SOURCE_EXTS and not any(part in SKIP_DIRS for part in f.parts):
            total_eligible += 1

    patterns: list[dict] = []
    result = IngestResult(chunks_added=0, files_ingested=0)
    current = 0

    for f in root.rglob("*"):
        if not f.is_file():
            continue
            
        ext = f.suffix.lower()
        if any(part in SKIP_DIRS for part in f.parts):
            result.skipped_reasons["skip_dir"] += 1
            result.skipped_by_ext[ext] += 1
            continue
            
        if ext not in SOURCE_EXTS:
            result.skipped_reasons["unsupported_type"] += 1
            result.skipped_by_ext[ext] += 1
            continue
            
        try:
            if f.stat().st_size > max_file_kb * 1024:
                result.skipped_reasons["too_large"] += 1
                result.skipped_by_ext[ext] += 1
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            result.skipped_reasons["unreadable"] += 1
            result.skipped_by_ext[ext] += 1
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
                
        result.files_ingested += 1
        result.by_ext[ext] += 1
        current += 1
        if progress_cb:
            progress_cb(current, total_eligible, rel)

    added = rag.append_patterns(patterns)
    if added:
        rag.save_index()
    result.chunks_added = added
    return result
