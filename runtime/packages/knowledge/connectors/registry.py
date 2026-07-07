"""Connector registry for the agnostic expansion drive.

A single source of truth the desktop UI can enumerate to render "add a source"
options, and the auto-ingest orchestrator can dispatch against. Each entry
describes one source type; ``status`` is honest about what's live vs. planned.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


@dataclass(frozen=True)
class Connector:
    key: str                      # stable id, e.g. "github"
    label: str                    # human label for the UI
    input_hint: str               # what the user provides
    status: str                   # "live" | "planned"
    needs_auth: bool              # does it require a token/OAuth?
    loader: Optional[Callable] = field(default=None, compare=False)  # lazy import -> ingest fn


def _github():
    from .github_connector import ingest_github_repo
    return ingest_github_repo


def _folder():
    from .folder_connector import ingest_folder
    return ingest_folder


def _rclone():
    from .rclone_connector import ingest_rclone
    return ingest_rclone


CONNECTORS: Dict[str, Connector] = {
    "github": Connector(
        key="github", label="GitHub repo",
        input_hint="owner/repo, git URL, or local path",
        status="live", needs_auth=False, loader=_github,
    ),
    "folder": Connector(
        key="folder", label="Folder / Synced cloud drive",
        input_hint="path to a folder (incl. synced Google Drive / Dropbox / OneDrive)",
        status="live", needs_auth=False, loader=_folder,
    ),
    # Any-cloud, one tool: rclone FUSE-mounts the remote read-only (virtual ROM)
    # with a local SSD cache, then we ingest it like a folder. Auth is a one-time
    # `rclone config` per provider — no token ever passes through here.
    "rclone": Connector(
        key="rclone", label="Cloud drive (any provider — rclone)",
        input_hint="rclone remote, e.g. onedrive: or gdrive:Work",
        status="live", needs_auth=True, loader=_rclone,
    ),
    "gdrive": Connector(
        key="gdrive", label="Google Drive",
        input_hint="rclone remote, e.g. gdrive: (set up once via `rclone config`)",
        status="live", needs_auth=True, loader=_rclone,
    ),
    "onedrive": Connector(
        key="onedrive", label="OneDrive",
        input_hint="rclone remote, e.g. onedrive: (set up once via `rclone config`)",
        status="live", needs_auth=True, loader=_rclone,
    ),
    "dropbox": Connector(
        key="dropbox", label="Dropbox",
        input_hint="rclone remote, e.g. dropbox: (set up once via `rclone config`)",
        status="live", needs_auth=True, loader=_rclone,
    ),
    "box": Connector(
        key="box", label="Box",
        input_hint="rclone remote, e.g. box: (set up once via `rclone config`)",
        status="live", needs_auth=True, loader=_rclone,
    ),
    "s3": Connector(
        key="s3", label="Amazon S3",
        input_hint="rclone remote, e.g. s3:bucket/prefix (set up once via `rclone config`)",
        status="live", needs_auth=True, loader=_rclone,
    ),
    # iCloud Drive has NO official public API — the honest path is the Folder
    # connector pointed at the local iCloud sync folder, not a native connector.
    "icloud": Connector(
        key="icloud", label="iCloud Drive (use Folder)",
        input_hint="point Folder at your synced iCloud Drive folder",
        status="planned", needs_auth=True,
    ),
}


def list_connectors() -> List[dict]:
    """UI-facing list of source types (no loader callables)."""
    return [
        {
            "key": c.key, "label": c.label, "input_hint": c.input_hint,
            "status": c.status, "needs_auth": c.needs_auth,
        }
        for c in CONNECTORS.values()
    ]


def get_loader(key: str) -> Callable:
    """Resolve a live connector's ingest function, or raise."""
    c = CONNECTORS.get(key)
    if c is None:
        raise KeyError(f"unknown connector: {key}")
    if c.status != "live" or c.loader is None:
        raise NotImplementedError(f"connector '{key}' is {c.status}, not yet available")
    return c.loader()
