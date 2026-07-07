"""rclone connector — the universal cloud login for the expansion drive.

One tool, 70+ backends (Google Drive, OneDrive, Dropbox, Box, S3, ...). We do
NOT boot anything and we do NOT build an image: we FUSE-mount the remote with
rclone's VFS cache so the FIRST read pulls from the cloud and EVERY read after
is straight off the local SSD at hardware speed. The corpus is read-only at
runtime (`--read-only`), so the cache never has to reconcile writes — that's the
"nobody writes it during runtime" design, enforced at the mount.

The mount is a plain filesystem. Ingestion is the exact same local walk / chunk /
embed path every other connector ends in — the mount just makes any cloud look
like a local folder. Zero bloat.

target forms:
  "onedrive:"            whole remote
  "gdrive:Work/notes"    a subfolder of the remote
  "/local/path"          already-local path (delegates to the folder connector)

Auth is out-of-band and one-time: `rclone config` creates the remote. We never
see or store a token here.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Optional, Set, Tuple

from .base import ingest_local_tree

MOUNTS_ROOT = Path.home() / ".synthesus" / "drive-mounts"
LOG_ROOT = Path.home() / ".synthesus"


def _list_remotes() -> Set[str]:
    """Configured rclone remote names (without the trailing ':')."""
    try:
        out = subprocess.run(
            ["rclone", "listremotes"], capture_output=True, text=True, timeout=15
        )
    except FileNotFoundError:
        raise ValueError("rclone is not installed. Install it, then run: rclone config")
    return {line.rstrip(":").strip() for line in out.stdout.splitlines() if line.strip()}


def _sanitize(spec: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", spec).strip("_") or "remote"


def ensure_mount(
    spec: str,
    *,
    vfs_cache_mode: str = "full",
    cache_max: str = "50G",
    dir_cache: str = "72h",
    timeout: int = 40,
) -> Path:
    """Idempotently FUSE-mount an rclone ``remote:path`` spec, read-only, cached.

    Returns the local mount path. Reuses an existing live mount. The mount runs
    as a detached background process (a mount — not a VM, not a booted image).
    """
    mp = MOUNTS_ROOT / _sanitize(spec)
    mp.mkdir(parents=True, exist_ok=True)
    if os.path.ismount(mp):
        return mp

    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    log = LOG_ROOT / f"rclone-{_sanitize(spec)}.log"
    cmd = [
        "rclone", "mount", spec, str(mp),
        "--read-only",                      # corpus is read-only at runtime
        "--vfs-cache-mode", vfs_cache_mode, # first read from cloud, rest from SSD
        "--vfs-cache-max-size", cache_max,
        "--dir-cache-time", dir_cache,
    ]
    with open(log, "a") as fh:
        subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT, start_new_session=True)

    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.ismount(mp):
            return mp
        time.sleep(0.5)
    raise ValueError(f"rclone mount for '{spec}' not ready in {timeout}s (see {log})")


def ingest_rclone(
    rag,
    target: str,
    namespace: Optional[str] = None,
    max_file_kb: int = 256,
) -> Tuple[int, int, str]:
    """Mount a cloud remote and ingest it into ``rag``.

    Returns (chunks_added, files_ingested, label). Appends (never wipes) + saves.
    """
    target = (target or "").strip()
    if not target:
        raise ValueError("target is required (e.g. 'onedrive:' or 'gdrive:Work')")

    # Already-local path: skip rclone entirely, use the folder path.
    is_remote = ":" in target and not target.startswith(("/", "~", "."))
    if not is_remote:
        from .folder_connector import ingest_folder
        return ingest_folder(rag, target, namespace=namespace, max_file_kb=max_file_kb)

    remote = target.split(":", 1)[0]
    remotes = _list_remotes()
    if remote not in remotes:
        have = ", ".join(sorted(remotes)) or "none configured"
        raise ValueError(
            f"rclone remote '{remote}' not found. Set it up once with `rclone config` "
            f"(currently have: {have})."
        )

    mount_path = ensure_mount(target)
    label = target.rstrip(":") or remote
    ns = namespace or f"cloud:{label}"
    added, files = ingest_local_tree(
        rag, mount_path, label=label, namespace=ns, domain="cloud", max_file_kb=max_file_kb
    )
    return added, files, label
