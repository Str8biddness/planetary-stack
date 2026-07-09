"""Folder connector for the Synthesus expansion drive.

Ingests any local directory tree. This is the zero-auth cloud path: Google Drive
for Desktop, Dropbox, and OneDrive all SYNC to a local folder, so pointing the
drive at that folder grounds Synthesus on the user's cloud files with no OAuth
and nothing leaving the machine. Also covers plain local project folders.

The API connectors (raw Drive/Dropbox/S3, for headless/unsynced access) are thin
fetch-to-temp fronts that end in this same ingestion path.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Tuple

from .base import ingest_local_tree, IngestResult


def ingest_folder(
    rag,
    path: str,
    namespace: Optional[str] = None,
    max_file_kb: int = 256,
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
) -> Tuple[IngestResult, str]:
    """Ingest a local folder tree (e.g. a synced cloud drive) into ``rag``.

    Returns (result, label). Appends (never wipes) + saves.
    """
    root = Path(path).expanduser()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Not a directory: {root}")
    label = root.name or str(root)
    ns = namespace or f"folder:{label}"
    result = ingest_local_tree(
        rag, root, label=label, namespace=ns, domain="folder", max_file_kb=max_file_kb, progress_cb=progress_cb
    )
    return result, label
