"""GitHub connector for the Synthesus expansion drive.

Pulls a repository's source + doc files and ingests them into the user's local
grounding index, so Synthesus can answer questions about the user's OWN code.
The repo is fetched from the user's GitHub; embedding + indexing stay local.

Accepts an ``owner/repo`` shorthand, a full git URL, or a local path (already
cloned). For private repos pass a token for the one fetch. The fetch is the only
GitHub-specific part; ingestion is the shared engine in ``base``.
"""
from __future__ import annotations

import base64
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional, Tuple
from urllib.parse import urlsplit

from .base import ingest_local_tree, IngestResult


def _clone_url(repo: str, token: Optional[str]) -> tuple[str, Optional[str]]:
    """Return a credential-free clone URL and a validated optional token."""

    value = repo.strip()
    credential = (token or "").strip() or None
    if credential and any(character.isspace() for character in credential):
        raise ValueError("GitHub access tokens must not contain whitespace")

    initial = urlsplit(value)
    if not initial.scheme and not value.startswith("git@") and value.count("/") == 1:
        url = f"https://github.com/{value}.git"
    else:
        url = value

    parsed = urlsplit(url)
    scheme = parsed.scheme.lower()
    if parsed.password is not None:
        raise ValueError("credentials embedded in repository URLs are not allowed")
    if parsed.username is not None and scheme != "ssh":
        raise ValueError("credentials embedded in repository URLs are not allowed")
    if parsed.query or parsed.fragment:
        raise ValueError("repository URLs must not contain a query or fragment")
    if scheme in {"http", "https"}:
        if scheme != "https":
            raise ValueError("GitHub repositories must use HTTPS or an SSH remote")
        if credential and (parsed.hostname or "").lower() != "github.com":
            raise ValueError("GitHub access tokens may be sent only to github.com")
    elif credential:
        raise ValueError("access-token authentication requires an HTTPS github.com URL")
    return url, credential


def _clone(repo: str, token: Optional[str], ref: Optional[str]) -> str:
    tmp = tempfile.mkdtemp(prefix="synth_gh_")
    try:
        url, credential = _clone_url(repo, token)
        cmd = ["git", "clone", "--depth", "1"]
        if ref:
            cmd += ["--branch", ref]
        cmd += [url, tmp]

        # Keep the origin URL credential-free. Git consumes this one-process
        # config from the child environment and does not write it to .git/config.
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        if credential:
            basic = base64.b64encode(
                f"x-access-token:{credential}".encode("utf-8")
            ).decode("ascii")
            env.update(
                {
                    "GIT_CONFIG_COUNT": "1",
                    "GIT_CONFIG_KEY_0": "http.https://github.com/.extraHeader",
                    "GIT_CONFIG_VALUE_0": f"Authorization: Basic {basic}",
                }
            )
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        return tmp
    except subprocess.CalledProcessError as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        raise ValueError(
            f"GitHub clone failed (git exit {exc.returncode}); verify repository, "
            "token permissions, and network access"
        ) from None
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def ingest_github_repo(
    rag,
    repo: str,
    token: Optional[str] = None,
    ref: Optional[str] = None,
    max_file_kb: int = 256,
    namespace: Optional[str] = None,
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
) -> Tuple[IngestResult, str]:
    """Ingest a GitHub repo (owner/repo, URL, or local path) into ``rag``'s index.

    Returns (result, repo_label). Appends (never wipes) and
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
        result = ingest_local_tree(
            rag, root, label=label, namespace=ns, domain="github", max_file_kb=max_file_kb, progress_cb=progress_cb
        )
        return result, label
    finally:
        if cloned:
            shutil.rmtree(cloned, ignore_errors=True)
