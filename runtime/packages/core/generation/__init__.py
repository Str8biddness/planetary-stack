"""Compatibility package for legacy ``core.generation.*`` imports."""

from __future__ import annotations

from pathlib import Path

_PACKAGES_DIR = Path(__file__).resolve().parents[2]
__path__ = [str(_PACKAGES_DIR / "reasoning" / "generation")]
