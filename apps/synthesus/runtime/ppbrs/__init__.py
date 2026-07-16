"""Compatibility package for legacy ``ppbrs.*`` imports."""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
__path__ = [str(_ROOT / "packages" / "reasoning")]

from packages.reasoning import *  # noqa: F401,F403

