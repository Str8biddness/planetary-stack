"""GitHub connector for the Synthesus expansion drive.

Pulls a repository's source + doc files and ingests them into the user's local
grounding index, so Synthesus can answer questions about the user's OWN code.
The repo is fetched from the user's GitHub; embedding + indexing stay local.

Accepts an ``owner/repo`` shorthand, a full git URL, or a local path (already
cloned). For private repos pass a token (or set GITHUB_TOKEN). The fetch is the
only GitHub-specific part; ingestion is the shared engine in ``base``.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple

from .base import ingest_local_tree


def _clone(repo: str, token: Optional[str], ref: Optional[str]) -> str:
    tmp = tempfile.mkdtemp(prefix="synth_gh_")
    url = repo
    # owner/repo shorthand -> https URL (with token for private repos)
    if repo.count("/") == 1 and not repo.startswith(("http", "git@")):
        url = f"https://{token}@github.com/{repo}.git" if token else f"https://github.com/{repo}.git"
    elif token and repo.startswith("https://github.com/"):
        url = repo.replace("https://", f"https://{token}@")
    cmd = ["git", "clone", "--depth", "1"]
    if ref:
        cmd += ["--branch", ref]
    cmd += [url, tmp]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return tmp


def ingest_github_repo(
    rag,
    repo: str,
    token: Optional[str] = None,
    ref: Optional[str] = None,
    max_file_kb: int = 256,
    namespace: Optional[str] = None,
) -> Tuple[int, int, str]:
    """Ingest a GitHub repo (owner/repo, URL, or local path) into ``rag``'s index.

    Returns (chunks_added, files_ingested, repo_label). Appends (never wipes) and
    saves the index. Fetch = the user's repo; embedding/indexing = local.
    """
    local = Path(repo)
    cloned: Optional[str] = None
    if local.exists() and local.is_dir():
        root, label = local, local.name
    else:
        cloned = _clone(repo, token, ref)
        root = Path(cloned)
        label = repo.rstrip("/").split("/")[-1].replace(".git", "")
    ns = namespace or f"github:{label}"

    try:
        added, files = ingest_local_tree(
            rag, root, label=label, namespace=ns, domain="github", max_file_kb=max_file_kb
        )
        return added, files, label
    finally:
        if cloned:
            shutil.rmtree(cloned, ignore_errors=True)
