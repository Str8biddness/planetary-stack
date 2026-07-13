#!/usr/bin/env python3
"""
Safe path / id helpers for Synthesus.

Threat model
------------
User-supplied identifiers (session_id, scene_id, utterance_id, char_id) are often
concatenated into filesystem paths such as ``{root}/{id}.json``. A crafted id like
``../../../../tmp/evil`` or ``foo/../../../etc/passwd`` is a **path traversal**
attack: if unsanitized, write/read escapes the intended root directory.

Defense
-------
``safe_id`` strips everything except ``[A-Za-z0-9_-]``, bounds length, and maps
empty results to the literal ``\"invalid\"`` so callers always get a single
path segment that cannot climb out of a join with a fixed root.

Use this at every sink where a client id becomes a filename. Do not re-copy
the regex into call sites — import here so the bug class cannot drift.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Union

_ID_SAFE = re.compile(r"[^A-Za-z0-9_-]")


def safe_id(raw: str, maxlen: int = 64) -> str:
    """Sanitize a user-supplied id for use as a single path segment.

    Parameters
    ----------
    raw:
        Untrusted identifier (session / scene / utterance / character id).
    maxlen:
        Maximum length after sanitization (default 64).

    Returns
    -------
    str
        Filename-safe id consisting only of ``[A-Za-z0-9_-]``, length in
        ``[1, maxlen]``. Empty input or all-stripped input becomes ``\"invalid\"``.

    Notes
    -----
    This does **not** open files. Callers must still join under a trusted root
    and (ideally) assert the resolved path stays under that root for defense
    in depth.
    """
    s = _ID_SAFE.sub("", str(raw if raw is not None else ""))[: int(maxlen)]
    return s or "invalid"


def safe_join(root: Union[str, Path], raw_id: str, *suffix_parts: str, maxlen: int = 64) -> Path:
    """Join ``root / safe_id(raw_id) / ...`` and assert no escape from root.

    Raises
    ------
    ValueError
        If the resolved path is outside ``root`` (should be impossible after
        safe_id, but catches programmer error / symlink races).
    """
    root_p = Path(root).resolve()
    sid = safe_id(raw_id, maxlen=maxlen)
    target = root_p.joinpath(sid, *suffix_parts).resolve()
    try:
        target.relative_to(root_p)
    except ValueError as exc:
        raise ValueError(
            f"path escape blocked: id={raw_id!r} -> {target} not under {root_p}"
        ) from exc
    return target
