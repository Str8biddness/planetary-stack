"""Mirror resolution for Knowledge Cloud bundle downloads.

The primary mirror is the zo.pub collection. Operators can override or extend
the mirror list via env or CLI flags so local Synthesus installs can fail over
to a private bucket or an internal staging URL without code changes.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Sequence

DEFAULT_PRIMARY = "https://zo.pub/syntech/synthesus-knowledge"

# We intentionally do not include `raw.githubusercontent.com` as a default mirror:
# LFS-tracked artifacts at that URL return the LFS pointer text, not the file
# bytes. zo.pub serves the real artifacts.
DEFAULT_MIRRORS: tuple[str, ...] = (DEFAULT_PRIMARY,)

_ENV_LIST = "SYNTHESUS_KNOWLEDGE_MIRRORS"
_ENV_SINGLE = "SYNTHESUS_KNOWLEDGE_CLOUD_URL"


def _clean(items: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in items:
        if not raw:
            continue
        url = raw.strip().rstrip("/")
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def resolve_mirrors(
    base_url: str | None = None,
    extra: Sequence[str] | None = None,
    *,
    env: dict[str, str] | None = None,
) -> list[str]:
    """Resolve the effective ordered list of mirrors.

    Precedence:
      1. Explicit `base_url` argument (single mirror).
      2. `--mirror` / `extra` CLI list.
      3. `SYNTHESUS_KNOWLEDGE_MIRRORS` env var (comma-separated).
      4. `SYNTHESUS_KNOWLEDGE_CLOUD_URL` env var (single mirror).
      5. Built-in defaults.

    The result is always a non-empty deduplicated list.
    """
    env = dict(env if env is not None else os.environ)
    candidates: list[str] = []
    if base_url:
        candidates.append(base_url)
    if extra:
        candidates.extend(extra)
    env_list = env.get(_ENV_LIST)
    if env_list:
        candidates.extend(env_list.split(","))
    env_single = env.get(_ENV_SINGLE)
    if env_single:
        candidates.append(env_single)
    if not candidates:
        candidates.extend(DEFAULT_MIRRORS)
    cleaned = _clean(candidates)
    return cleaned or list(DEFAULT_MIRRORS)


def describe_mirrors(mirrors: Sequence[str]) -> str:
    if not mirrors:
        return "(none)"
    return ", ".join(mirrors)
